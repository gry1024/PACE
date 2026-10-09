# 模块说明
# Alembic迁移环境：显式读取配置并连接PostgreSQL。
#
# 模型元数据用于漂移比较；迁移历史由versions维护，API /Worker启动不自动建表。
# 连接串不写入alembic.ini，从SecretStr读取后仅交给Engine。
# 集成测试可以注入已有连接，确保在自建隔离schema中执行真实迁移。

"""Alembic reads secrets from Settings, not a committed connection string."""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from pace.adapters.db.models import Base
from pace.adapters.db.session import database_url
from pace.config import Settings

# ORM元数据仅用于生成 /检查迁移，不会通过它偷偷create_all。
target_metadata = Base.metadata


# 实现说明：configure
# 在给定同步连接上配置模型比对并运行迁移事务。
#
# compare_type=True帮助发现列类型漂移；连接可能由异步Engine的run_sync提供。
def configure(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


# 实现说明：run_online
# 用NullPool临时Engine执行线上迁移后释放资源。
#
# 迁移是显式命令，不借API连接池；异步连接通过run_sync调用Alembic同步接口。
async def run_online():
    engine = create_async_engine(database_url(Settings()), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(configure)
    await engine.dispose()


# 测试显式注入连接优先，避免迁移误连真实应用schema。
if context.config.attributes.get("connection") is not None:
    configure(context.config.attributes["connection"])
# 离线模式只生成SQL；literal_binds让输出可阅读，不表示SQL已执行。
elif context.is_offline_mode():
    context.configure(
        url=database_url(Settings()), target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
