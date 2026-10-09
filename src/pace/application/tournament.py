# 模块说明
# PACE 的通用四候选淘汰赛，不依赖数据库或模型 SDK。
#
# 请求者 Snapshot 在所有轮次保持不变；每组最多四个真实候选并始终带 no_match。
# 候选资格查询由未来 connect 用例负责，本模块只拒绝自身和重复 ID。
# 诊断概率仅属于当前组；上游失败或无效选择不能变成 No Match。

"""Four-way elimination with explicit No Match and reproducible diagnostics."""

import asyncio
import math
from collections.abc import Sequence

from pace.application.contracts import RequestContext
from pace.application.ports import ChoiceProvider
from pace.domain.errors import InvalidSelection
from pace.domain.models import ChoiceDecision, EntitySnapshot, RoundTrace, Selection

NO_MATCH = "no_match"


# 实现说明：resolve_decision
# 校验单组模型结果，并实施稳定且保守的并列规则。
#
# 必须包含全部真实候选与 no_match 的概率，值有限且在 0–1，合计近似 1。
# choice 必须是合法最大概率项；并列含 no_match 时淘汰本组，否则按稳定 ID 选最小者。
# 并列采用精确浮点相等，不额外引入未经校准的 confidence / 近似阈值。
def resolve_decision(decision: ChoiceDecision, candidate_ids: set[str]) -> str:
    # 校验范围仅限本组，禁止模型返回其他组或输入资料中的伪造 ID。
    allowed = candidate_ids | {NO_MATCH}
    probabilities = decision.probabilities
    # 这一组完整性检查失败应报错，不能补齐遗漏概率或猜一个 Winner。
    if (
        decision.choice not in allowed
        or set(probabilities) != allowed
        or any(not math.isfinite(v) or v < 0 or v > 1 for v in probabilities.values())
        or not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.001)
    ):
        raise InvalidSelection()
    # 模型 choice 必须属于最高概率集合，否则返回自相矛盾。
    maximum = max(probabilities.values())
    tied = {key for key, value in probabilities.items() if value == maximum}
    if decision.choice not in tied:
        raise InvalidSelection()
    return NO_MATCH if NO_MATCH in tied else min(tied)


# 实现说明：Tournament
# 用注入的 ChoiceProvider 编排选择，业务规则与 SDK 调用分离。
#
# 每次 select 自建 Semaphore；并发限制作用于本次淘汰赛，非跨请求全局限流。
class Tournament:
    # 实现说明：Tournament.__init__
    # 保存 Provider 与正整数并发上限。
    #
    # Provider 可为真实官方 SDK Adapter 或离线测试桩；这里不连接外部服务。
    def __init__(self, provider: ChoiceProvider, concurrency: int = 4):
        if concurrency < 1:
            raise ValueError("concurrency must be positive.")
        self.provider = provider
        self.concurrency = concurrency

    # 实现说明：Tournament.select
    # 返回最终候选 ID 或有效 No Match，以及按轮 / 组顺序排列的诊断。
    #
    # 先检查 ID，再稳定排序；同轮独立组有限并发，下一轮必须等待上一轮完成。
    # 即使只剩一个候选，也要与 no_match 作最后判断，不能自动视为匹配。
    # 任意组失败会取消同轮未完成调用，保留原始业务错误。
    async def select(
        self,
        requester: EntitySnapshot,
        request_text: str,
        candidates: Sequence[EntitySnapshot],
        context: RequestContext | None = None,
    ) -> Selection:
        if len({c.user_id for c in candidates}) != len(candidates):
            raise ValueError("Candidate IDs must be unique.")
        if any(c.user_id == requester.user_id for c in candidates):
            raise ValueError("Requester cannot be a candidate.")
        # 稳定 ID 顺序便于复现；分组敏感性仍需真实评测，不是效果保证。
        remaining = sorted(candidates, key=lambda c: str(c.user_id))
        traces: list[RoundTrace] = []
        round_number = 1
        # 每次 select 都有自己的并发配额，不会限制另一个 select 的总调用量。
        semaphore = asyncio.Semaphore(self.concurrency)
        while remaining:
            groups = [remaining[i : i + 4] for i in range(0, len(remaining), 4)]

            # 实现说明：Tournament.select.choose
            # 执行一个分组调用并生成 RoundTrace。
            #
            # round_id 用默认参数绑定当前轮，避免闭包后续读取已递增的 round_number。
            # Semaphore 只包围 Provider 调用；结果合法性与并列选择随后独立检查。
            async def choose(
                group_number: int, group: list[EntitySnapshot], round_id: int = round_number
            ):
                async with semaphore:
                    decision = await self.provider.choose(requester, request_text, group, context)
                winner = resolve_decision(decision, {str(c.user_id) for c in group})
                return RoundTrace(
                    round_id, group_number, tuple(str(c.user_id) for c in group), winner, decision
                )

            # 先创建同轮所有任务；Semaphore 再控制真正同时发往 Provider 的数量。
            pending = [asyncio.create_task(choose(i + 1, group)) for i, group in enumerate(groups)]
            try:
                round_traces = await asyncio.gather(*pending)
            finally:
                # Preserve the original error while cancelling outstanding provider calls.
                for task in pending:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            traces.extend(round_traces)
            # no_match 只消灭本组，其他组选出的候选继续；不跨组比较概率。
            winners = {trace.winner for trace in round_traces} - {NO_MATCH}
            remaining = [c for c in remaining if str(c.user_id) in winners]
            # 只剩一个分组时已经完成最终判断，无需再把同一 Winner 无限送回模型。
            if len(groups) == 1:
                return Selection(remaining[0].user_id if remaining else None, tuple(traces))
            round_number += 1
        return Selection(None, tuple(traces))
