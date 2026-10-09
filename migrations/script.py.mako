# 模块说明：由Alembic生成的固定迁移历史；连接串与秘密不得写入本文件。
# 已应用的迁移不要随模型修改；结构变化通过新增revision表达。
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}

# 升级：按外键依赖顺序执行结构变化；不在应用启动时隐式运行。
def upgrade() -> None:
    ${upgrades if upgrades else "pass"}

# 回滚：通常反向撤销结构，可能删除数据；必须明确授权与备份范围。
def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
