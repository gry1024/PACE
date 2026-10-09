# 新迁移保留 0001 历史，补齐业务幂等、文件集合和 Google 身份基础设施。
"""Business state and Gmail OAuth persistence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    """显式升级；既有账号未验证 Google，保留 nullable 而非伪造 sub。"""
    op.add_column("accounts", sa.Column("google_subject", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_accounts_google_subject", "accounts", ["google_subject"])
    op.add_column("entities", sa.Column("files", JSONB(), server_default="[]", nullable=False))
    op.create_table(
        "sync_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("account_id", "request_id", name="uq_sync_receipt"),
    )
    op.create_table(
        "oauth_records",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    for column in ("kind", "account_id", "expires_at"):
        op.create_index(f"ix_oauth_records_{column}", "oauth_records", [column])


def downgrade():
    """回滚会丢失身份 / 同步状态，仅用于明确授权的迁移回退。"""
    op.drop_table("oauth_records")
    op.drop_table("sync_receipts")
    op.drop_column("entities", "files")
    op.drop_constraint("uq_accounts_google_subject", "accounts", type_="unique")
    op.drop_column("accounts", "google_subject")
