# 模块说明
# 两项业务 MCP Tool 与连接事件的正式数据契约。
#
# Pydantic 负责结构 / 字段校验，MCP 与 HTTP Schema 从同一模型生成，避免协议与用例漂移。
# 所有输入拒绝额外字段，可信身份单独传入；字段校验不能替代账号授权、乐观锁或幂等事务。
# 本模块不读远端文件、不调模型、不写数据库；accepted / matched 仍需真实用例产生。

"""Versioned business contracts. Identity is supplied by the transport, not tool input."""

import hashlib
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


# 实现说明：Contract
# 共享契约基类，extra=forbid 禁止悄悄接受未知字段。
#
# 特别是 user_id / email 等参数不能成为身份伪造通道。
class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# 实现说明：SourceFile
# Host 明确授权并实际读取后的文本与来源。
#
# source_id 是稳定来源键，content_hash 对应原样 UTF-8 文本，observed_at 需有时区。
# 这里只校验声明的一致性，不证明 Host 真的获得权限或文件可信。
class SourceFile(Contract):
    source_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=255)
    text: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: AwareDatetime

    # 实现说明：SourceFile.validate_content
    # 完成文件类型、大小与内容指纹校验。
    #
    # 哈希基于未裁剪、未规范化的 UTF-8 原文；避免服务器与 Host 对不同内容建立相同来源引用。
    # 单文件上限 1 MiB，限制的是字节而不是字符数量；中文编码需要计入。
    @model_validator(mode="after")
    def validate_content(self):
        if not self.name.lower().endswith((".txt", ".md")):
            raise ValueError("Only TXT and Markdown are supported.")
        if len(self.text.encode("utf-8")) > 1024 * 1024:
            raise ValueError("File exceeds 1 MiB.")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.content_hash:
            raise ValueError("content_hash must be the SHA-256 of the UTF-8 text.")
        return self


# 实现说明：UpsertEntry
# 明确新增或更新一条长期 Demand / Supply。
#
# 稳定 entry_id 支持后续更新；不能由即时 Request 隐式构造此对象。
class UpsertEntry(Contract):
    operation: Literal["upsert"]
    entry_id: UUID
    text: str = Field(min_length=1, max_length=10000)


# 实现说明：RemoveEntry
# 明确撤销某条长期意图，仅需要稳定 entry_id。
#
# 没有 text 字段，避免把撤销操作与更新语义混在一起。
class RemoveEntry(Contract):
    operation: Literal["remove"]
    entry_id: UUID


# 按 operation 区分 upsert / remove，生成明确的联合 Schema 而非猜测字段语义。
EntryUpdate = Annotated[UpsertEntry | RemoveEntry, Field(discriminator="operation")]


# 实现说明：SyncEntityInput
# 实体同步请求：幂等键、授权文件、明确长期更新与预期版本。
#
# files=None 表示未提交文件变更，files=[] 是明确空集合；具体合并规则待用例实现。
# expected_entity_version 只做非负校验，真正版本冲突需数据库事务检查。
class SyncEntityInput(Contract):
    request_id: UUID
    files: list[SourceFile] | None = Field(default=None, max_length=20)
    demand_updates: list[EntryUpdate] = Field(default_factory=list)
    supply_updates: list[EntryUpdate] = Field(default_factory=list)
    expected_entity_version: int | None = Field(default=None, ge=0)

    # 实现说明：SyncEntityInput.validate_updates
    # 确保这次调用确实表达更新且不存在同批重复来源 / 长期项。
    #
    # 分别检查 D、S 内部 entry_id，不禁止 D/S 使用同一 ID（两类是不同命名空间）。
    # 文件合计限制 8 MiB，不包含 JSON 转义和 HTTP body 的额外开销。
    @model_validator(mode="after")
    def validate_updates(self):
        if self.files is None and not self.demand_updates and not self.supply_updates:
            raise ValueError("At least one explicit update is required.")
        if self.files is not None:
            if len({f.source_id for f in self.files}) != len(self.files):
                raise ValueError("source_id must be unique.")
            if sum(len(f.text.encode("utf-8")) for f in self.files) > 8 * 1024 * 1024:
                raise ValueError("Files exceed 8 MiB total.")
        for updates in (self.demand_updates, self.supply_updates):
            if len({u.entry_id for u in updates}) != len(updates):
                raise ValueError("An entry can only be updated once per request.")
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


# 实现说明：SyncEntityResult
# 真实任务接受后的同步状态契约。
#
# entity_version / status / job_id 必须对应实际持久数据；accepted 不等于 Build 完成。
class SyncEntityResult(Contract):
    status: Literal["accepted"]
    entity_version: int
    entity_status: Literal["building", "ready", "refreshing"]
    job_id: UUID | None = None
    accepted_updates: list[str]


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
# ontology_refresh 固定提示 Host 在返回后重新收集；不能谎称 Worker 已读取远端文件。
class ConnectResult(Contract):
    status: Literal["matched", "no_match"]
    request_id: UUID
    entity_version: int
    connection_id: UUID | None = None
    candidate: CandidateResult | None = None
    notification: NotificationState | None = None
    ontology_refresh: Literal["host_collection_required"] = "host_collection_required"

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
