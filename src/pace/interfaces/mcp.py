# 模块说明
# 官方 MCP Python SDK 的 Tool 定义、命令分发与身份保护边界。
#
# 使用 Server / StreamableHTTPSessionManager，不自写 JSON-RPC、协议发现或 HTTP 会话。
# 业务只公开 sync_entity、connect；隔离层扩展 webhook events/*。
# 身份与 scope 在整个 MCP HTTP 入口验证，测试身份只能通过明确的测试装配注入。

"""Official SDK Streamable HTTP transport; exactly two business tools."""

import json
from urllib.parse import urlsplit

from mcp import types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from pace.application.contracts import (
    ConnectInput,
    ConnectResult,
    SyncEntityInput,
    SyncEntityResult,
)
from pace.bootstrap import Container
from pace.domain.errors import AuthenticationRequired, PaceError

# Schema 与调用分发共用此映射，防止发现两个 Tool、执行却另有隐藏入口。
TOOL_CONTRACTS = {
    "sync_entity": (SyncEntityInput, SyncEntityResult),
    "connect": (ConnectInput, ConnectResult),
}


# 实现说明：tool_definitions
# 由唯一契约映射生成官方 SDK Tool 对象。
#
# 输入 / 输出 Schema 均来自 Pydantic；两项操作会改变状态并可能访问外部世界。
# sync_entity 完整替换画像，因此 destructiveHint=True；持久用例实现同身份 / 同请求键重放。
def tool_definitions() -> list[types.Tool]:
    descriptions = {
        "sync_entity": (
            "Publish the complete PA-prepared O/D/S profile before connect; ready immediately."
        ),
        "connect": (
            "Submit an instant request; return Top-1 contact or No Match. "
            "First call sync_entity and pass its entity_version; do not sync after returning."
        ),
    }
    return [
        types.Tool(
            name=name,
            description=descriptions[name],
            inputSchema=input_model.model_json_schema(),
            outputSchema=output_model.model_json_schema(),
            annotations=types.ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=name == "sync_entity",
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        for name, (input_model, output_model) in TOOL_CONTRACTS.items()
    ]


# 实现说明：build_server
# 构造官方 Server 并注册发现 / 调用回调。
#
# 选择底层公开回调是为了保持平坦输入契约与统一结构化错误，不实现自有协议。
def build_server(container: Container) -> Server:
    # 实现说明：build_server.list_tools
    # 返回固定两项业务 Tool 的 Schema 与行为标注。
    #
    # 本回调不查询候选或暴露账号数据，仍由外层身份边界保护。
    async def list_tools(context, params):
        return types.ListToolsResult(tools=tool_definitions())

    # 实现说明：build_server.call_tool
    # 从服务端 request state 取得可信身份，校验输入后调用对应应用命令。
    #
    # 不得从 arguments 的 Email / 用户 ID 推导身份；结果同时提供文本与 structuredContent。
    # ValidationError 只返回安全 invalid_input，不回显可能包含私人正文的校验详情。
    # 仅捕获可公开 PaceError；其他未知异常仍交 SDK 处理。
    async def call_tool(context, params):
        try:
            # 此值由 ProtectedMCP 写入，客户端不能通过 Tool 参数覆写可信身份。
            principal = context.request.scope["state"]["pace_principal"]
            if params.name not in TOOL_CONTRACTS:
                return error_result("unknown_tool", "Unknown business tool.")
            required_scope = "pace:sync" if params.name == "sync_entity" else "pace:connect"
            if required_scope not in principal.scopes:
                return error_result(
                    "insufficient_scope", "The tool requires an additional PACE scope."
                )
            input_model, _ = TOOL_CONTRACTS[params.name]
            data = input_model.model_validate(params.arguments or {})
            # 只对已登记名称分发；缺数据库时命令明确抛 FeatureUnavailable。
            result = await getattr(container.commands, params.name)(principal, data)
            payload = result.model_dump(mode="json")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(payload))],
                structuredContent=payload,
            )
        except ValidationError:
            return error_result("invalid_input", "Input does not satisfy the tool contract.")
        except PaceError as exc:
            return error_result(exc.code, exc.public_message)
        except Exception:
            # SQL / SDK 原始异常可能带私有正文，不能作为 MCP 错误文本回显。
            return error_result("internal_error", "The PACE operation could not be completed.")

    return Server(
        "pace",
        version="0.1.0",
        instructions=(
            "PACE connections for event-capable personal agents. Under ongoing setup consent, "
            "prepare a rich O/D/S profile and sync before every connect; pass its entity_version. "
            "Subscribe to connection.matched and initialize a profile during setup. "
            "No scheduled sync or agent-to-agent chat."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        get_tool_input_schema=lambda name: (
            TOOL_CONTRACTS[name][0].model_json_schema() if name in TOOL_CONTRACTS else None
        ),
    )


# 实现说明：error_result
# 将稳定错误码 / 公开消息转为 SDK 的 Tool 错误结果。
#
# isError=True 与 no_match 是不同语义；structuredContent 与文本携带同一安全载荷。
def error_result(code: str, message: str) -> types.CallToolResult:
    payload = {"error": {"code": code, "message": message}}
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
        isError=True,
    )


# 实现说明：ProtectedMCP
# 包围官方 transport 的最小身份 / 权限校验层。
#
# OAuth 服务由独立 Adapter 与官方路由提供；本类拒绝未经验证的凭据。
class ProtectedMCP:
    """Authentication covers initialize, discovery and calls; no development bypass."""

    # 实现说明：ProtectedMCP.__init__
    # 创建无服务端会话依赖的官方 Streamable HTTP 管理器。
    #
    # json_response 便于结构化结果；body 最大 10 MiB，JSON 编码开销可能先于文本上限触发。
    def __init__(self, container: Container):
        self.container = container
        origin = container.settings.public_base_url
        hosts = [urlsplit(origin).netloc]
        origins = [origin]
        if container.settings.app_env == "development":
            hosts.extend(["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]:*"])
            origins.extend(["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"])
        security = TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins)
        self.security = TransportSecurityMiddleware(security)
        self.manager = StreamableHTTPSessionManager(
            build_server(container),
            stateless=True,
            json_response=True,
            max_request_body_size=10 * 1024 * 1024,
            security_settings=security,
        )

    # 实现说明：ProtectedMCP.__call__
    # 所有 MCP HTTP 方法在进入 SDK 前都要通过凭据和 scope 校验。
    #
    # 无 Bearer 为 401；默认验证器为 503；缺全部相关 scope 为 403，Tool / Event 分别检查所需 scope。
    # 成功后只将 Principal 放入服务端 scope.state，再调用 SDK 的 ASGI 处理。
    # Token 不写响应或日志，401 通过 WWW-Authenticate 提示客户端认证。
    async def __call__(self, scope, receive, send):
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        # Header 名称不区分大小写；Latin-1 解码 HTTP 原始头，不输出 Token。
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        try:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                raise AuthenticationRequired()
            principal = await self.container.identity.verify(token)
            # 发现只要求一项相关 scope；具体 Tool / Event 再检查自己的权限。
            if not {"pace:connect", "pace:sync"}.intersection(principal.scopes):
                response = JSONResponse(
                    {"error": {"code": "insufficient_scope", "message": "PACE scopes required."}},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
            # 请求级身份只存在当前 ASGI scope，不写共享全局变量避免串用户。
            scope.setdefault("state", {})["pace_principal"] = principal
        except PaceError as exc:
            response = JSONResponse(
                {"error": {"code": exc.code, "message": exc.public_message}},
                status_code=exc.status_code,
                headers={
                    "WWW-Authenticate": (
                        'Bearer resource_metadata="'
                        + self.container.settings.public_base_url
                        + '/.well-known/oauth-protected-resource/mcp"'
                    )
                }
                if exc.status_code == 401
                else None,
            )
            await response(scope, receive, send)
            return
        if self.container.events is not None:
            from pace.interfaces.events import METHODS, discovery_sender, handle_event_request

            method = headers.get(b"mcp-method", b"").decode("latin-1")
            if method in METHODS:
                if "pace:connect" not in principal.scopes:
                    await JSONResponse({"error": {"code": "insufficient_scope"}}, status_code=403)(
                        scope,
                        receive,
                        send,
                    )
                    return
                rejection = await self.security.validate_request(
                    Request(scope, receive),
                    is_post=scope["method"] == "POST",
                )
                if rejection:
                    await rejection(scope, receive, send)
                    return
                await handle_event_request(
                    scope,
                    receive,
                    send,
                    principal,
                    self.container.events,
                    self.container.settings.public_base_url,
                )
                return
            if method == "server/discover":
                send = discovery_sender(send)
        await self.manager.handle_request(scope, receive, send)
