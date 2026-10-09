# 模块说明
# 必要配置缺失时的明确失败实现。
#
# 配置完整时由 bootstrap 使用真实 OAuth / 持久用例，这些缺省实现不模拟成功。
# 本模块不使用内存数据模拟成功，不把演示结果当作生产连接。
# 后续替换这些实现时需完成授权、幂等、并发与事务验收。

"""Explicit unavailable boundaries when required infrastructure is not configured."""

from pace.application.contracts import (
    ConnectInput,
    ConnectResult,
    SyncEntityInput,
    SyncEntityResult,
)
from pace.domain.errors import FeatureUnavailable
from pace.domain.models import Principal


# 实现说明：UnconfiguredIdentity
# 拒绝把任意 Bearer Token 视为可信账号。
#
# 此类不是 OAuth 验证器；仅明确暴露当前缺少身份接线。
class UnconfiguredIdentity:
    # 实现说明：UnconfiguredIdentity.verify
    # 始终报告身份能力未接线。
    #
    # token 参数用于满足 Port 签名，但不能据此生成测试用户；错误不回显 Token。
    async def verify(self, bearer_token: str) -> Principal:
        raise FeatureUnavailable()


# 实现说明：UnconfiguredCommands
# 两项业务命令的未配置实现。
#
# 对外能发现契约，但不能声称已同步、生成 Ontology 或创建 Match。
class UnconfiguredCommands:
    # 实现说明：UnconfiguredCommands.sync_entity
    # 明确拒绝缺数据库配置的 Entity 更新。
    #
    # 不能先返回 accepted 再丢弃输入；真正实现需持久化来源、并发版本与任务。
    async def sync_entity(self, principal: Principal, data: SyncEntityInput) -> SyncEntityResult:
        raise FeatureUnavailable()

    # 实现说明：UnconfiguredCommands.connect
    # 明确拒绝缺数据库配置的连接用例。
    #
    # 有效 No Match 必须来自真实候选查询和选择，不能用来掩盖缺少接线。
    async def connect(self, principal: Principal, data: ConnectInput) -> ConnectResult:
        raise FeatureUnavailable()
