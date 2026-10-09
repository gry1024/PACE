"""Per-subscription event outcomes prevent one success hiding another failure."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "matches",
        sa.Column("event_deliveries", postgresql.JSONB(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("matches", "event_deliveries")
