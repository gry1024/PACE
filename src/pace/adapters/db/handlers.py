# 模块说明：两条独立通知通道；发送前重查账号和当前完整画像版本。
"""Notification state updates for durable jobs; ontology is published synchronously."""

from uuid import UUID

from sqlalchemy import select

from pace.adapters.db.business import require_account, require_current_snapshot
from pace.adapters.db.models import ConnectionRequest, Match


class BusinessHandlers:
    """注入 Email / Event 能力；没有假装成功的未配置通道。"""

    def __init__(self, sessions, email=None, events=None):
        self.sessions, self.email, self.events = sessions, email, events

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
                await self._snapshots(session, match)
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
                    await self._snapshots(session, match)
                except (AccountUnavailable, EntityNotReady):
                    raise PermanentDeliveryError() from None
            state = await self.events.deliver_subscription(payload)
        except Exception:
            await self._state(payload, "event_status", "failed")
            raise
        await self._state(payload, "event_status", state)

    async def _snapshots(self, session, match):
        """发送前双向检查联系快照仍是当前授权画像；完整替换后终止旧通知。"""
        request = await session.get(ConnectionRequest, match.request_id)
        await require_current_snapshot(session, request.snapshot_id)
        await require_current_snapshot(session, match.candidate_snapshot_id)

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
        """生产注册表仅两条通知任务；缺配置的具体方法明确失败。"""
        return {
            "email.send": self.send_email,
            "event.deliver": self.deliver_event,
        }
