# 模块说明：真实 PostgreSQL 隔离 schema 验证业务事务 / 重放 / 版本与 Worker。
"""Providers are offline fakes; persistence and migrations are real."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pace.adapters.db.business import BusinessRepository
from pace.adapters.db.handlers import BusinessHandlers
from pace.adapters.db.jobs import JobQueue
from pace.adapters.db.models import (
    Account,
    ConnectionRequest,
    Entity,
    EntityVersion,
    EventSubscription,
    Job,
    Match,
)
from pace.adapters.delivery.capture import CaptureEmail
from pace.application.business import PersistentCommands
from pace.application.contracts import PROFILE_FORMAT, ConnectInput, SyncEntityInput
from pace.application.tournament import Tournament
from pace.domain.errors import (
    AccountUnavailable,
    IdempotencyConflict,
    PermanentDeliveryError,
    ProviderUnavailable,
    SelectionLimit,
    VersionConflict,
)
from pace.domain.models import CONSENT_VERSION, ChoiceDecision, Principal
from pace.interfaces.worker import Worker


async def account(sessions, name):
    """测试创建合成已验证账号；生产账号只从 Google callback 建立。"""
    async with sessions.begin() as session:
        row = Account(
            email=name + "@gmail.com",
            google_subject="synthetic-" + name,
            email_verified_at=datetime.now(UTC),
            consented_at=datetime.now(UTC),
            consent_version=CONSENT_VERSION,
            enabled=True,
            host_bindings=[],
        )
        session.add(row)
        await session.flush()
        return Principal(row.id, frozenset({"pace:sync", "pace:connect"}), "test-host")


class Choice:
    """可控制失败与 No Match；记录次数以证明重放没有费用。"""

    def __init__(self, fail=False, no_match=False):
        self.calls, self.fail, self.no_match = 0, fail, no_match

    async def choose(self, requester, request_text, candidates, context):
        self.calls += 1
        if self.fail:
            raise ProviderUnavailable()
        winner = "no_match" if self.no_match else str(candidates[0].user_id)
        return ChoiceDecision(
            winner,
            {
                **{str(c.user_id): float(str(c.user_id) == winner) for c in candidates},
                "no_match": float(winner == "no_match"),
            },
            "test",
        )


def commands(sessions, choice):
    return PersistentCommands(BusinessRepository(sessions), Tournament(choice))


def request():
    return ConnectInput(
        request_id=uuid4(),
        request_text="Python coaching",
        entity_version=1,
        context={"observed_at": datetime.now(UTC), "timezone": "Asia/Shanghai"},
    )


def profile(ontology="Python synthetic profile", **kwargs):
    """全量快照；空值明确清除。"""
    return SyncEntityInput.model_validate(
        dict(request_id=uuid4(), ontology=ontology, demands=[], supplies=[]) | kwargs
    )


async def ready(sessions, principal, subscribe=True):
    """合成 PA 入池：原生回调与画像都准备好；不发真实 challenge。"""
    if subscribe:
        async with sessions.begin() as session:
            session.add(
                EventSubscription(
                    account_id=principal.user_id,
                    client_id=principal.client_id,
                    subscription_key=str(uuid4()),
                    callback_url="https://receiver.example/hook",
                    signing_secret_ciphertext="synthetic",
                    verified_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
    return await commands(sessions, Choice()).sync_entity(principal, profile())


async def test_concurrent_connect_replay_and_atomic_capture(sessions, tmp_path):
    left, right = await account(sessions, "left"), await account(sessions, "right")
    await ready(sessions, left)
    await ready(sessions, right)
    choice, data = Choice(), request()
    service = commands(sessions, choice)
    results = await asyncio.gather(*(service.connect(left, data) for _ in range(3)))
    assert results[0].status == "matched" and results[0].candidate.email == "right@gmail.com"
    assert all(r == results[0] for r in results) and choice.calls == 1
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Match)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(Job).where(Job.kind == "email.send")
            )
            == 1
        )
        entity = await session.get(Entity, left.user_id)
        assert entity.demands == []  # 即时请求没有偷偷变成长期 Demand。
    worker = Worker(
        JobQueue(sessions),
        BusinessHandlers(
            sessions,
            email=CaptureEmail(tmp_path),
        ).registry(),
    )
    while await worker.run_once():
        pass
    async with sessions() as session:
        assert (await session.get(Match, results[0].connection_id)).email_status == "captured"
    assert len(list(tmp_path.glob("*.json"))) == 1
    with pytest.raises(IdempotencyConflict):
        await service.connect(left, data.model_copy(update={"request_text": "changed"}))


async def test_sync_immediate_publication_concurrency_noop_and_clear(sessions):
    principal = await account(sessions, "versions")
    service = commands(sessions, Choice())
    first = profile(
        "obsolete",
        expected_entity_version=0,
        demands=["explicit need"],
        supplies=["explicit offer"],
    )
    results = await asyncio.gather(*(service.sync_entity(principal, first) for _ in range(3)))
    assert all(r == results[0] for r in results)
    assert results[0].entity_status == "ready" and results[0].changed
    same = await service.sync_entity(
        principal,
        profile(
            "obsolete",
            expected_entity_version=1,
            demands=["explicit need"],
            supplies=["explicit offer"],
        ),
    )
    assert same.entity_version == 1 and not same.changed
    two = await service.sync_entity(principal, profile("current", expected_entity_version=1))
    assert two.entity_version == 2
    # 原同步回执重放不覆盖之后接受的内容；不同载荷复用 ID 明确冲突。
    assert await service.sync_entity(principal, first) == results[0]
    with pytest.raises(IdempotencyConflict):
        await service.sync_entity(principal, first.model_copy(update={"ontology": "changed"}))
    clear = await service.sync_entity(principal, profile("", expected_entity_version=2))
    assert clear.entity_version == 3 and clear.entity_status == "ready"
    async with sessions() as session:
        rows = (await session.scalars(select(EntityVersion).order_by(EntityVersion.version))).all()
        assert len(rows) == 3 and all(r.prompt_version == PROFILE_FORMAT for r in rows)
        assert rows[0].snapshot["demands"] == ["explicit need"]
        assert rows[0].snapshot["supplies"] == ["explicit offer"]
        assert rows[1].snapshot["demands"] == rows[1].snapshot["supplies"] == []
        assert rows[-1].snapshot == {"ontology": "", "demands": [], "supplies": []}
        assert all(r.sources == [] and r.model is None for r in rows)
        assert await session.scalar(select(func.count()).select_from(Job)) == 0


async def test_failed_provider_persists_failure_then_retry(sessions):
    left, right = await account(sessions, "failureleft"), await account(sessions, "failureright")
    await ready(sessions, left)
    await ready(sessions, right)
    choice, data = Choice(fail=True), request()
    service = commands(sessions, choice)
    with pytest.raises(ProviderUnavailable):
        await service.connect(left, data)
    async with sessions() as session:
        row = (await session.scalars(select(ConnectionRequest))).one()
        assert row.status == "failed" and row.result is None
        assert await session.scalar(select(func.count()).select_from(Match)) == 0
    choice.fail, choice.no_match = False, True
    assert (await service.connect(left, data)).status == "no_match"
    assert choice.calls == 2
    async with sessions.begin() as session:
        (await session.get(Account, left.user_id)).enabled = False
    with pytest.raises(AccountUnavailable):
        await service.connect(left, data)


async def test_revocation_during_selection_and_before_mail(sessions, tmp_path):
    left, right = await account(sessions, "revokedleft"), await account(sessions, "revokedright")
    await ready(sessions, left)
    await ready(sessions, right)

    class RevokingChoice(Choice):
        async def choose(self, requester, request_text, candidates, context):
            async with sessions.begin() as session:
                (await session.get(Account, right.user_id)).enabled = False
            return await super().choose(requester, request_text, candidates, context)

    with pytest.raises(AccountUnavailable):
        await commands(sessions, RevokingChoice()).connect(left, request())
    async with sessions.begin() as session:
        assert await session.scalar(select(func.count()).select_from(Match)) == 0
        (await session.get(Account, right.user_id)).enabled = True
    result = await commands(sessions, Choice()).connect(left, request())
    async with sessions.begin() as session:
        (await session.get(Account, left.user_id)).enabled = False
        job = (await session.scalars(select(Job).where(Job.kind == "email.send"))).one()
    with pytest.raises(PermanentDeliveryError):
        await BusinessHandlers(sessions, email=CaptureEmail(tmp_path)).send_email(job.payload)
    assert not list(tmp_path.iterdir())
    async with sessions() as session:
        assert (await session.get(Match, result.connection_id)).email_status == "failed"


async def test_candidate_budget_and_version_conflict(sessions):
    left = await account(sessions, "budgetleft")
    await ready(sessions, left)
    for name in ("budgetone", "budgettwo"):
        await ready(sessions, await account(sessions, name))
    choice = Choice()
    service = PersistentCommands(BusinessRepository(sessions), Tournament(choice), max_candidates=1)
    with pytest.raises(SelectionLimit):
        await service.connect(left, request())
    assert choice.calls == 0
    with pytest.raises(VersionConflict):
        await service.sync_entity(left, profile(expected_entity_version=0))
    async with sessions() as session:
        assert (await session.get(Entity, left.user_id)).version == 1


async def test_multiple_subscription_failure_is_visible_until_successful_retry(sessions, tmp_path):
    from pace.domain.errors import DeliveryUnavailable

    left, right = await account(sessions, "eventsleft"), await account(sessions, "eventsright")
    await ready(sessions, left)
    await ready(sessions, right, subscribe=False)
    async with sessions.begin() as session:
        for number in (1, 2):
            session.add(
                EventSubscription(
                    account_id=right.user_id,
                    client_id=f"host-{number}",
                    subscription_key=f"test-{number}",
                    callback_url="https://receiver.example/hook",
                    signing_secret_ciphertext="synthetic",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                    verified_at=datetime.now(UTC),
                )
            )
    result = await commands(sessions, Choice()).connect(left, request())
    assert result.notification.event == "queued"
    async with sessions() as session:
        jobs = (await session.scalars(select(Job).where(Job.kind == "event.deliver"))).all()
    assert len(jobs) == 2

    class Events:
        fail = False
        calls = 0

        async def deliver_subscription(self, payload):
            self.calls += 1
            if self.fail:
                raise DeliveryUnavailable()
            return "accepted_by_receiver"

    events = Events()
    handlers = BusinessHandlers(sessions, events=events, email=CaptureEmail(tmp_path))
    await handlers.deliver_event(jobs[0].payload)
    await handlers.deliver_event(jobs[0].payload)
    assert events.calls == 1  # DB 已保存接收回执时，重复 Worker 执行不再次发 webhook。
    async with sessions() as session:
        assert (await session.get(Match, result.connection_id)).event_status == "queued"
    events.fail = True
    with pytest.raises(DeliveryUnavailable):
        await handlers.deliver_event(jobs[1].payload)
    async with sessions() as session:
        assert (await session.get(Match, result.connection_id)).event_status == "failed"
    async with sessions() as session:
        email_job = (await session.scalars(select(Job).where(Job.kind == "email.send"))).one()
    # Events 失败不阻挡 Gmail；两通道独立，成功邮件也不掩盖事件失败。
    await handlers.send_email(email_job.payload)
    async with sessions() as session:
        match = await session.get(Match, result.connection_id)
        assert match.email_status == "captured" and match.event_status == "failed"
    events.fail = False
    await handlers.deliver_event(jobs[1].payload)
    async with sessions() as session:
        match = await session.get(Match, result.connection_id)
        assert match.event_status == "accepted_by_receiver" and match.email_status == "captured"


async def test_profile_clear_blocks_old_replay_candidates_and_notification(sessions, tmp_path):
    from pace.domain.errors import EntityNotReady

    left, right = await account(sessions, "sourceleft"), await account(sessions, "sourceright")
    await ready(sessions, left)
    await ready(sessions, right)
    service = commands(sessions, Choice())
    original_request = request()
    assert (await service.connect(left, original_request)).status == "matched"
    await service.sync_entity(right, profile(""))
    with pytest.raises(EntityNotReady):
        await service.connect(left, original_request)
    assert (await service.connect(left, request())).status == "no_match"
    async with sessions() as session:
        email_job = (await session.scalars(select(Job).where(Job.kind == "email.send"))).one()
    with pytest.raises(PermanentDeliveryError):
        await BusinessHandlers(sessions, email=CaptureEmail(tmp_path)).send_email(email_job.payload)
    assert not list(tmp_path.iterdir())
    # 同样阻止平台事件披露旧画像，而不是只保护邮件通道。
    async with sessions() as session:
        event_job = (await session.scalars(select(Job).where(Job.kind == "event.deliver"))).one()
    with pytest.raises(PermanentDeliveryError):
        await BusinessHandlers(sessions, events=object()).deliver_event(event_job.payload)


async def test_connect_rejects_stale_sync_version_before_provider(sessions):
    left, right = await account(sessions, "staleleft"), await account(sessions, "staleright")
    await ready(sessions, left)
    await ready(sessions, right)
    choice = Choice()
    service = commands(sessions, choice)
    await service.sync_entity(left, profile("Updated Python profile"))
    with pytest.raises(VersionConflict):
        await service.connect(left, request())
    assert choice.calls == 0
    assert (
        await service.connect(left, request().model_copy(update={"entity_version": 2}))
    ).status == "matched"


async def test_legacy_profile_and_old_consent_require_reauthorization_and_sync(sessions):
    from pace.domain.errors import EntityNotReady

    left, right = await account(sessions, "legacyleft"), await account(sessions, "legacyright")
    await ready(sessions, left)
    await ready(sessions, right)
    async with sessions.begin() as session:
        row = (
            await session.scalars(
                select(EntityVersion).where(EntityVersion.account_id == right.user_id)
            )
        ).one()
        row.prompt_version = "old-llm-format"
    service = commands(sessions, Choice())
    assert (await service.connect(left, request())).status == "no_match"
    with pytest.raises(EntityNotReady):
        await service.connect(right, request())
    updated = await service.sync_entity(right, profile())
    assert updated.entity_version == 2 and updated.changed
    async with sessions.begin() as session:
        (await session.get(Account, right.user_id)).consent_version = "gmail-connections-v1"
    with pytest.raises(AccountUnavailable):
        await service.sync_entity(right, profile())


async def test_candidates_without_active_callback_are_excluded(sessions):
    left, right = await account(sessions, "callbackleft"), await account(sessions, "callbackright")
    await ready(sessions, left)
    await ready(sessions, right, subscribe=False)
    choice = Choice()
    service = commands(sessions, choice)
    assert (await service.connect(left, request())).status == "no_match"
    assert choice.calls == 0
    await ready(sessions, right)
    assert (await service.connect(left, request())).status == "matched"
    async with sessions.begin() as session:
        sub = (
            await session.scalars(
                select(EventSubscription).where(EventSubscription.account_id == right.user_id)
            )
        ).one()
        sub.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await service.connect(left, request())).status == "no_match"
    assert choice.calls == 1
