# 模块说明
# 基于 PostgreSQL 事务、行锁与租约的可靠任务队列。
#
# 入队不自行提交，让业务数据与通知 / Build 任务可以原子提交。
# 领取使用 SKIP LOCKED，持有者更新使用 lease_id 与截止时间，支持并发和崩溃恢复。
# 队列保证至少一次执行；外部副作用发生后确认前崩溃仍会重做，Handler 必须幂等。

"""Transactional enqueue and leased SKIP LOCKED work claims."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pace.adapters.db.models import Job
from pace.domain.errors import IdempotencyConflict


# 实现说明：enqueue
# 在调用者 Session / 事务内插入或查找稳定键的任务。
#
# ON CONFLICT DO NOTHING RETURNING 避免并发重复创建；相同 kind / payload 返回旧 ID。
# 同键不同内容报 idempotency_conflict，不覆写状态或重置 attempts。
# max_attempts 变化当前不参与冲突判定；本函数不 commit，也不执行 Handler。
async def enqueue(
    session: AsyncSession,
    kind: str,
    dedupe_key: str,
    payload: dict[str, Any],
    max_attempts: int = 3,
) -> UUID:
    """Caller owns the transaction: business writes and enqueue commit together."""
    # 插入冲突由数据库唯一键解决，不能先查后插造成竞争窗口。
    result = await session.execute(
        insert(Job)
        .values(kind=kind, dedupe_key=dedupe_key, payload=payload, max_attempts=max_attempts)
        .on_conflict_do_nothing(index_elements=[Job.dedupe_key])
        .returning(Job.id)
    )
    job_id = result.scalar_one_or_none()
    if job_id is not None:
        return job_id
    previous = (await session.scalars(select(Job).where(Job.dedupe_key == dedupe_key))).one()
    if previous.kind != kind or previous.payload != payload:
        raise IdempotencyConflict()
    return previous.id


# 实现说明：JobQueue
# 管理持久任务领取与租约状态，不理解载荷的具体业务内容。
#
# 各进程可独立创建队列对象，共享 PostgreSQL 数据而非内存队列。
class JobQueue:
    # 实现说明：JobQueue.__init__
    # 保存 Session 工厂与最短三秒的租约期限。
    #
    # 租约必须允许心跳续期；测试可使用独立数据库 Session 工厂。
    def __init__(self, sessions, lease_seconds: int = 300):
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be at least 3.")
        self.sessions = sessions
        self.lease_seconds = lease_seconds

    # 实现说明：JobQueue.claim
    # 在一个事务中清理耗尽租约并原子领取一条任务。
    #
    # 只选到期 queued 或租约过期 running，且 attempts 尚未耗尽。
    # SKIP LOCKED 让并发 Worker 跳过被其他事务锁住的候选。
    # UPDATE RETURNING 同时置 running、增加 attempts、赋新租约，离开上下文才提交。
    async def claim(self) -> Job | None:
        async with self.sessions.begin() as session:
            await session.execute(
                update(Job)
                .where(
                    Job.status == "running",
                    Job.lease_until <= func.now(),
                    Job.attempts >= Job.max_attempts,
                )
                .values(
                    status="failed", error_code="lease_exhausted", lease_id=None, lease_until=None
                )
            )
            # 子查询在同一事务锁定一条可领取记录；多 Worker 不等待同一条锁。
            eligible = (
                select(Job.id)
                .where(
                    Job.attempts < Job.max_attempts,
                    or_(
                        and_(Job.status == "queued", Job.available_at <= func.now()),
                        and_(Job.status == "running", Job.lease_until <= func.now()),
                    ),
                )
                .order_by(Job.available_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
                .scalar_subquery()
            )
            return (
                await session.scalars(
                    update(Job)
                    # 与选择子查询组成单条 UPDATE，避免查出任务后被其他进程同时领取。
                    .where(Job.id == eligible)
                    .values(
                        status="running",
                        attempts=Job.attempts + 1,
                        lease_id=uuid4(),
                        lease_until=func.now() + timedelta(seconds=self.lease_seconds),
                    )
                    .returning(Job)
                )
            ).one_or_none()

    # 实现说明：JobQueue.renew
    # 仅为仍持有有效租约的 Worker 延长截止时间。
    #
    # 返回 False 表示租约失效 / 已被接管，调用者必须停止而非继续副作用。
    async def renew(self, job: Job) -> bool:
        return await self._update(
            job, lease_until=func.now() + timedelta(seconds=self.lease_seconds)
        )

    # 实现说明：JobQueue.complete
    # 在有效租约下记录完成时间并清除租约。
    #
    # 返回值是确认是否实际成功；不能把“Handler已返回”当作DB已确认。
    async def complete(self, job: Job) -> bool:
        return await self._update(
            job, status="completed", completed_at=func.now(), lease_id=None, lease_until=None
        )

    # 实现说明：JobQueue.fail
    # 记录安全错误并决定有限重试或终止。
    #
    # 退避最多300秒；有剩余尝试时queued，耗尽时failed。
    # 错误码截到列长度，原始异常 / 邮件正文 / Key 不存这里。
    async def fail(self, job: Job, error_code: str) -> bool:
        # 每次领取才增加 attempts；失败根据当前计数计算有上限退避。
        delay = min(300, 2 ** min(job.attempts, 8))
        return await self._update(
            job,
            status="failed" if job.attempts >= job.max_attempts else "queued",
            available_at=datetime.now(UTC) + timedelta(seconds=delay),
            error_code=error_code[:100],
            lease_id=None,
            lease_until=None,
        )

    # 实现说明：JobQueue._update
    # 所有持有者状态更新共用的条件写入。
    #
    # 同时匹配任务 ID、running、lease UUID 和未过期，防止旧进程污染接管后的状态。
    # rowcount==1 才表示当前持有者成功更新，不无条件返回成功。
    async def _update(self, job: Job, **values) -> bool:
        async with self.sessions.begin() as session:
            # 更新条件包含有效租约；即使任务 ID相同，也不能由旧持有者确认。
            result = await session.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.status == "running",
                    Job.lease_id == job.lease_id,
                    Job.lease_until > func.now(),
                )
                .values(**values)
            )
            return result.rowcount == 1
