# 模块说明：官方 MCP OAuth 路由与 Google 浏览器回跳；不提供匿名账号注册 API。
"""Browser consent binds each Google flow to an HttpOnly cookie."""

import html
import secrets

from mcp.server.auth.provider import construct_redirect_uri
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from pace.adapters.auth.google import SCOPES
from pace.domain.errors import PaceError


def auth_routes(provider):
    """SDK 校验注册 URI / scope / PKCE，本层只实现 Google 同意和验证回跳。"""
    secure = provider.base.startswith("https://")

    def error():
        return JSONResponse(
            {"error": "gmail_authorization_failed"},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )

    async def consent(request):
        if request.method == "POST":
            form = await request.form()
            flow = str(form.get("flow", ""))
            cookie = request.cookies.get("pace_oauth_flow", "")
            if not flow or not cookie or not secrets.compare_digest(flow, cookie):
                return error()
            if form.get("consent") != "yes":
                return error()
            try:
                response = RedirectResponse(await provider.google_redirect(flow), status_code=303)
            except PaceError:
                return error()
        else:
            flow = request.query_params.get("flow", "")
            record = await provider._read("flow", flow)
            if record is None:
                return error()
            name = html.escape(record.payload.get("client_name") or "MCP client")
            safe_flow = html.escape(flow, quote=True)
            response = HTMLResponse(
                "<!doctype html><html lang='zh'><meta charset='utf-8'>"
                "<title>PACE Gmail 授权</title>"
                f"<h1>连接 PACE</h1><p>客户端：{name}</p>"
                "<p>仅支持已验证的 @gmail.com。相同 Gmail 在不同平台使用同一个 PACE 账号。</p>"
                "<p>同意后，你可参与连接匹配；匹配会向双方披露 Gmail 和请求相关资料，"
                "并向你的 Gmail 发送连接通知。登录不会授权读取你的邮件。</p>"
                f"<form method='post'><input type='hidden' name='flow' value='{safe_flow}'>"
                "<label><input type='checkbox' name='consent' value='yes' required>"
                "同意 Gmail 身份绑定、连接资料披露和邮件通知</label>"
                "<p><button type='submit'>使用 Google 继续</button></p></form></html>"
            )
            response.set_cookie(
                "pace_oauth_flow",
                flow,
                max_age=600,
                httponly=True,
                secure=secure,
                samesite="lax",
                path="/auth",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    async def callback(request):
        flow = request.query_params.get("state", "")
        cookie = request.cookies.get("pace_oauth_flow", "")
        if (
            not flow
            or not cookie
            or not secrets.compare_digest(flow, cookie)
            or request.query_params.get("error")
            or not request.query_params.get("code")
        ):
            return error()
        try:
            code, params = await provider.complete_google(flow, request.query_params["code"])
        except Exception:
            # Google SDK 失败可能包含凭据；只公开稳定错误，不回显异常详情。
            return error()
        response = RedirectResponse(
            construct_redirect_uri(
                params["redirect_uri"],
                code=code,
                state=params.get("state"),
                iss=provider.base,
            ),
            status_code=303,
        )
        response.delete_cookie("pace_oauth_flow", path="/auth")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return [
        *create_auth_routes(
            provider,
            AnyHttpUrl(provider.base),
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=SCOPES,
                default_scopes=SCOPES,
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
        *create_protected_resource_routes(
            AnyHttpUrl(provider.resource),
            [AnyHttpUrl(provider.base)],
            scopes_supported=SCOPES,
        ),
        Route("/auth/consent", consent, methods=["GET", "POST"]),
        Route("/auth/google/callback", callback, methods=["GET"]),
    ]
