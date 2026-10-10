# 模块说明
# HTTP 运维入口与官方 MCP transport 的生命周期挂载。
#
# FastAPI 路由只提供存活、就绪和公开契约；业务 Tool 由 MCP SDK 分发，不增加 REST 业务旁路。
# 存活与依赖配置 / 迁移就绪分开；readyz 不调用付费模型或发送邮件。
# 应用退出关闭本进程拥有的 SDK Client 和数据库 Engine。

"""Public operations endpoints and protected MCP mounting."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.routing import Route

from pace.bootstrap import Container
from pace.interfaces.mcp import TOOL_CONTRACTS, ProtectedMCP


# 实现说明：build_app
# 构建 FastAPI 应用，并将受保护 MCP ASGI 对象挂在精确 /mcp 路径。
#
# 通过 Route 挂载已可调用的 ASGI 对象，不自行处理协议会话或 SSE。
def build_app(container: Container) -> FastAPI:
    transport = ProtectedMCP(container)

    # 实现说明：build_app.lifespan
    # 在应用生命周期内启动官方 MCP 管理器，并在退出时关闭 Container。
    #
    # SDK 使用其 run 上下文管理内部任务；业务资源关闭放入 finally，保证正常异常退出也执行。
    @asynccontextmanager
    async def lifespan(app):
        async with transport.manager.run():
            try:
                yield
            finally:
                await container.close()

    app = FastAPI(
        title="PACE",
        version="0.1.0",
        description="PACE Gmail identity, profile synchronization and connection backend.",
        lifespan=lifespan,
    )
    app.state.container = container
    if container.oauth is not None:
        from pace.interfaces.auth import auth_routes

        app.router.routes.extend(auth_routes(container.oauth))
    # GET / POST / DELETE 都先经过 ProtectedMCP；具体协议方法由官方 SDK处理。
    app.router.routes.append(Route("/mcp", transport, methods=["GET", "POST", "DELETE"]))

    # 实现说明：build_app.healthz
    # 仅报告当前 Python HTTP 进程存活与 mvp 阶段。
    #
    # 不读取秘密、不查询 DB，也不触发模型调用，因此不能当作完整就绪检查。
    @app.get("/healthz", tags=["operations"])
    def healthz():
        return {"status": "ok", "service": "pace", "stage": "mvp"}

    # 实现说明：build_app.readyz
    # 检查必要配置和 DB 迁移；未满足返回 503，满足返回 200。
    #
    # ready 不代表外部凭据已验收或独立 Worker 正在运行，部署验收另行执行。
    @app.get("/readyz", tags=["operations"], status_code=503)
    async def readyz():
        from sqlalchemy import text

        pending = []
        if container.oauth is None:
            pending.append("gmail_oauth_configuration")
        if container.choice is None:
            pending.append("jev_configuration")
        if container.events is None:
            pending.append("mcp_events_configuration")
        if container.settings.email_delivery_mode != "gmail" or not all(
            (
                container.settings.gmail_sender,
                container.settings.gmail_refresh_token,
                container.settings.gmail_client_id,
                container.settings.gmail_client_secret,
            )
        ):
            pending.append("gmail_notification_configuration")
        if container.database is None:
            pending.append("database_configuration")
        else:
            try:
                async with container.database.sessions() as session:
                    revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
                    if revision != "0003":
                        pending.append("database_migration")
            except Exception:
                pending.append("database_unavailable")
        return JSONResponse(
            {
                "status": "not_ready" if pending else "ready",
                "stage": "mvp",
                "email_delivery_mode": container.settings.email_delivery_mode,
                "pending": pending,
            },
            status_code=503 if pending else 200,
        )

    # 实现说明：build_app.contracts
    # 公开当前正式 Tool 的输入 / 输出 Schema。
    #
    # Schema 来自 Pydantic，不含真实用户数据、秘密或第三个业务 Tool。
    @app.get("/contracts", tags=["operations"])
    def contracts():
        """Public schemas contain no credentials or user data."""
        return {
            "version": "0.1.0",
            "business_tools": {
                name: {
                    "input": input_model.model_json_schema(),
                    "output": output_model.model_json_schema(),
                }
                for name, (input_model, output_model) in TOOL_CONTRACTS.items()
            },
        }

    return app
