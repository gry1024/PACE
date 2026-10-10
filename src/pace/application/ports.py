# 模块说明
# 声明应用层需要的外部能力，不包含 SDK 或网络实现。
#
# 使用 Python Protocol 做结构类型约束：满足方法签名的真实 Adapter / 测试桩都能注入。
# 身份独立于 Tool 数据；选择独立于数据库；PA 直接提交画像，交付通过独立 Port。
# Protocol 存在不等于外部配置可用，具体实现由 bootstrap 选择。

"""Dependency boundaries used by application services."""

from collections.abc import Sequence
from typing import Protocol

from pace.application.contracts import (
    ConnectInput,
    ConnectResult,
    RequestContext,
    SyncEntityInput,
    SyncEntityResult,
)
from pace.domain.models import ChoiceDecision, EntitySnapshot, Principal


# 实现说明：IdentityVerifier
# 访问凭据到可信 Principal 的验证边界。
#
# OAuth 实现验证 PACE opaque Token 的资源、有效期、scope 和已验证 Gmail 账号绑定。
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
    # 原样发布 PA 提供的完整 O / D / S 快照。
    #
    # 返回 accepted / ready 表示快照已提交，立即可匹配，无后台构建任务。
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


# 实现说明：EventDelivery
# 向持久已验证订阅投递连接事件的能力，调用前再次校验权限与到期。
#
# Event Adapter 校验 callback、签名、到期与撤销，Queue负责有限重试。
class EventDelivery(Protocol):
    # 实现说明：EventDelivery.deliver_subscription
    # 投递完整最小 Event 载荷，并报告实际通道状态。
    #
    # HTTP 接受不表示用户阅读，未配置不能返回成功。
    async def deliver_subscription(self, payload: dict) -> str: ...


# 实现说明：EmailDelivery
# 邮件交付边界，可由本地捕获或系统 Gmail Adapter 实现。
#
# 交付状态要区分 captured 和 provider_accepted。
class EmailDelivery(Protocol):
    # 实现说明：EmailDelivery.deliver
    # 使用稳定 delivery_id 投递指定邮件。
    #
    # 重试不得创造新业务连接；同键不同内容要检测冲突，返回真实状态。
    async def deliver(self, recipient: str, subject: str, body: str, delivery_id: str) -> str: ...
