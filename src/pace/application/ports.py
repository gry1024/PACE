# 模块说明
# 声明应用层需要的外部能力，不包含 SDK 或网络实现。
#
# 使用 Python Protocol 做结构类型约束：满足方法签名的真实 Adapter / 测试桩都能注入。
# 身份独立于 Tool 数据；选择独立于数据库；Ontology 和交付可分开实现、测试。
# Protocol 存在不等于对应能力已完成，当前多项业务 Port 仍未接线。

"""Dependency boundaries used by application services."""

from collections.abc import Sequence
from typing import Protocol

from pace.application.contracts import (
    ConnectInput,
    ConnectionMatched,
    ConnectResult,
    RequestContext,
    SourceFile,
    SyncEntityInput,
    SyncEntityResult,
)
from pace.domain.models import ChoiceDecision, EntitySnapshot, Principal


# 实现说明：IdentityVerifier
# 访问凭据到可信 Principal 的验证边界。
#
# 未来实现必须验证 Token 的 issuer、audience、有效期、scope 和账号绑定。
class IdentityVerifier(Protocol):
    # 实现说明：IdentityVerifier.verify
    # 校验 Bearer Token，成功才返回 Principal。
    #
    # 失败应抛安全业务错误，不能信任输入 Token 内未经验证的字段。
    async def verify(self, bearer_token: str) -> Principal: ...


# 实现说明：BusinessCommands
# 传输层调用的两项业务用例接口。
#
# 输入身份由 transport 决定，具体命令负责授权、幂等、持久化和外部调用。
class BusinessCommands(Protocol):
    # 实现说明：BusinessCommands.sync_entity
    # 同步明确授权的文件和长期 D / S 更新。
    #
    # 返回 accepted 只表示实际持久任务已接受，不表示 Ontology 生成完成。
    async def sync_entity(
        self, principal: Principal, data: SyncEntityInput
    ) -> SyncEntityResult: ...

    # 实现说明：BusinessCommands.connect
    # 根据独立即时请求查找连接。
    #
    # 成功结果必须与提交的 Request / Match / 通知任务一致；不得修改长期 D / S。
    async def connect(self, principal: Principal, data: ConnectInput) -> ConnectResult: ...


# 实现说明：ChoiceProvider
# 对单组候选进行结构化选择的外部能力。
#
# 分组、淘汰、并列规则属于 Tournament，不应藏在 SDK Adapter 内。
class ChoiceProvider(Protocol):
    # 实现说明：ChoiceProvider.choose
    # 用同一 Requester Snapshot 和请求上下文评价该组候选。
    #
    # 返回真实候选 ID 或 no_match，以及组内诊断；服务故障必须抛错。
    async def choose(
        self,
        requester: EntitySnapshot,
        request_text: str,
        candidates: Sequence[EntitySnapshot],
        context: RequestContext | None = None,
    ) -> ChoiceDecision: ...


# 实现说明：OntologyBuilder
# 从上传文本构建 / 更新 Ontology 的能力，当前只有接口。
#
# 不能替代 Host 去读取远端文件，也不能自动把即时请求改为长期需求。
class OntologyBuilder(Protocol):
    # 实现说明：OntologyBuilder.build
    # 接收明确上传的文件与可选旧 Snapshot，返回 Ontology 文本。
    #
    # 具体提取、合并、来源保留和版本切换需要后续 Adapter / 用例实现。
    async def build(self, files: Sequence[SourceFile], previous: EntitySnapshot | None) -> str: ...


# 实现说明：EventDelivery
# 向已验证订阅地址投递连接事件的能力，当前只有接口。
#
# 实际实现还需校验 callback、签名、到期、重试与幂等。
class EventDelivery(Protocol):
    # 实现说明：EventDelivery.deliver
    # 投递完整最小 Event 载荷，并报告实际通道状态。
    #
    # HTTP 接受不表示用户阅读，未配置不能返回成功。
    async def deliver(self, callback_url: str, event: ConnectionMatched) -> str: ...


# 实现说明：EmailDelivery
# 邮件交付边界，可由本地捕获或真实 SMTP Adapter 实现。
#
# 交付状态要区分 captured 和 provider_accepted。
class EmailDelivery(Protocol):
    # 实现说明：EmailDelivery.deliver
    # 使用稳定 delivery_id 投递指定邮件。
    #
    # 重试不得创造新业务连接；同键不同内容要检测冲突，返回真实状态。
    async def deliver(self, recipient: str, subject: str, body: str, delivery_id: str) -> str: ...
