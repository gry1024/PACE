# 模块说明
# 集中装配具体依赖，保持业务代码与外部 SDK 分离。
#
# 本模块知道具体 DB / Jev Adapter；应用规则只依赖 Port，不自己读取 Key 或实例化 SDK。
# 默认身份 / 业务命令明确报未接线，不能因配置了 DB 和 Key 就返回模拟匹配。
# Container 管理 API 进程拥有的资源，其关闭由 FastAPI lifespan 触发。

"""Composition root: only this module selects concrete infrastructure adapters."""

from dataclasses import dataclass

from pace.adapters.db.session import Database
from pace.adapters.providers.jev import JevChoiceProvider
from pace.application.ports import BusinessCommands, IdentityVerifier
from pace.application.services import UnconfiguredCommands, UnconfiguredIdentity
from pace.config import Settings


# 实现说明：Container
# API 进程持有的依赖集合。
#
# identity 决定可信 Principal；commands 提供两项业务用例；database / choice 可缺省。
# 后两者装配完成不表示 commands 已使用它们，目前业务仍未接线。
@dataclass
class Container:
    settings: Settings
    identity: IdentityVerifier
    commands: BusinessCommands
    database: Database | None
    choice: JevChoiceProvider | None

    # 实现说明：Container.close
    # 释放本 Container 创建的模型连接和数据库连接池。
    #
    # 按 Jev、DB 的顺序关闭，避免正常退出留下网络资源。
    # 当前关闭是顺序 await，若前一步异常，后一步没有 finally 保证；扩展时需审查此限制。
    async def close(self):
        if self.choice is not None:
            await self.choice.close()
        if self.database is not None:
            await self.database.close()


# 实现说明：build_container
# 根据配置选择具体 Adapter，并保留显式注入的应用 Port。
#
# 配置缺失时不隐式改用内存数据库或伪造模型；可选依赖保持 None。
# Jev 使用官方 SDK，超时和输入预算来自已校验 Settings。
# 默认 Unconfigured 实现是可观察失败边界，不是临时成功桩。
def build_container(
    settings: Settings,
    identity: IdentityVerifier | None = None,
    commands: BusinessCommands | None = None,
) -> Container:
    return Container(
        settings=settings,
        # 测试可注入合成实现；默认实现不会接受任意 Token。
        identity=identity or UnconfiguredIdentity(),
        commands=commands or UnconfiguredCommands(),
        # Engine 构造不会自动建表；迁移必须由 Alembic 显式执行。
        database=Database(settings) if settings.database_url else None,
        # 仅在 Key 已配置时创建官方 SDK Adapter，不自动进行远程调用。
        choice=JevChoiceProvider(
            settings.jev_api_key.get_secret_value(),
            settings.jev_model,
            timeout=settings.provider_timeout_seconds,
            input_bytes=settings.jev_input_bytes,
        )
        if settings.jev_api_key
        else None,
    )
