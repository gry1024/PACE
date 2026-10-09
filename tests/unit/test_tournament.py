# 模块说明
# 不调用模型的Tournament业务规则测试。
#
# Provider桩控制组选结果，以隔离分组 /淘汰 /并列 /错误取消行为。
# 固定伪概率只用于编排断言，不能宣称真实Jev效果。

import asyncio
from uuid import UUID

import pytest

from pace.application.tournament import Tournament, resolve_decision
from pace.domain.errors import InvalidSelection, ProviderUnavailable
from pace.domain.models import ChoiceDecision, EntitySnapshot


# 实现说明：snapshot
# 用整数UUID构造稳定且易读的合成Snapshot。
#
# 方便断言候选排序、分组与自身排除，不绑定任何真实账号。
def snapshot(number):
    return EntitySnapshot(UUID(int=number), 1, f"Synthetic candidate {number}")


# 实现说明：FirstProvider
# 默认选该组首候选，可指定某些组首ID触发no_match。
#
# 记录每次调用的候选整数ID以检查轮数和尾组。
class FirstProvider:
    # 实现说明：FirstProvider.__init__
    # 记录调用列表和预设No Match组。
    #
    # 集合化配置避免重复声明影响测试；没有网络副作用。
    def __init__(self, no_match_groups=()):
        self.calls = []
        self.no_match_groups = set(no_match_groups)

    # 实现说明：FirstProvider.choose
    # 按预设产生合法组内选择与一位概率。
    #
    # 维持ChoiceProvider签名；context接受但不推理，效果不在该桩测试范围。
    async def choose(self, requester, request_text, candidates, context=None):
        self.calls.append(tuple(c.user_id.int for c in candidates))
        keys = [str(c.user_id) for c in candidates] + ["no_match"]
        winner = "no_match" if candidates[0].user_id.int in self.no_match_groups else keys[0]
        return ChoiceDecision(winner, {k: float(k == winner) for k in keys}, "fake")


# 实现说明：test_rounds_tail_groups_and_single_candidate_are_evaluated
# 参数化0 /1 /4 /5 /16 /17，固定预期调用数与最终候选。
#
# 倒序输入迫使实现真正做稳定排序；每组1–4断言验证尾组不补伪候选。
@pytest.mark.parametrize(("count", "calls"), [(0, 0), (1, 1), (4, 1), (5, 3), (16, 5), (17, 8)])
async def test_rounds_tail_groups_and_single_candidate_are_evaluated(count, calls):
    provider = FirstProvider()
    result = await Tournament(provider).select(
        snapshot(100), "Synthetic request", [snapshot(i) for i in range(count, 0, -1)]
    )
    assert result.candidate_id == (UUID(int=1) if count else None)
    assert len(provider.calls) == calls
    assert all(1 <= len(group) <= 4 for group in provider.calls)
    assert len(result.traces) == calls


# 实现说明：test_no_match_eliminates_only_its_group
# 第一组选no_match时，另一组Winner仍可继续。
#
# 防止把局部No Match误当整个候选池立刻失败。
async def test_no_match_eliminates_only_its_group():
    provider = FirstProvider(no_match_groups={1})
    result = await Tournament(provider).select(
        snapshot(100), "request", [snapshot(i) for i in range(1, 6)]
    )
    assert result.candidate_id == UUID(int=5)


# 实现说明：test_all_groups_no_match
# 所有组淘汰后返回candidate_id=None。
#
# 没有可胜出的候选时不创造默认Winner。
async def test_all_groups_no_match():
    result = await Tournament(FirstProvider({1, 5})).select(
        snapshot(100), "request", [snapshot(i) for i in range(1, 6)]
    )
    assert result.candidate_id is None


# 实现说明：test_tie_prefers_no_match_then_stable_candidate_id
# 固定两种并列：含no_match优先淘汰，候选间并列取稳定最小ID。
#
# 不按Provider恰好返回的choice或输入顺序决定。
def test_tie_prefers_no_match_then_stable_candidate_id():
    assert (
        resolve_decision(ChoiceDecision("a", {"a": 0.5, "no_match": 0.5}, "fake"), {"a"})
        == "no_match"
    )
    assert (
        resolve_decision(
            ChoiceDecision("b", {"a": 0.5, "b": 0.5, "no_match": 0}, "fake"), {"a", "b"}
        )
        == "a"
    )


# 实现说明：test_invalid_probability_distribution_fails
# 参数化NaN、总和错误、缺键和注入额外键，均须InvalidSelection。
#
# 不能修补模型概率然后声称有效No Match。
@pytest.mark.parametrize(
    "probabilities",
    [
        {"a": float("nan"), "no_match": 1},
        {"a": 0.6, "no_match": 0.6},
        {"a": 1},
        {"a": 1, "no_match": 0, "injected": 0},
    ],
)
def test_invalid_probability_distribution_fails(probabilities):
    with pytest.raises(InvalidSelection):
        resolve_decision(ChoiceDecision("a", probabilities, "fake"), {"a"})


# 实现说明：test_provider_error_propagates_and_cancels_other_groups
# 一组上游失败，另一组永久等待，要求错误传播且等待任务被取消。
#
# cancelled事件在finally设置，证明不是仅忽略兄弟任务。
async def test_provider_error_propagates_and_cancels_other_groups():
    cancelled = asyncio.Event()

    # 实现说明：test_provider_error_propagates_and_cancels_other_groups.FailingProvider
    # 制造并行组的失败 /悬挂组合，专门检查取消语义。
    class FailingProvider:
        # 实现说明：test_provider_error_propagates_and_cancels_other_groups.FailingProvider.choose
        # 首组先让出执行权再抛ProviderUnavailable，确保另组已启动。
        #
        # 另一组等待不会自行结束的Event，在被取消时finally记录证据。
        async def choose(self, requester, request_text, candidates, context=None):
            if candidates[0].user_id.int == 1:
                await asyncio.sleep(0)
                raise ProviderUnavailable()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    with pytest.raises(ProviderUnavailable):
        await Tournament(FailingProvider()).select(
            snapshot(100), "request", [snapshot(i) for i in range(1, 6)]
        )
    assert cancelled.is_set()


# 实现说明：test_self_and_duplicate_candidates_are_rejected
# 自身或重复ID必须在Provider调用前被拒绝。
#
# calls为空证明没有为非法候选浪费模型请求。
async def test_self_and_duplicate_candidates_are_rejected():
    provider = FirstProvider()
    for pool in ([snapshot(100)], [snapshot(1), snapshot(1)]):
        with pytest.raises(ValueError):
            await Tournament(provider).select(snapshot(100), "request", pool)
    assert provider.calls == []
