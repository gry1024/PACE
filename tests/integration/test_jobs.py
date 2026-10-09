# 模块说明
# 通过真实迁移与PostgreSQL验证任务队列的可靠性边界。
#
# 覆盖去重 /载荷冲突 /事务回滚、并发唯一领取、过期接管和旧租约拒绝。
# 所有Handler /payload为合成数据，不发送真实邮件或事件。
# 这些测试不能替代外部投递恰好一次或长任务持续heartbeat验收。

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from pace.adapters.db.jobs import JobQueue, enqueue
from pace.adapters.db.models import Job
from pace.domain.errors import IdempotencyConflict
from pace.interfaces.worker import Worker


# 实现说明：test_enqueue_commits_deduplicates_and_rolls_back_atomically
# 证明同键同载荷返回同ID，同键不同载荷冲突，事务异常不留下任务。
#
# 最后只应有首次已提交任务，防止enqueue私自commit破坏业务原子性。
async def test_enqueue_commits_deduplicates_and_rolls_back_atomically(sessions):
    async with sessions.begin() as session:
        first = await enqueue(session, "synthetic", "same", {"value": 1})
    async with sessions.begin() as session:
        assert await enqueue(session, "synthetic", "same", {"value": 1}) == first
    with pytest.raises(IdempotencyConflict):
        async with sessions.begin() as session:
            await enqueue(session, "synthetic", "same", {"value": 2})
    with pytest.raises(RuntimeError):
        async with sessions.begin() as session:
            await enqueue(session, "synthetic", "rollback", {})
            raise RuntimeError("synthetic rollback")
    async with sessions() as session:
        assert len((await session.scalars(select(Job))).all()) == 1


# 实现说明：test_concurrent_claims_do_not_share_job
# 四项任务由五个并发领取者竞争，恰有四个不同ID。
#
# 多出的领取应为空，不能重复取得同一任务，验证SKIP LOCKED实际数据库行为。
async def test_concurrent_claims_do_not_share_job(sessions):
    async with sessions.begin() as session:
        for i in range(4):
            await enqueue(session, "synthetic", str(i), {})
    queue = JobQueue(sessions)
    # 同时启动多个领取事务，不能用串行调用伪装并发验收。
    claimed = await asyncio.gather(*(queue.claim() for _ in range(5)))
    ids = [job.id for job in claimed if job is not None]
    assert len(ids) == len(set(ids)) == 4


# 实现说明：test_expired_lease_is_recovered_and_stale_worker_cannot_ack
# 模拟Worker失联：直接把租约置过去，再由新Queue接管同ID。
#
# 新的lease_id与attempts必须变化；旧持有者不能续租或完成，新持有者可以。
async def test_expired_lease_is_recovered_and_stale_worker_cannot_ack(sessions):
    async with sessions.begin() as session:
        await enqueue(session, "synthetic", "recover", {})
    queue = JobQueue(sessions)
    old = await queue.claim()
    async with sessions.begin() as session:
        await session.execute(
            update(Job)
            .where(Job.id == old.id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    # 重新构造Queue只共享持久数据库，模拟进程重启后的状态恢复。
    recovered = await JobQueue(sessions).claim()
    assert recovered.id == old.id
    # 同一任务ID不等于同一占有权，旧进程必须被新租约挡住。
    assert recovered.lease_id != old.lease_id
    assert recovered.attempts == 2
    assert await queue.renew(old) is False
    assert await queue.renew(recovered) is True
    assert await queue.complete(old) is False
    assert await queue.complete(recovered) is True


# 实现说明：test_exhausted_lease_moves_to_failed
# 单次尝试任务租约过期后必须终止，不永久留running或再次执行。
#
# 验证lease_exhausted错误码与failed持久状态。
async def test_exhausted_lease_moves_to_failed(sessions):
    async with sessions.begin() as session:
        await enqueue(session, "synthetic", "exhaust", {}, max_attempts=1)
    queue = JobQueue(sessions)
    job = await queue.claim()
    async with sessions.begin() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await queue.claim() is None
    async with sessions() as session:
        failed = await session.get(Job, job.id)
        assert failed.status == "failed"
        assert failed.error_code == "lease_exhausted"


# 实现说明：test_worker_completes_registered_handler_and_retries_unknown_kind
# 合成Handler正常执行后任务完成；未注册类型明确失败。
#
# 未知任务max_attempts=1使本用例立即failed，检查code而非虚假通知成功。
# 最后空队列run_once=False，只表达未领取到任务。
async def test_worker_completes_registered_handler_and_retries_unknown_kind(sessions):
    called = []

    # 实现说明：test_worker_completes_registered_handler_and_retries_unknown_kind.handler
    # 记录收到的合成载荷，代替真实外部副作用。
    #
    # 列表断言证明Handler被调用，但不冒充邮件或Ontology成功。
    async def handler(payload):
        called.append(payload)

    async with sessions.begin() as session:
        first = await enqueue(session, "synthetic", "handled", {"test": True})
    worker = Worker(JobQueue(sessions), {"synthetic": handler})
    assert await worker.run_once()
    async with sessions() as session:
        assert (await session.get(Job, first)).status == "completed"
    assert called == [{"test": True}]
    async with sessions.begin() as session:
        unknown = await enqueue(session, "unwired", "unknown", {}, max_attempts=1)
    assert await worker.run_once()
    async with sessions() as session:
        job = await session.get(Job, unknown)
        assert job.status == "failed"
        assert job.error_code == "handler_not_configured"
    assert await worker.run_once() is False
