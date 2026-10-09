# 模块说明
# 独立 Worker 进程与任务 Handler 生命周期。
#
# Worker 执行已注册 Ontology / Email / Event Handler，未知类型明确失败。
# 任务执行与续租并发，租约丢失终止当前路径，异常只记录稳定安全code。
# run_once 返回是否曾领取任务，不是业务副作用成功标志。

"""Independent durable worker; handlers are wired here as capabilities are implemented."""

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from pace.adapters.db.jobs import JobQueue
from pace.adapters.db.models import Job
from pace.bootstrap import build_container
from pace.config import Settings
from pace.domain.errors import PaceError, PermanentDeliveryError

# Handler 只负责具体副作用，任务领取 / 重试 / 租约由 Worker / Queue 管理。
JobHandler = Callable[[dict], Awaitable[None]]


# 实现说明：Worker
# 把 JobQueue 和具体异步 Handler 注册表组合起来。
#
# Handler 接收结构化 payload，必须为至少一次执行设计稳定幂等行为。
class Worker:
    # 实现说明：Worker.__init__
    # 注入队列与 kind→Handler 映射。
    #
    # 类本身不读取环境、不建立数据库或自动注册模拟 Handler。
    def __init__(self, queue: JobQueue, handlers: dict[str, JobHandler]):
        self.queue = queue
        self.handlers = handlers

    # 实现说明：Worker._heartbeat
    # 每三分之一租约周期尝试续租。
    #
    # renew=False 表示已经失去任务占有权，抛错使执行路径停止；不能盲目继续投递。
    async def _heartbeat(self, job: Job):
        while True:
            await asyncio.sleep(self.queue.lease_seconds / 3)
            if not await self.queue.renew(job):
                raise RuntimeError("job_lease_lost")

    # 实现说明：Worker.run_once
    # 尝试领取并处理一项任务，管理执行 / 心跳的完整退出。
    #
    # 没有任务返回False；未知kind记录handler_not_configured并有限重试。
    # 已注册Handler和心跳并发等待，续租先失败则中止执行；正常结束尝试DB确认。
    # 未知异常只记录handler_failed；finally取消并等待剩余任务，避免后台悬挂。
    # 返回True只表示领取过，complete返回False不能被解释为业务已完成。
    async def run_once(self) -> bool:
        job = await self.queue.claim()
        if job is None:
            return False
        handler = self.handlers.get(job.kind)
        if handler is None:
            await self.queue.fail(job, "handler_not_configured")
            return True
        # 先分开创建执行与心跳，确保长任务不会依靠无限租约。
        heartbeat = asyncio.create_task(self._heartbeat(job))
        execution = asyncio.create_task(handler(job.payload))
        try:
            done, _ = await asyncio.wait(
                [heartbeat, execution], return_when=asyncio.FIRST_COMPLETED
            )
            # 如果续租先失败，await 会抛错并走取消流程，避免失去租约后继续执行。
            if heartbeat in done:
                await heartbeat  # Lease loss aborts execution; no stale completion.
            await execution
            # 此处可能返回 False；run_once 不把布尔返回解释成对外成功状态。
            await self.queue.complete(job)
        except Exception as exc:
            # Raw exceptions may contain private payloads or credentials.
            await self.queue.fail(
                job,
                exc.code if isinstance(exc, PaceError) else "handler_failed",
                **({"terminal": True} if isinstance(exc, PermanentDeliveryError) else {}),
            )
        finally:
            for task in (heartbeat, execution):
                if not task.done():
                    task.cancel()
            await asyncio.gather(heartbeat, execution, return_exceptions=True)
        return True


# 实现说明：run
# 装配独立 Worker 的数据库并选择单次或持续轮询。
#
# 通过 bootstrap 装配持久 Handler；capture 为默认本地通知通道。
# 空队列按配置sleep，退出时在finally关闭Engine。
async def run(once: bool):
    settings = Settings()
    container = build_container(settings)
    if container.database is None:
        raise ValueError("DATABASE_URL is required for the worker.")
    queue = JobQueue(container.database.sessions, lease_seconds=settings.worker_lease_seconds)
    worker = Worker(queue, handlers=container.handlers.registry())
    try:
        if once:
            await worker.run_once()
        else:
            while True:
                if not await worker.run_once():
                    await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        await container.close()


# 实现说明：main
# 解析 --once 并运行异步Worker。
#
# Ctrl+C 正常停止；未确认任务的租约在到期后可由下一进程恢复。
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Attempt one claim, then exit.")
    args = parser.parse_args()
    with suppress(KeyboardInterrupt):
        asyncio.run(run(args.once))


if __name__ == "__main__":
    main()
