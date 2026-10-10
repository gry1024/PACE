# 模块说明：持久 connect 编排；存储通过注入的事务对象访问，选择通过 ChoiceProvider。
# Request 独立于 D/S；Provider 错误写成 failed，而不是 No Match。
"""Business commands with persisted idempotency and explicit selection boundaries."""

import asyncio
from typing import Protocol

from pace.application.contracts import ConnectInput, SyncEntityInput, payload_hash
from pace.application.tournament import Tournament
from pace.domain.errors import PaceError, SelectionLimit, VersionConflict
from pace.domain.models import Principal


class BusinessStore(Protocol):
    """事务 Port；具体 SQL、行锁和映射封装在数据库 Adapter。"""

    def connection(self, principal, data): ...

    async def synchronize(self, principal, data): ...


class PersistentCommands:
    """仅持有 Port 与预算；不读取 Key、不创建 SDK、不解析传输协议。"""

    def __init__(
        self, store: BusinessStore, tournament: Tournament, timeout=60, max_candidates=128
    ):
        self.store = store
        self.tournament = tournament
        self.timeout = timeout
        self.max_candidates = max_candidates

    async def sync_entity(self, principal: Principal, data: SyncEntityInput):
        """同步由数据库原子发布 / 回执边界实现，不调用模型或入队构建。"""
        return await self.store.synchronize(principal, data)

    async def connect(self, principal: Principal, data: ConnectInput):
        """同键串行执行；成功重放零模型调用，失败允许同载荷重试。"""
        failure = None
        result = None
        async with self.store.connection(principal, data) as unit:
            await unit.require_account(principal.user_id)
            old = await unit.replay(payload_hash(data))
            if old is not None:
                return old
            requester = await unit.requester()
            if requester[1].version != data.entity_version:
                raise VersionConflict()
            candidates = await unit.candidates(self.max_candidates + 1)
            await unit.begin_request(requester, payload_hash(data))
            try:
                if len(candidates) > self.max_candidates:
                    raise SelectionLimit()
                async with asyncio.timeout(self.timeout):
                    selection = await self.tournament.select(
                        requester[1], data.request_text, [c[1] for c in candidates], data.context
                    )
                result = await unit.finish(requester, candidates, selection)
            except TimeoutError:
                failure = SelectionLimit()
                await unit.mark_failed(failure.code)
            except PaceError as exc:
                failure = exc
                await unit.mark_failed(exc.code)
        # 必须等事务提交才返回 / 抛业务错误，避免 failed 状态随着 raise 回滚。
        if failure is not None:
            raise failure
        return result
