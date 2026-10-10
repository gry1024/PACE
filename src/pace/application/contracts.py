# 模块说明
# 两项业务 MCP Tool 与连接事件的正式数据契约。
#
# Pydantic 负责结构 / 字段校验，MCP 与 HTTP Schema 从同一模型生成，避免协议与用例漂移。
# 所有输入拒绝额外字段，可信身份单独传入；字段校验不能替代账号授权、乐观锁或幂等事务。
# 本模块不读远端文件、不调模型、不写数据库；accepted / matched 仍需真实用例产生。

"""Versioned business contracts. Identity is supplied by the transport, not tool input."""

import hashlib
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


# 实现说明：Contract
# 共享契约基类，extra=forbid 禁止悄悄接受未知字段。
#
# 特别是 user_id / email 等参数不能成为身份伪造通道。
class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# PA 提供完整画像，后端只校验结构与预算，不提炼或推断事实。
# O/D/S 必须全部提交；空文本 / 空列表表示明确清除，不使用增量合并。
# 初始持续授权覆盖连接前同步，实际可访问资料及工具确认仍由 PA 平台管理。
PROFILE_FORMAT = "pa-entity-v1"
MAX_PROFILE_BYTES = 4000


class SyncEntityInput(Contract):
    request_id: UUID
    ontology: str = Field(max_length=4000)
    demands: list[str] = Field(max_length=20)
    supplies: list[str] = Field(max_length=20)
    expected_entity_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_profile(self):
        """拒绝空白长期项和超预算完整画像；不裁剪或改写 PA 正文。"""
        for entries in (self.demands, self.supplies):
            if any(not entry.strip() for entry in entries):
                raise ValueError("Long-term entries cannot be blank.")
            if len(set(entries)) != len(entries):
                raise ValueError("Long-term entries must be unique.")
        if self.ontology and not self.ontology.strip():
            raise ValueError("ontology must be empty or nonblank.")
        if (
            sum(
                len(value.encode("utf-8"))
                for value in (self.ontology, *self.demands, *self.supplies)
            )
            > MAX_PROFILE_BYTES
        ):
            raise ValueError("O/D/S exceeds 4000 UTF-8 bytes.")
        return self


# 实现说明：RequestContext
# 当前请求的观察时间、IANA 时区和可选授权地点描述。
#
# 保留时间上下文，防止选择仅靠长期资料猜测“明天 / 晚上”的含义。
class RequestContext(Contract):
    observed_at: AwareDatetime
    timezone: str
    location_description: str | None = Field(default=None, max_length=2000)

    # 实现说明：RequestContext.valid_timezone
    # 要求时区可由标准库 ZoneInfo 识别。
    #
    # 同时处理不存在的时区和非法路径 / 名称；错误不把输入变成默认时区。
    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be an IANA timezone.") from exc
        return value


# 实现说明：ConnectInput
# 独立即时连接请求，没有长期更新或可伪造身份字段。
#
# Request 必须单独持久化，不能自动转为 Demand；context 与文本共同参与判断。
class ConnectInput(Contract):
    request_id: UUID
    entity_version: int = Field(ge=1)
    request_text: str = Field(min_length=1, max_length=10000)
    context: RequestContext

    # 实现说明：ConnectInput.nonblank
    # 拒绝全空白请求，但不修改原始非空文本。
    #
    # 保留用户真实表达，不在此处自动整理、截断或改写约束。
    @field_validator("request_text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request_text cannot be blank.")
        return value


# 同步在调用者事务内立即发布；changed=False 表示原样内容未新增版本。
# 相同 request_id 的重试仍返回原回执，不覆盖之后接受的版本。
class SyncEntityResult(Contract):
    status: Literal["accepted"]
    entity_version: int
    entity_status: Literal["ready"] = "ready"
    changed: bool


# 实现说明：CandidateResult
# 为此次连接公开的最小候选信息。
#
# email 当前只是字符串字段，不负责 Email 验证；真实联系地址必须来自已验证账号。
class CandidateResult(Contract):
    pace_user_id: UUID
    relevant_information: str
    email: str


# 共享可观察状态；后续各通道用例还需限定哪些状态转换合法。
DeliveryState = Literal[
    "queued", "not_subscribed", "captured", "accepted_by_receiver", "provider_accepted", "failed"
]


# 实现说明：NotificationState
# 分别报告 Event 和 Email 的实际状态。
#
# 不能用一个通道成功掩盖另一个失败，queued / captured 也不是用户收到或已读。
class NotificationState(Contract):
    event: DeliveryState
    email: DeliveryState


# 实现说明：ConnectResult
# 匹配与 No Match 共用的结果契约。
#
# 使用调用者同步回执中的 entity_version；连接后不再触发同步。
class ConnectResult(Contract):
    status: Literal["matched", "no_match"]
    request_id: UUID
    entity_version: int
    connection_id: UUID | None = None
    candidate: CandidateResult | None = None
    notification: NotificationState | None = None

    # 实现说明：ConnectResult.validate_outcome
    # 约束结果分支，避免 No Match 泄露联系方式或伪造通知。
    #
    # matched 必须同时含连接、候选、通道状态；no_match 三者必须全为空。
    # 此校验只验证对象形状，不证明事务已提交或通知任务真实存在。
    @model_validator(mode="after")
    def validate_outcome(self):
        values = (self.connection_id, self.candidate, self.notification)
        if self.status == "matched" and any(v is None for v in values):
            raise ValueError("A match requires connection, candidate and notification.")
        if self.status == "no_match" and any(v is not None for v in values):
            raise ValueError("No Match cannot disclose a candidate or enqueue notifications.")
        return self


# 实现说明：ConnectionMatched
# 对被匹配方投递的完整最小事件。
#
# 稳定 event_id 用于重试去重，载荷直接包含申请方相关信息与 Email，不需要第三个业务 Tool。
class ConnectionMatched(Contract):
    """Full minimal event payload; never requires a third business tool."""

    event_id: UUID
    type: Literal["connection.matched"] = "connection.matched"
    occurred_at: AwareDatetime
    connection_id: UUID
    request_summary: str
    requester: CandidateResult


# 实现说明：payload_hash
# 生成已经通过契约校验的规范化载荷 SHA-256。
#
# JSON 按键排序且无额外空格，使字段传入顺序不改变 hash；UUID / 时间按 JSON 模式序列化。
# 这是幂等比较工具，不能替代身份+请求键的持久化重放与并发控制。
def payload_hash(payload: Contract) -> str:
    """Canonical validated input hash for future persistent idempotency handling."""
    import json

    body = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
