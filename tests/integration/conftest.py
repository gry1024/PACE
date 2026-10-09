# 模块说明
# 真实PostgreSQL集成测试的隔离与迁移fixture。
#
# 默认跳过；只有PACE_TEST_DATABASE=1才使用配置数据库，不能误当纯离线测试。
# 每个测试随机建pace_test_* schema，实际执行Alembic升级，不用create_all代替迁移验收。
# finally只删除自身创建的隔离schema，不清空应用表；用测试数据库凭据运行。

"""Opt-in PostgreSQL tests migrate an isolated, randomly named schema."""

import os
import re
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pace.adapters.db.session import database_url
from pace.config import Settings


# 实现说明：sessions
# 为一个测试提供隔离schema内的异步Session工厂。
#
# 先严格检查随机schema名称，再用search_path让模型与迁移落入它。
# Engine和schema在finally清理，防止失败测试留下连接或表。
# DROP只针对本fixture创建的精确schema，不操作public业务数据。
@pytest.fixture
async def sessions():
    # 显式开启，避免普通pytest误连数据库或创建schema。
    if os.environ.get("PACE_TEST_DATABASE") != "1":
        pytest.skip("Set PACE_TEST_DATABASE=1 to run isolated PostgreSQL tests.")
    url = database_url(Settings())
    # 随机UUID隔离并行 /重复测试；只允许固定前缀和十六进制。
    schema = "pace_test_" + uuid4().hex
    assert re.fullmatch(r"pace_test_[0-9a-f]{32}", schema)
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    # 连接级search_path确保所有未限定表名指向测试schema。
    engine = create_async_engine(url, connect_args={"options": f"-csearch_path={schema}"})

    # 实现说明：sessions.migrate
    # 把现有测试连接交给Alembic执行真实head升级。
    #
    # 连接注入防止env.py另外创建连接跳出测试search_path。
    def migrate(connection):
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    try:
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            # Delete only the exact schema created by this fixture, never application tables.
            # 只清理自建精确schema；此处不接受用户输入或计算出的其他路径。
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
