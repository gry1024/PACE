# 模块说明
# 固定的0001初始迁移：六张业务表加jobs基础设施。
#
# upgrade按外键依赖顺序创建表 /索引，downgrade按反向顺序删除。
# 字段与约束记录历史Schema；已应用到共享环境后应新增迁移，不改写旧历史。
# 这里的表存在不代表账号、业务授权、Ontology或通知流程已经实现。

"""initial_framework

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 实现说明：upgrade
# 建立初始MVP存储结构与可靠任务基础设施。
#
# 先accounts /jobs，再Entity /Snapshot /订阅，最后Request /Match，满足外键依赖。
# Schema创建由开发 /部署显式触发，不会由API存活检查或Worker自动运行。
def upgrade() -> None:
    # Reviewed initial framework schema; business handlers are implemented separately.
    # 账号根表：验证、注册授权与跨Host绑定；默认enabled=false。
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_version", sa.String(length=50), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("host_bindings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    # 基础设施任务表：稳定去重键、有限尝试与租约；不是第七个业务概念。
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 数据库硬约束仅校验当前表达式；不能代替业务授权或合法状态流转。
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')", name="job_status"
        ),
        # 数据库硬约束仅校验当前表达式；不能代替业务授权或合法状态流转。
        sa.CheckConstraint("attempts >= 0 AND max_attempts > 0", name="job_attempts"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    # 按status /available_at建立轮询索引，服务于到期任务领取。
    op.create_index("ix_jobs_poll", "jobs", ["status", "available_at"], unique=False)
    # 账号当前O/D/S与版本状态；发布切换仍需应用事务。
    op.create_table(
        "entities",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("ontology", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("demands", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supplies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 数据库硬约束仅校验当前表达式；不能代替业务授权或合法状态流转。
        sa.CheckConstraint(
            "status IN ('building','ready','refreshing','failed')", name="entity_status"
        ),
        # 数据库硬约束仅校验当前表达式；不能代替业务授权或合法状态流转。
        sa.CheckConstraint("version >= 0", name="entity_version_nonnegative"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("account_id"),
    )
    # 完成快照历史与来源；同账号版本唯一，只追加规则需用例保证。
    op.create_table(
        "entity_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 数据库硬约束仅校验当前表达式；不能代替业务授权或合法状态流转。
        sa.CheckConstraint("version > 0", name="snapshot_version_positive"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "version", name="uq_entity_snapshot"),
    )
    op.create_index(
        op.f("ix_entity_versions_account_id"), "entity_versions", ["account_id"], unique=False
    )
    # 订阅与回调元数据；实际签名 /公网上传验证未实现。
    op.create_table(
        "event_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("subscription_key", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("callback_url", sa.String(length=2048), nullable=False),
        sa.Column("signing_secret_ciphertext", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "client_id", "subscription_key", name="uq_subscription"),
    )
    op.create_index(
        op.f("ix_event_subscriptions_account_id"),
        "event_subscriptions",
        ["account_id"],
        unique=False,
    )
    # 独立即时请求与重放结果；账号+request_id唯一。
    op.create_table(
        "connection_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("selection_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 数据库硬约束仅校验当前表达式；不能代替业务授权或合法状态流转。
        sa.CheckConstraint(
            "status IN ('pending','matched','no_match','failed')", name="request_status"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["entity_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "request_id", name="uq_connect_idempotency"),
    )
    op.create_index(
        op.f("ix_connection_requests_account_id"),
        "connection_requests",
        ["account_id"],
        unique=False,
    )
    # Request的唯一连接结果；禁止自身连接，资格 /归属仍需用例校验。
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("contact_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("event_status", sa.String(length=30), nullable=False),
        sa.Column("email_status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 数据库硬约束仅校验当前表达式；不能代替业务授权或合法状态流转。
        sa.CheckConstraint("requester_id <> candidate_id", name="match_distinct_accounts"),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["candidate_snapshot_id"],
            ["entity_versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["connection_requests.id"],
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(op.f("ix_matches_candidate_id"), "matches", ["candidate_id"], unique=False)
    op.create_index(op.f("ix_matches_requester_id"), "matches", ["requester_id"], unique=False)


# 实现说明：downgrade
# 删除0001创建的表和索引，顺序与依赖相反。
#
# 会丢失业务数据，仅用于明确回滚迁移；不是正常启动或通用排错步骤。
# 当前交付验证没有在应用数据库执行此删除路径。
def downgrade() -> None:
    # Reviewed initial framework schema; business handlers are implemented separately.
    op.drop_index(op.f("ix_matches_requester_id"), table_name="matches")
    op.drop_index(op.f("ix_matches_candidate_id"), table_name="matches")
    op.drop_table("matches")
    op.drop_index(op.f("ix_connection_requests_account_id"), table_name="connection_requests")
    op.drop_table("connection_requests")
    op.drop_index(op.f("ix_event_subscriptions_account_id"), table_name="event_subscriptions")
    op.drop_table("event_subscriptions")
    op.drop_index(op.f("ix_entity_versions_account_id"), table_name="entity_versions")
    op.drop_table("entity_versions")
    op.drop_table("entities")
    op.drop_index("ix_jobs_poll", table_name="jobs")
    op.drop_table("jobs")
    # 最后删除所有依赖的根账号表；回滚前必须明确数据损失范围。
    op.drop_table("accounts")
