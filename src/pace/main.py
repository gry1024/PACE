# 模块说明
# FastAPI / ASGI 的组合入口。
#
# uvicorn 导入本模块的 app；实际依赖选择集中在 bootstrap，HTTP 路由集中在 interfaces。
# create_app 暴露测试装配点，但生产 app 不注入任何合成身份或模拟业务命令。
# 导入时构造客户端 / Engine 不等于网络连通或业务准备就绪。

"""ASGI composition entry point: uvicorn pace.main:app."""

from pace.application.ports import BusinessCommands, IdentityVerifier
from pace.bootstrap import build_container
from pace.config import Settings, get_settings
from pace.interfaces.http import build_app


# 实现说明：create_app
# 构造一个具有独立 Container 和生命周期的 ASGI 应用。
#
# settings 缺省时使用缓存配置；identity / commands 是供测试或明确装配使用的 Port。
# 生产入口不传这两个替代实现，因此仍会拒绝未验证身份和未接线业务。
# 函数只装配，不迁移数据库、不触发模型调用、不创建用户或匹配。
def create_app(
    settings: Settings | None = None,
    identity: IdentityVerifier | None = None,
    commands: BusinessCommands | None = None,
):
    """Tests inject ports here; the production entry point never accepts arbitrary identities."""
    return build_app(build_container(settings or get_settings(), identity, commands))


# 供 uvicorn pace.main:app 使用的生产入口；没有测试绕过开关。
app = create_app()
