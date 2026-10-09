# 模块说明
# 离线验证官方SDK Adapter的形状转换与预算检查。
#
# 用SDKStub替换Client构造，仍调用真实JevChoiceProvider代码，不发网络请求。
# 验证时间上下文、UUID序列化、no_match criterion、关闭Client与调用前预算错误。

from types import SimpleNamespace
from uuid import UUID

import pytest

from pace.adapters.providers.jev import JevChoiceProvider
from pace.application.contracts import RequestContext
from pace.domain.errors import InputTooLarge
from pace.domain.models import EntitySnapshot


# 实现说明：SDKStub
# 模拟官方SDK异步方法的最小可观察桩。
#
# 只服务Adapter边界测试，不能作模型选择质量证据。
class SDKStub:
    # 实现说明：SDKStub.__init__
    # 初始化调用输入与关闭标记，便于断言Adapter实际传入什么。
    #
    # 不保存真实Key或建立任何连接。
    def __init__(self):
        self.state = None
        self.questions = None
        self.closed = False

    # 实现说明：SDKStub.system_one
    # 记录state /questions并返回符合Adapter访问方式的合成响应。
    #
    # 选择第一个criteria、生成合法一位概率，保持model /usage字段形状。
    async def system_one(self, *, state, questions):
        self.state, self.questions = state, questions
        keys = list(questions["match"].criteria)
        return SimpleNamespace(
            choices={
                "match": SimpleNamespace(
                    choice=keys[0],
                    probabilities={key: float(key == keys[0]) for key in keys},
                    confidence=1.0,
                )
            },
            model="synthetic-sdk",
            usage=None,
        )

    # 实现说明：SDKStub.aclose
    # 把关闭动作变为可断言的标记。
    #
    # 验证生命周期确实调用官方异步关闭方法，而非仅释放局部引用。
    async def aclose(self):
        self.closed = True


# 实现说明：test_adapter_preserves_context_and_uses_real_sdk_contract
# 检查Adapter传递IANA时区、字符串UUID与no_match，并映射返回选择。
#
# 最后显式close并断言SDK关闭；不调用真实服务。
async def test_adapter_preserves_context_and_uses_real_sdk_contract(monkeypatch):
    sdk = SDKStub()
    monkeypatch.setattr("pace.adapters.providers.jev.AsyncTypeSafeClient", lambda **kwargs: sdk)
    provider = JevChoiceProvider("synthetic-key", "synthetic-model")
    context = RequestContext(observed_at="2026-10-07T12:00:00Z", timezone="Asia/Shanghai")
    result = await provider.choose(
        EntitySnapshot(UUID(int=100), 1, "requester"),
        "request",
        [EntitySnapshot(UUID(int=1), 1, "candidate")],
        context,
    )
    assert sdk.state["request"]["context"]["timezone"] == "Asia/Shanghai"
    assert sdk.state["requester"]["user_id"] == str(UUID(int=100))
    assert "no_match" in sdk.questions["match"].criteria
    assert result.choice == str(UUID(int=1))
    await provider.close()
    assert sdk.closed


# 实现说明：test_budget_error_occurs_before_provider_call
# 用极小预算迫使Adapter在SDK调用前报InputTooLarge。
#
# state仍为None证明没有请求发出，防止先产生用量再校验输入。
async def test_budget_error_occurs_before_provider_call(monkeypatch):
    sdk = SDKStub()
    monkeypatch.setattr("pace.adapters.providers.jev.AsyncTypeSafeClient", lambda **kwargs: sdk)
    provider = JevChoiceProvider("synthetic", "synthetic", input_bytes=10)
    with pytest.raises(InputTooLarge):
        await provider.choose(EntitySnapshot(UUID(int=100), 1, "facts"), "request", [])
    assert sdk.state is None
