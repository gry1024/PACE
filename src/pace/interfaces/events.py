# 模块说明：官方 SDK 尚无公开 events 回调，隔离扩展方法，工具 transport 继续使用 SDK。
"""MCP 2026-07-28 events extension on the authenticated transport."""

import json

from starlette.responses import JSONResponse

from pace.adapters.delivery.events import CallbackError
from pace.application.contracts import ConnectionMatched
from pace.domain.errors import PaceError

METHODS = {"events/list", "events/subscribe", "events/unsubscribe"}


def event_definitions():
    """data Schema 与实际 webhook envelope 一致，不把事件登记为业务工具。"""
    schema = ConnectionMatched.model_json_schema()
    for name in ("event_id", "occurred_at", "type"):
        schema["properties"].pop(name, None)
        if name in schema.get("required", []):
            schema["required"].remove(name)
    return [
        {
            "name": "connection.matched",
            "description": "A connection request selected you.",
            "delivery": ["webhook"],
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "payloadSchema": schema,
        }
    ]


async def handle_event_request(scope, receive, send, principal, adapter, base):
    """有界读取、版本及方法头一致检查；授权已由外围完成。"""
    headers = dict(scope.get("headers", []))
    identifier = None
    try:
        if scope["method"] != "POST" or headers.get(b"mcp-protocol-version") != b"2026-07-28":
            raise ValueError()
        origin = headers.get(b"origin")
        if origin and origin.decode() != base:
            raise ValueError()
        content = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                raise ValueError()
            content.extend(message.get("body", b""))
            if len(content) > 16384:
                raise ValueError()
            if not message.get("more_body"):
                break
        request = json.loads(content)
        identifier = request["id"]
        method = request["method"]
        params = request.get("params", {})
        if (
            request.get("jsonrpc") != "2.0"
            or method not in METHODS
            or headers.get(b"mcp-method", b"").decode() != method
            or params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion")
            != "2026-07-28"
        ):
            raise ValueError()
        if method == "events/list":
            result = {"events": event_definitions()}
        elif method == "events/subscribe":
            result = await adapter.subscribe(principal, params)
        else:
            result = await adapter.unsubscribe(principal, params)
        response = {"jsonrpc": "2.0", "id": identifier, "result": result}
    except CallbackError as exc:
        response = {
            "jsonrpc": "2.0",
            "id": identifier,
            "error": {
                "code": -32015,
                "message": "CallbackEndpointError",
                "data": {"reason": exc.reason},
            },
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        response = {
            "jsonrpc": "2.0",
            "id": identifier,
            "error": {"code": -32602, "message": "Invalid event parameters."},
        }
    except PaceError as exc:
        response = {
            "jsonrpc": "2.0",
            "id": identifier,
            "error": {"code": -32000, "message": exc.public_message},
        }
    await JSONResponse(response)(scope, receive, send)


def discovery_sender(send):
    """仅给 SDK JSON 发现响应加 events capability，其他字节保持原样。"""
    start = None
    chunks = bytearray()

    async def amended(message):
        nonlocal start
        if message["type"] == "http.response.start":
            start = message
        elif message["type"] == "http.response.body":
            chunks.extend(message.get("body", b""))
            if message.get("more_body"):
                return
            try:
                body = json.loads(chunks)
                if "capabilities" in body.get("result", {}):
                    body["result"]["capabilities"]["events"] = {}
                    chunks[:] = json.dumps(body).encode()
            except (ValueError, TypeError, AttributeError):
                pass
            start["headers"] = [(k, v) for k, v in start["headers"] if k != b"content-length"]
            start["headers"].append((b"content-length", str(len(chunks)).encode()))
            await send(start)
            await send({"type": "http.response.body", "body": bytes(chunks)})
        else:
            await send(message)

    return amended
