# 模块说明
# 业务尚未接线时的明确失败实现。
#
# Port、契约、数据库表和选择规则已经存在，但账号 / Entity / Match 用例仍待实现。
# 本模块不使用内存数据模拟成功，不把演示结果当作生产连接。
# 后续替换这些实现时需完成授权、幂等、并发与事务验收。

"""Explicit unwired boundaries until account and entity transactions are implemented."""

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
    # 明确拒绝尚未实现的 Entity 更新。
    #
    # 不能先返回 accepted 再丢弃输入；真正实现需持久化来源、并发版本与任务。
    async def sync_entity(self, principal: Principal, data: SyncEntityInput) -> SyncEntityResult:
        raise FeatureUnavailable()

    # 实现说明：UnconfiguredCommands.connect
    # 明确拒绝尚未实现的连接用例。
    #
    # 有效 No Match 必须来自真实候选查询和选择，不能用来掩盖缺少接线。
    async def connect(self, principal: Principal, data: ConnectInput) -> ConnectResult:
        raise FeatureUnavailable()
