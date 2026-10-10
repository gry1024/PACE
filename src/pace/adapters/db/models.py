# 模块说明
# MVP 业务表、同步回执、OAuth 状态与持久 jobs 的 SQLAlchemy 映射。
#
# 这些结构与迁移负责对象存在、唯一键、部分状态和值域，不代表业务用例已完成。
# 授权、Snapshot 归属、只追加历史、JSON 内部结构与幂等重放仍需用例检查。
# 多数 UUID / JSON 默认值是 Python ORM default，直接 SQL INSERT 不能假设它们都有服务端默认。
# OAuth 与 webhook secret 通过 Fernet 加密；Key 在外部环境配置中。

"""Business and infrastructure tables; Alembic owns schema changes."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# 实现说明：Base
# 全部 ORM 表的声明基类与元数据入口。
#
# Alembic 使用 Base.metadata 对比模型，API 不用它偷偷 create_all。
class Base(DeclarativeBase):
    pass


# 实现说明：Timestamped
# 共用创建时间字段。
#
# server_default=now() 使用数据库时钟，直接 SQL / ORM 插入都有一致时间基准。
class Timestamped:
    # 数据库生成的创建时间；保留时区，方便跨 Host 与重试诊断。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# 实现说明：Account
# 稳定用户账号与注册连接授权的持久结构。
#
# Gmail 唯一与 Google sub 唯一；验证与披露同意由 Google callback 写入。
class Account(Timestamped, Base):
    __tablename__ = "accounts"
    # 内部稳定主键，由 ORM 生成 UUID；不是用户可以指定来获取他人对象的凭据。
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # 由 Google 验证后写入规范 Gmail；本列另保证唯一。
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # Google 验证的稳定 sub；跨 Host 不依赖各平台临时用户 ID。
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    # 真实验证成功时间；字段存在本身不能证明验证流程已运行。
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 记录初始持续 PA 上传 / 匹配 / 披露 / 双通知授权的说明版本，便于追踪同意口径。
    consent_version: Mapped[str | None] = mapped_column(String(50))
    # 一次性注册连接授权时间；后续候选查询须明确要求已授权。
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 默认禁用，避免未完成验证 / 授权的账号意外进入候选池。
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # 跨 Host 身份绑定的结构；issuer / subject / client 应经验证后写入。
    host_bindings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


# 实现说明：Entity
# 每个账号至多一条当前 Entity：O / D / S、状态与版本。
#
# 同步事务直接发布完整快照并维护版本与 updated_at；Worker 只处理通知。
class Entity(Timestamped, Base):
    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint("version >= 0", name="entity_version_nonnegative"),
        CheckConstraint(
            "status IN ('building','ready','refreshing','failed')", name="entity_status"
        ),
    )
    # 所属账号外键；每个访问 / 更新用例仍须检查当前 Principal 的对象权限。
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    # 实体版本号；唯一性 / 值域不等于已经实现乐观锁或版本发布事务。
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 对象生命周期状态；数据库 CheckConstraint 限定部分合法值，不自动执行状态转换。
    status: Mapped[str] = mapped_column(String(20), default="building")
    # PA 提供的原样文本以 {text: ...} JSONB 保存。
    ontology: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # 只存明确长期 Demand，不允许即时 Request 自动追加。
    demands: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # 只存明确长期 Supply；选择允许 Demand↔Demand，不强制供需单向配对。
    supplies: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # 旧上传协议的历史原文列，仅兼容历史 schema；新同步不读写此列。
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # 插入默认时间；同步和发布事务主动维护更新时间。
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# 实现说明：EntityVersion
# 历史已完成 O/D/S Snapshot；来源 / 模型元数据列仅保留旧协议兼容。
#
# 同账号版本号唯一，version>0；当前无不可变 Trigger，业务用例只追加。
class EntityVersion(Timestamped, Base):
    __tablename__ = "entity_versions"
    __table_args__ = (
        UniqueConstraint("account_id", "version", name="uq_entity_snapshot"),
        CheckConstraint("version > 0", name="snapshot_version_positive"),
    )
    # 内部稳定主键，由 ORM 生成 UUID；不是用户可以指定来获取他人对象的凭据。
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # 所属账号外键；每个访问 / 更新用例仍须检查当前 Principal 的对象权限。
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    # 实体版本号；唯一性 / 值域不等于已经实现乐观锁或版本发布事务。
    version: Mapped[int] = mapped_column(Integer)
    # 已完成的 O / D / S 快照内容；pa-entity-v1 由 PA 直接提供，历史只追加。
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # 旧提取协议的来源元数据；新 PA 快照为空，不伪造远端来源证明。
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # 历史后端提炼模型标识；PA 直接发布时为 None，不声明使用了后端模型。
    model: Mapped[str | None] = mapped_column(String(100))
    # 画像格式 / 历史生成规则版本；与模型版本分别记录，避免 Prompt 改动不可追溯。
    prompt_version: Mapped[str | None] = mapped_column(String(50))


# 实现说明：ConnectionRequest
# 独立即时请求、幂等载荷与选择结果。
#
# 账号+客户端request_id唯一；外键确保Snapshot存在，但不保证它归此账号所有。
class ConnectionRequest(Timestamped, Base):
    __tablename__ = "connection_requests"
    __table_args__ = (
        UniqueConstraint("account_id", "request_id", name="uq_connect_idempotency"),
        CheckConstraint(
            "status IN ('pending','matched','no_match','failed')", name="request_status"
        ),
    )
    # 内部稳定主键，由 ORM 生成 UUID；不是用户可以指定来获取他人对象的凭据。
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # 所属账号外键；每个访问 / 更新用例仍须检查当前 Principal 的对象权限。
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    # 客户端幂等键，与所属账号共同唯一；不同账号可以使用同一请求 UUID。
    request_id: Mapped[UUID] = mapped_column()
    # 规范化输入指纹；同键不同输入应冲突，不能覆盖已有结果。
    payload_hash: Mapped[str] = mapped_column(String(64))
    # 工作 / 请求原始结构化载荷，可能有私人资料，不应写公共日志。
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Requester 所用完成版本的引用；需要额外检查与 account_id 一致。
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("entity_versions.id"))
    # 对象生命周期状态；数据库 CheckConstraint 限定部分合法值，不自动执行状态转换。
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # 保存已提交的原始幂等结果，不随通知状态变动重新生成。
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # 分组诊断数据，组内概率不能作为全局成功率。
    selection_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # 保存稳定安全错误类别，不保存外部异常全文或凭据。
    error_code: Mapped[str | None] = mapped_column(String(100))


# 实现说明：Match
# 某个 Request 的唯一连接结果与双方联系快照。
#
# 禁止双方相同，不代表账号已验证 / 同意；业务命令还需校验候选资格。
class Match(Timestamped, Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("requester_id <> candidate_id", name="match_distinct_accounts"),
    )
    # 内部稳定主键，由 ORM 生成 UUID；不是用户可以指定来获取他人对象的凭据。
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # 连接引用内部 Request 主键，一条 Request 至多一个 Match。
    request_id: Mapped[UUID] = mapped_column(ForeignKey("connection_requests.id"), unique=True)
    # 申请方账号，必须与关联 Request 的所有者一致，当前需用例保证。
    requester_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    # 被选中的账号；必须排除自身并具备验证 / 授权资格。
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    # 被选时的完成快照，避免后续更新改变历史连接证据。
    candidate_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("entity_versions.id"))
    # 此次披露的联系方式 / 相关信息快照，不依赖当前账号字段后来变动。
    contact_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Event 通道独立状态；不能用邮件成功覆写 Event 失败。
    event_status: Mapped[str] = mapped_column(String(30), default="queued")
    # 每个订阅独立交付状态，聚合后不能让另一订阅成功掩盖失败。
    event_deliveries: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    # Email 通道独立状态；queued / provider_accepted 不等于已读。
    email_status: Mapped[str] = mapped_column(String(30), default="queued")


# 实现说明：EventSubscription
# 持久化事件订阅、验证和过期 / 撤销信息。
#
# EventWebhooks 实施公网固定 IP、challenge、加密、签名与 account/client 归属校验。
class EventSubscription(Timestamped, Base):
    __tablename__ = "event_subscriptions"
    __table_args__ = (
        UniqueConstraint("account_id", "client_id", "subscription_key", name="uq_subscription"),
    )
    # 内部稳定主键，由 ORM 生成 UUID；不是用户可以指定来获取他人对象的凭据。
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # 所属账号外键；每个访问 / 更新用例仍须检查当前 Principal 的对象权限。
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    # 经过身份绑定的 Host / OAuth 客户端标识，不接受模型任意声明。
    client_id: Mapped[str] = mapped_column(String(200))
    # 同账号 / client 内的稳定订阅键，用于幂等刷新与去重。
    subscription_key: Mapped[str] = mapped_column(String(200))
    # 当前冻结业务事件只有 connection.matched。
    event_type: Mapped[str] = mapped_column(String(100), default="connection.matched")
    # Adapter 对 challenge 和投递均实施公网 HTTPS / SSRF 校验。
    callback_url: Mapped[str] = mapped_column(String(2048))
    # Fernet 密文，包含当前 / 短期轮换旧 secret；密钥不写入数据库。
    signing_secret_ciphertext: Mapped[str] = mapped_column(String)
    # 订阅有效期；Worker 投递前需校验，没有自动删除逻辑。
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # callback challenge 成功时间，未验证订阅不能用于真实投递。
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 撤销时间，后续领取 / 投递时都应尊重撤销状态。
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# 实现说明：Job
# 可靠任务基础设施，不是额外业务对象。
#
# 唯一dedupe_key防止重复入队；租约与尝试字段支持进程重启和至少一次执行。
class Job(Timestamped, Base):
    """Infrastructure, not a seventh business concept."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed')", name="job_status"),
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="job_attempts"),
        Index("ix_jobs_poll", "status", "available_at"),
    )
    # 内部稳定主键，由 ORM 生成 UUID；不是用户可以指定来获取他人对象的凭据。
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Handler 注册键；未知类型明确失败而非执行默认模拟成功逻辑。
    kind: Mapped[str] = mapped_column(String(100))
    # 全任务表唯一稳定键，重试不能创造新的业务通知身份。
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    # 工作 / 请求原始结构化载荷，可能有私人资料，不应写公共日志。
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # 对象生命周期状态；数据库 CheckConstraint 限定部分合法值，不自动执行状态转换。
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    # 每次真实领取增加一次；续租不增加尝试数。
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 有限重试上限，避免未知 Handler 或外部故障无限消耗资源。
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    # 任务最早可领取时间，用于失败退避，不是执行完成时间。
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # 每次领取生成新 UUID，阻止旧 Worker 确认被接管任务。
    lease_id: Mapped[UUID | None] = mapped_column()
    # 当前持有者的截止时间；过期后允许其他 Worker 恢复执行。
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 保存稳定安全错误类别，不保存外部异常全文或凭据。
    error_code: Mapped[str | None] = mapped_column(String(100))
    # 成功确认时间；只在持有有效租约时写入。
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncReceipt(Timestamped, Base):
    """同步操作的持久幂等回执；原结果重放不再次更新或调用模型。"""

    __tablename__ = "sync_receipts"
    __table_args__ = (UniqueConstraint("account_id", "request_id", name="uq_sync_receipt"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    request_id: Mapped[UUID] = mapped_column()
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OAuthRecord(Timestamped, Base):
    """OAuth 短期状态 / 令牌 / 客户端记录；Bearer 和 code 的 key 只存 SHA-256。"""

    __tablename__ = "oauth_records"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
