# 模块说明：业务事务、候选查询、快照映射与通知原子入队。
# 同键 advisory 锁避免并发重复选择；候选资格在返回联系方式前再次加锁检查。
"""PostgreSQL business transaction adapter; no provider SDK imports."""

import hashlib
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, text

from pace.adapters.db.jobs import enqueue
from pace.adapters.db.models import (
    Account,
    ConnectionRequest,
    Entity,
    EntityVersion,
    EventSubscription,
    Match,
    SyncReceipt,
)
from pace.application.contracts import (
    PROFILE_FORMAT,
    CandidateResult,
    ConnectionMatched,
    ConnectResult,
    NotificationState,
    SyncEntityResult,
    payload_hash,
)
from pace.domain.errors import (
    AccountUnavailable,
    EntityNotReady,
    IdempotencyConflict,
    VersionConflict,
)
from pace.domain.gmail import canonical_gmail
from pace.domain.models import CONSENT_VERSION, EntitySnapshot


async def advisory_lock(session, key: str):
    """稳定 64-bit 事务锁；Hash 碰撞最多额外串行，不改变数据归属。"""
    lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def snapshot(row: EntityVersion) -> EntitySnapshot:
    """DB 已完成版本 → 文本领域值，永不使用未完成 Entity 的临时 Ontology。"""
    data = row.snapshot
    return EntitySnapshot(
        row.account_id,
        row.version,
        data["ontology"],
        tuple(data.get("demands", [])),
        tuple(data.get("supplies", [])),
    )


def eligible(account: Account) -> bool:
    """Gmail + Google sub + 验证 + 注册披露同意 + 启用共同决定资格。"""
    try:
        return bool(
            canonical_gmail(account.email) == account.email
            and account.google_subject
            and account.enabled
            and account.email_verified_at
            and account.consented_at
            and account.consent_version == CONSENT_VERSION
        )
    except ValueError:
        return False


async def require_account(session, user_id, *, lock=False):
    """未授权对象统一拒绝，不区分不存在与别人账号的内部信息。"""
    query = select(Account).where(Account.id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    account = (await session.scalars(query)).one_or_none()
    if account is None or not eligible(account):
        raise AccountUnavailable()
    return account


async def latest(session, user_id):
    """只查 PA 直接发布的完成版本；旧 LLM 历史需首次重新同步才能入池。"""
    return (
        await session.scalars(
            select(EntityVersion)
            .where(
                EntityVersion.account_id == user_id, EntityVersion.prompt_version == PROFILE_FORMAT
            )
            .order_by(EntityVersion.version.desc())
            .limit(1)
        )
    ).one_or_none()


async def require_current_snapshot(session, snapshot_id):
    """完整画像替换撤销旧版本；旧匹配回执及待投递通知不能重新披露旧资料。"""
    row = await session.get(EntityVersion, snapshot_id)
    entity = await session.get(Entity, row.account_id, populate_existing=True) if row else None
    if (
        row is None
        or entity is None
        or row.prompt_version != PROFILE_FORMAT
        or entity.status != "ready"
        or row.version != entity.version
        or not any((row.snapshot["ontology"], row.snapshot["demands"], row.snapshot["supplies"]))
    ):
        raise EntityNotReady()


class BusinessRepository:
    """Session 工厂为唯一基础设施依赖；连接与同步事务分别持有稳定键。"""

    def __init__(self, sessions):
        self.sessions = sessions

    @asynccontextmanager
    async def connection(self, principal, data):
        """网络选择在有预算的事务中进行，避免同键重复模型调用。"""
        async with self.sessions.begin() as session:
            await advisory_lock(session, f"connect:{principal.user_id}:{data.request_id}")
            yield ConnectionUnit(session, principal, data)

    async def synchronize(self, principal, data):
        """锁账号串行修改 Entity；相同请求在版本判断前重放原回执。"""
        async with self.sessions.begin() as session:
            await require_account(session, principal.user_id, lock=True)
            old = (
                await session.scalars(
                    select(SyncReceipt).where(
                        SyncReceipt.account_id == principal.user_id,
                        SyncReceipt.request_id == data.request_id,
                    )
                )
            ).one_or_none()
            digest = payload_hash(data)
            if old:
                if old.payload_hash != digest:
                    raise IdempotencyConflict()
                return SyncEntityResult.model_validate(old.result)
            entity = await session.get(Entity, principal.user_id, with_for_update=True)
            if entity is None:
                entity = Entity(
                    account_id=principal.user_id,
                    version=0,
                    files=[],
                    demands=[],
                    supplies=[],
                    ontology={},
                    status="building",
                )
                session.add(entity)
            if (
                data.expected_entity_version is not None
                and data.expected_entity_version != entity.version
            ):
                raise VersionConflict()
            previous = await latest(session, principal.user_id)
            profile = {
                "ontology": data.ontology,
                "demands": data.demands,
                "supplies": data.supplies,
            }
            changed = (
                previous is None
                or previous.version != entity.version
                or previous.snapshot != profile
            )
            if changed:
                entity.version += 1
                entity.ontology = {"text": data.ontology}
                entity.demands, entity.supplies = data.demands, data.supplies
                session.add(
                    EntityVersion(
                        account_id=entity.account_id,
                        version=entity.version,
                        snapshot=profile,
                        sources=[],
                        model=None,
                        prompt_version=PROFILE_FORMAT,
                    )
                )
            # 最近同步时间单独于快照版本；重复内容不新增历史 / 不触发模型。
            entity.status, entity.updated_at = "ready", datetime.now(UTC)
            result = SyncEntityResult(
                status="accepted",
                entity_version=entity.version,
                changed=changed,
            )
            session.add(
                SyncReceipt(
                    account_id=entity.account_id,
                    request_id=data.request_id,
                    payload_hash=digest,
                    result=result.model_dump(mode="json"),
                )
            )
            return result


class ConnectionUnit:
    """connect 事务内查询 / 写入对象；不得脱离本 Session 使用。"""

    def __init__(self, session, principal, data):
        self.session, self.principal, self.data = session, principal, data
        self.request = None

    async def require_account(self, user_id):
        return await require_account(self.session, user_id)

    async def replay(self, digest):
        """成功结果严格原样重放；失败同载荷可重试；不同载荷冲突。"""
        self.request = (
            await self.session.scalars(
                select(ConnectionRequest).where(
                    ConnectionRequest.account_id == self.principal.user_id,
                    ConnectionRequest.request_id == self.data.request_id,
                )
            )
        ).one_or_none()
        if self.request:
            if self.request.payload_hash != digest:
                raise IdempotencyConflict()
            if self.request.result is not None:
                if self.request.result["status"] == "matched":
                    match = (
                        await self.session.scalars(
                            select(Match).where(
                                Match.request_id == self.request.id,
                            )
                        )
                    ).one()
                    # 幂等不能绕过当前授权；历史回执仍保存，但撤销后拒绝新的读取披露。
                    await require_account(self.session, match.candidate_id)
                    await require_current_snapshot(self.session, self.request.snapshot_id)
                    await require_current_snapshot(self.session, match.candidate_snapshot_id)
                return ConnectResult.model_validate(self.request.result)
        return None

    async def requester(self):
        row = await latest(self.session, self.principal.user_id)
        if row is None:
            raise EntityNotReady()
        await require_current_snapshot(self.session, row.id)
        return row, snapshot(row)

    async def candidates(self, limit):
        """资格过滤后取每账号最新完成版本；保留账号资料用于事务结果快照。"""
        newest = (
            select(EntityVersion.account_id, func.max(EntityVersion.version).label("version"))
            .group_by(EntityVersion.account_id)
            .subquery()
        )
        rows = (
            await self.session.execute(
                select(EntityVersion, Account)
                .join(
                    newest,
                    (EntityVersion.account_id == newest.c.account_id)
                    & (EntityVersion.version == newest.c.version),
                )
                .join(Account, Account.id == EntityVersion.account_id)
                .join(Entity, Entity.account_id == Account.id)
                .where(
                    Account.id != self.principal.user_id,
                    select(EventSubscription.id)
                    .where(
                        EventSubscription.account_id == Account.id,
                        EventSubscription.event_type == "connection.matched",
                        EventSubscription.verified_at.is_not(None),
                        EventSubscription.revoked_at.is_(None),
                        EventSubscription.expires_at > func.now(),
                    )
                    .exists(),
                    Account.enabled.is_(True),
                    Account.email_verified_at.is_not(None),
                    Account.consented_at.is_not(None),
                    Account.consent_version == CONSENT_VERSION,
                    Account.google_subject.is_not(None),
                    Account.google_subject != "",
                    Account.email.bool_op("~")(r"^[a-z0-9]+@gmail\.com$"),
                    Entity.status == "ready",
                    EntityVersion.version == Entity.version,
                    EntityVersion.prompt_version == PROFILE_FORMAT,
                    (Entity.ontology["text"].astext != "")
                    | (Entity.demands != [])
                    | (Entity.supplies != []),
                )
                .order_by(Account.id)
                .limit(limit)
            )
        ).all()
        # Gmail 规范检查属于应用资格；不能将非 Gmail legacy 账号入池。
        return [(row, snapshot(row), account) for row, account in rows if eligible(account)][:limit]

    async def begin_request(self, requester, digest):
        if self.request is None:
            self.request = ConnectionRequest(
                account_id=self.principal.user_id,
                request_id=self.data.request_id,
                payload_hash=digest,
                payload=self.data.model_dump(mode="json"),
                snapshot_id=requester[0].id,
            )
            self.session.add(self.request)
        self.request.status, self.request.error_code = "pending", None
        self.request.snapshot_id = requester[0].id
        await self.session.flush()

    async def mark_failed(self, code):
        self.request.status, self.request.error_code = "failed", code

    async def finish(self, requester, candidates, selection):
        """在提交前按 ID 顺序锁双方再校验；Match 与两通道 outbox 同事务。"""
        self.request.selection_trace = [asdict(t) for t in selection.traces]
        if selection.candidate_id is None:
            result = ConnectResult(
                status="no_match",
                request_id=self.data.request_id,
                entity_version=requester[1].version,
            )
        else:
            row, candidate, _ = next(
                c for c in candidates if c[1].user_id == selection.candidate_id
            )
            accounts = {}
            for user_id in sorted([self.principal.user_id, candidate.user_id], key=str):
                accounts[user_id] = await require_account(self.session, user_id, lock=True)
            await require_current_snapshot(self.session, requester[0].id)
            await require_current_snapshot(self.session, row.id)
            connection_id, event_id = uuid4(), uuid4()

            # 摘要为取自显式证据的模板，不能伪称 Jev 生成了自然语言理由。
            def contact(account, value):
                info = related_information(value, self.data.request_text)
                return CandidateResult(
                    pace_user_id=account.id, email=account.email, relevant_information=info
                )

            counterpart = contact(accounts[candidate.user_id], candidate)
            event = ConnectionMatched(
                event_id=event_id,
                occurred_at=datetime.now(UTC),
                connection_id=connection_id,
                request_summary=self.data.request_text[:2000],
                requester=contact(accounts[self.principal.user_id], requester[1]),
            )
            subscriptions = (
                await self.session.scalars(
                    select(EventSubscription).where(
                        EventSubscription.account_id == candidate.user_id,
                        EventSubscription.event_type == "connection.matched",
                        EventSubscription.verified_at.is_not(None),
                        EventSubscription.revoked_at.is_(None),
                        EventSubscription.expires_at > func.now(),
                    )
                )
            ).all()
            # 第一版服务对象必须有原生回调；选择期间订阅失效不能降级成仅邮件。
            if not subscriptions:
                raise AccountUnavailable()
            notification = NotificationState(event="queued", email="queued")
            match = Match(
                id=connection_id,
                request_id=self.request.id,
                requester_id=self.principal.user_id,
                candidate_id=candidate.user_id,
                candidate_snapshot_id=row.id,
                contact_snapshot={
                    "candidate": counterpart.model_dump(mode="json"),
                    "requester": event.requester.model_dump(mode="json"),
                },
                event_status=notification.event,
                event_deliveries={str(s.id): "queued" for s in subscriptions},
                email_status=notification.email,
            )
            self.session.add(match)
            await enqueue(
                self.session,
                "email.send",
                f"email:{connection_id}",
                {
                    "connection_id": str(connection_id),
                    "delivery_id": str(event_id),
                    "recipient": counterpart.email,
                    "subject": "PACE connection request",
                    "body": (
                        f"{event.request_summary}\n\n{event.requester.relevant_information}"
                        f"\nGmail: {event.requester.email}"
                    ),
                },
            )
            for subscription in subscriptions:
                await enqueue(
                    self.session,
                    "event.deliver",
                    f"event:{event_id}:{subscription.id}",
                    {
                        "connection_id": str(connection_id),
                        "subscription_id": str(subscription.id),
                        "event": event.model_dump(mode="json"),
                    },
                )
            result = ConnectResult(
                status="matched",
                request_id=self.data.request_id,
                entity_version=requester[1].version,
                connection_id=connection_id,
                candidate=counterpart,
                notification=notification,
            )
        self.request.status = result.status
        self.request.result = result.model_dump(mode="json")
        return result


def related_information(value, request_text):
    """只披露请求词命中的少量原文证据，不在联系人结果附送整个用户画像。"""
    words = set(re.findall(r"[a-z0-9]{2,}", request_text.lower()))
    words.difference_update(
        {
            "and",
            "for",
            "the",
            "with",
            "that",
            "this",
            "have",
            "need",
            "find",
            "want",
            "please",
            "help",
            "from",
            "on",
            "at",
            "to",
            "of",
            "in",
            "is",
            "or",
            "me",
            "we",
            "an",
            "as",
            "be",
        }
    )
    chinese = re.findall(r"[\u4e00-\u9fff]+", request_text)
    words.update(s[i : i + 2] for s in chinese for i in range(len(s) - 1))
    words.difference_update({"需要", "寻找", "帮我", "请问", "一个", "可以", "能够"})
    lines = [
        line.strip()
        for text_value in (value.ontology, *value.demands, *value.supplies)
        for line in text_value.splitlines()
        if line.strip()
    ]
    relevant = [
        (sum(word in line.lower() for word in words), index, line)
        for index, line in enumerate(lines)
    ]
    selected = sorted((item for item in relevant if item[0]), key=lambda item: (-item[0], item[1]))
    return (
        "\n".join(line for _, _, line in selected[:4])[:2000]
        or "No request-related excerpt available."
    )
