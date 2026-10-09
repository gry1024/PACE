# 模块说明
# 通过真实官方MCP ASGI transport验证发现 /调用与身份边界。
#
# 只将Identity /Commands替换为合成测试实现，协议解析与Schema仍由真实SDK运行。
# 测试针对2026-07-28 envelope /header约定，不证明真实OAuth或Host安装可用。
# 默认能力未接线必须明显报错，而不是返回模拟匹配。

from uuid import UUID

from fastapi.testclient import TestClient

from pace.application.contracts import ConnectResult
from pace.config import Settings
from pace.domain.models import Principal
from pace.main import create_app


# 实现说明：TestIdentity
# 只在create_app测试装配中使用的合成身份验证器。
#
# __test__=False避免pytest把这份辅助类当成测试类收集；不是生产认证绕过。
class TestIdentity:
    __test__ = False

    # 实现说明：TestIdentity.verify
    # 要求固定合成Token，返回固定账号与两项测试scope。
    #
    # 无任何真实用户凭据；用于证明Principal来自服务端Port而不是Tool参数。
    async def verify(self, bearer_token):
        assert bearer_token == "synthetic-token"
        return Principal(UUID(int=100), frozenset({"pace:connect", "pace:sync"}))


# 实现说明：TestCommands
# 提供一个可通过SDK输出Schema的合成connect命令。
#
# 该桩不写数据库、不查询候选、不能代表生产No Match行为已实现。
class TestCommands:
    __test__ = False

    # 实现说明：TestCommands.connect
    # 断言实际收到可信Principal，再构造形状合法的合成No Match。
    #
    # 请求ID沿用输入，便于检查SDK结构化返回与命令之间的接线。
    async def connect(self, principal, data):
        assert principal.user_id == UUID(int=100)
        return ConnectResult(status="no_match", request_id=data.request_id, entity_version=1)


# 实现说明：headers
# 构造当前协议的HTTP头；可为具体Tool补MCP-Name。
#
# Accept同时列JSON与event-stream，避免transport协商错误遮蔽业务测试。
def headers(method="tools/list", name=None):
    return {
        "MCP-Method": method,
        **({"MCP-Name": name} if name else {}),
        "Authorization": "Bearer synthetic-token",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
    }


# 实现说明：request
# 构造JSON-RPC请求与2026协议要求的_meta envelope。
#
# 每次携带版本与客户端capabilities，不能沿用旧协议initialize格式假设。
def request(method, params=None, request_id=1):
    envelope = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {**(params or {}), "_meta": envelope},
    }


# 实现说明：test_default_mcp_rejects_missing_auth_and_unconfigured_verification
# 默认入口无Token返回401，有合成Token但无验证器返回503。
#
# 公开/contracts只暴露两个Schema，不表示能绕过MCP身份保护。
def test_default_mcp_rejects_missing_auth_and_unconfigured_verification():
    with TestClient(create_app(Settings(_env_file=None)), base_url="http://localhost") as client:
        assert client.post("/mcp", json=request("tools/list")).status_code == 401
        assert client.post("/mcp", headers=headers(), json=request("tools/list")).status_code == 503
        public = client.get("/contracts").json()
        assert set(public["business_tools"]) == {"sync_entity", "connect"}


# 实现说明：test_real_sdk_discover_list_and_call_with_injected_test_ports
# 真实SDK依次处理server/discover、tools/list、tools/call。
#
# 验证版本支持、只有两Tool、改变状态标注和结构化No Match；测试桩仅替代应用边界。
def test_real_sdk_discover_list_and_call_with_injected_test_ports():
    app = create_app(Settings(_env_file=None), identity=TestIdentity(), commands=TestCommands())
    with TestClient(app, base_url="http://localhost") as client:
        init = client.post(
            "/mcp",
            headers=headers("server/discover"),
            json=request("server/discover"),
        )
        assert init.status_code == 200, init.text
        assert "2026-07-28" in init.json()["result"]["supportedVersions"]
        listed = client.post("/mcp", headers=headers(), json=request("tools/list"))
        tools = listed.json()["result"]["tools"]
        assert {tool["name"] for tool in tools} == {"sync_entity", "connect"}
        assert all(tool["annotations"]["readOnlyHint"] is False for tool in tools)
        called = client.post(
            "/mcp",
            headers=headers("tools/call", "connect"),
            json=request(
                "tools/call",
                {
                    "name": "connect",
                    "arguments": {
                        "request_id": str(UUID(int=1)),
                        "request_text": "Synthetic request",
                        "context": {
                            "observed_at": "2026-10-07T12:00:00Z",
                            "timezone": "Asia/Shanghai",
                        },
                    },
                },
            ),
        )
        result = called.json()["result"]
        assert result["structuredContent"]["status"] == "no_match"
        assert result["isError"] is False


# 实现说明：test_unconfigured_commands_report_error_instead_of_fake_match
# 身份可验证但业务未接线时应得到isError /feature_unavailable。
#
# 区分正常MCP协议响应中的业务错误与匹配结果。
def test_unconfigured_commands_report_error_instead_of_fake_match():
    app = create_app(Settings(_env_file=None), identity=TestIdentity())
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post(
            "/mcp",
            headers=headers("tools/call", "sync_entity"),
            json=request(
                "tools/call",
                {
                    "name": "sync_entity",
                    "arguments": {"request_id": str(UUID(int=1)), "files": []},
                },
            ),
        )
        result = response.json()["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "feature_unavailable"


def test_events_extension_discovery_and_header_validation():
    """官方SDK发现仍正常，仅隔离扩展增加events能力且没有第三项Tool。"""
    app = create_app(Settings(_env_file=None), identity=TestIdentity(), commands=TestCommands())
    app.state.container.events = object()
    with TestClient(app, base_url="http://localhost") as client:
        discovered = client.post(
            "/mcp", headers=headers("server/discover"), json=request("server/discover")
        )
        assert (
            discovered.status_code == 200
            and "events" in discovered.json()["result"]["capabilities"]
        )
        listed = client.post("/mcp", headers=headers("events/list"), json=request("events/list"))
        assert listed.status_code == 200
        definition = listed.json()["result"]["events"][0]
        assert definition["name"] == "connection.matched" and definition["delivery"] == ["webhook"]
        assert "event_id" not in definition["payloadSchema"]["properties"]
        wrong = client.post(
            "/mcp",
            headers=headers("events/list"),
            json=request("events/unsubscribe", {"id": "bad"}),
        )
        assert wrong.json()["error"]["code"] == -32602
        blocked = client.post(
            "/mcp",
            headers={**headers("events/list"), "Origin": "https://evil.example"},
            json=request("events/list"),
        )
        assert blocked.status_code == 403


def test_authenticated_mcp_rejects_untrusted_host():
    app = create_app(Settings(_env_file=None), identity=TestIdentity(), commands=TestCommands())
    with TestClient(app, base_url="http://evil.example") as client:
        blocked = client.post("/mcp", headers=headers(), json=request("tools/list"))
        assert blocked.status_code == 421


def test_scopes_are_checked_per_tool():
    class ConnectOnly(TestIdentity):
        async def verify(self, bearer_token):
            return Principal(UUID(int=100), frozenset({"pace:connect"}))

    app = create_app(Settings(_env_file=None), identity=ConnectOnly(), commands=TestCommands())
    with TestClient(app, base_url="http://localhost") as client:
        listed = client.post("/mcp", headers=headers(), json=request("tools/list"))
        assert listed.status_code == 200
        called = client.post(
            "/mcp",
            headers=headers("tools/call", "sync_entity"),
            json=request(
                "tools/call",
                {
                    "name": "sync_entity",
                    "arguments": {
                        "request_id": str(UUID(int=1)),
                        "files": [],
                    },
                },
            ),
        )
        assert called.json()["result"]["structuredContent"]["error"]["code"] == "insufficient_scope"
