# 模块说明：持久业务任务 Handler；先检查版本再调用模型，提交时再次保护版本。
"""Ontology publication and notification state updates for durable jobs."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from pace.adapters.db.business import require_account, require_snapshot_sources
from pace.adapters.db.models import ConnectionRequest, Entity, EntityVersion, Match
from pace.application.contracts import SourceFile


class BusinessHandlers:
    """注入 LLM / Email / Event 能力；没有假装成功的未配置通道。"""

    def __init__(self, sessions, ontology=None, email=None, events=None):
        self.sessions, self.ontology, self.email, self.events = sessions, ontology, email, events

    async def build_ontology(self, payload):
        """过时任务零模型调用；双检版本使晚返回不能覆盖较新同步。"""
        user_id, version = UUID(payload["account_id"]), payload["version"]
        async with self.sessions() as session:
            entity = await session.get(Entity, user_id)
            completed = (
                await session.scalars(
                    select(EntityVersion).where(
                        EntityVersion.account_id == user_id, EntityVersion.version == version
                    )
                )
            ).one_or_none()
            if entity is None or entity.version != version or completed:
                return
            await require_account(session, user_id)
        try:
            files = [SourceFile.model_validate(f) for f in payload["files"]]
            if files and self.ontology is None:
                from pace.domain.errors import FeatureUnavailable

                raise FeatureUnavailable()
            ontology = await self.ontology.build(files, None) if files else ""
            async with self.sessions.begin() as session:
                entity = (
                    await session.scalars(
                        select(Entity).where(Entity.account_id == user_id).with_for_update()
                    )
                ).one()
                if entity.version != version:
                    return
                await require_account(session, user_id)
                exists = (
                    await session.scalars(
                        select(EntityVersion).where(
                            EntityVersion.account_id == user_id, EntityVersion.version == version
                        )
                    )
                ).one_or_none()
                if exists:
                    return
                sources = [
                    {k: f[k] for k in ("source_id", "name", "content_hash", "observed_at")}
                    for f in payload["files"]
                ]
                session.add(
                    EntityVersion(
                        account_id=user_id,
                        version=version,
                        snapshot={
                            "ontology": ontology,
                            "demands": payload["demands"],
                            "supplies": payload["supplies"],
                        },
                        sources=sources,
                        model=getattr(self.ontology, "model", "injected"),
                        prompt_version="ontology-v1",
                    )
                )
                entity.ontology = {"text": ontology}
                entity.status, entity.updated_at = "ready", datetime.now(UTC)
        except Exception:
            async with self.sessions.begin() as session:
                entity = (
                    await session.scalars(
                        select(Entity).where(Entity.account_id == user_id).with_for_update()
                    )
                ).one_or_none()
                if entity is not None and entity.version == version:
                    entity.status = "failed"
            raise

    async def send_email(self, payload):
        """稳定 delivery_id 重试；先前已捕获 / provider_accepted 时不再次调用。"""
        from pace.domain.errors import (
            AccountUnavailable,
            DeliveryUnavailable,
            EntityNotReady,
            PermanentDeliveryError,
        )

        if self.email is None:
            raise DeliveryUnavailable()
        async with self.sessions() as session:
            match = await session.get(Match, UUID(payload["connection_id"]))
            if match is None or match.email_status in ("captured", "provider_accepted"):
                return
            try:
                await require_account(session, match.requester_id)
                recipient = await require_account(session, match.candidate_id)
                if recipient.email != payload["recipient"]:
                    raise AccountUnavailable()
                await self._sources(session, match)
            except (AccountUnavailable, EntityNotReady):
                await self._state(payload, "email_status", "failed")
                raise PermanentDeliveryError() from None
        try:
            state = await self.email.deliver(
                payload["recipient"], payload["subject"], payload["body"], payload["delivery_id"]
            )
        except Exception:
            await self._state(payload, "email_status", "failed")
            raise
        await self._state(payload, "email_status", state)

    async def deliver_event(self, payload):
        """由 Event Adapter 再校验订阅 / 过期 / 撤销，不把无订阅当已投递。"""
        from pace.domain.errors import (
            AccountUnavailable,
            DeliveryUnavailable,
            EntityNotReady,
            PermanentDeliveryError,
        )

        if self.events is None:
            raise DeliveryUnavailable()
        try:
            async with self.sessions() as session:
                match = await session.get(Match, UUID(payload["connection_id"]))
                if match is None:
                    return
                if match.event_deliveries.get(payload["subscription_id"]) in {
                    "accepted_by_receiver",
                    "inactive",
                }:
                    return
                try:
                    await require_account(session, match.requester_id)
                    await require_account(session, match.candidate_id)
                    await self._sources(session, match)
                except (AccountUnavailable, EntityNotReady):
                    raise PermanentDeliveryError() from None
            state = await self.events.deliver_subscription(payload)
        except Exception:
            await self._state(payload, "event_status", "failed")
            raise
        await self._state(payload, "event_status", state)

    async def _sources(self, session, match):
        """发送前双向检查历史联系快照引用的来源仍在当前授权集合中。"""
        request = await session.get(ConnectionRequest, match.request_id)
        await require_snapshot_sources(session, request.snapshot_id)
        await require_snapshot_sources(session, match.candidate_snapshot_id)

    async def _state(self, payload, column, value):
        """只更新指定通道；不改写 connect 的原始幂等回执。"""
        async with self.sessions.begin() as session:
            match = (
                await session.scalars(
                    select(Match)
                    .where(Match.id == UUID(payload["connection_id"]))
                    .with_for_update()
                )
            ).one_or_none()
            if match:
                if column == "event_status":
                    states = {**match.event_deliveries, payload["subscription_id"]: value}
                    match.event_deliveries = states
                    values = set(states.values())
                    match.event_status = (
                        "failed"
                        if "failed" in values
                        else "queued"
                        if "queued" in values
                        else "accepted_by_receiver"
                        if "accepted_by_receiver" in values
                        else "not_subscribed"
                    )
                else:
                    setattr(match, column, value)

    def registry(self):
        """生产注册表三种业务任务；缺配置的具体方法明确失败。"""
        return {
            "ontology.build": self.build_ontology,
            "email.send": self.send_email,
            "event.deliver": self.deliver_event,
        }
