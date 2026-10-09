# 模块说明
# 异步 PostgreSQL 连接与 Session 生命周期。
#
# SQLAlchemy asyncio 复用 psycopg 驱动，不自写连接池或在启动时建表。
# 连接串由 Settings 的 SecretStr 提供，不能输出到日志；Schema 由 Alembic 显式迁移。
# 本模块只持有基础设施，不替代业务事务、权限或幂等检查。

"""Async PostgreSQL sessions. Never auto-create tables on application startup."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from pace.config import Settings
from pace.domain.errors import FeatureUnavailable


# 实现说明：database_url
# 读取秘密连接串，并转换为 SQLAlchemy 的 PostgreSQL psycopg URL。
#
# 缺配置明确报未接线；不允许自动降级 SQLite 或任意其他驱动。
# 只替换已知前缀，避免改写连接串中其他部分。
def database_url(settings: Settings) -> str:
    if settings.database_url is None:
        raise FeatureUnavailable()
    url = settings.database_url.get_secret_value()
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("PACE requires a PostgreSQL psycopg connection URL.")
    return url


# 实现说明：Database
# API / Worker 可各自拥有的异步 Engine 和 Session 工厂。
#
# 不同进程不共享内存连接池，共享的是持久 PostgreSQL。
class Database:
    # 实现说明：Database.__init__
    # 建立 Engine 与不在 commit 后立即过期的 Session 工厂。
    #
    # pool_pre_ping 在借出连接前检测失效连接；构造 Engine 不会迁移 Schema。
    # expire_on_commit=False 允许已领取任务离开事务后读字段，避免异步隐式加载。
    def __init__(self, settings: Settings):
        self.engine: AsyncEngine = create_async_engine(database_url(settings), pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    # 实现说明：Database.close
    # 释放本 Engine 持有的连接池。
    #
    # 应在进程生命周期退出或集成测试清理时调用，不是在每条查询后重建 Engine。
    async def close(self):
        await self.engine.dispose()
