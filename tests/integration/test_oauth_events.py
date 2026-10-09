# 模块说明：只模拟 Google 已验证 claims 与 HTTPS 接收器，OAuth 存储 / 协议实际运行。
import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from mcp.server.auth.provider import AuthorizationParams, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy import func, select
from starlette.applications import Starlette
from starlette.testclient import TestClient

from pace.adapters.auth.google import GoogleOAuth
from pace.adapters.db.models import Account, OAuthRecord
from pace.adapters.delivery.events import EventWebhooks
from pace.config import Settings
from pace.domain.errors import AuthenticationRequired
from pace.interfaces.auth import auth_routes


def settings():
    return Settings(
        _env_file=None,
        google_client_id="synthetic-id",
        google_client_secret="synthetic-secret",
        encryption_key=Fernet.generate_key().decode(),
    )


def client(name):
    return OAuthClientInformationFull(
        client_id=name,
        client_name=name,
        redirect_uris=["http://127.0.0.1:9000/callback"],
        token_endpoint_auth_method="none",
        scope="pace:sync pace:connect",
    )


async def grant(provider, host, monkeypatch, exchange=True):
    """两个 Host 的 Google 验证得到同一邮箱 / sub，不模拟 PACE token 校验。"""
    verifier = "v" * 50
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    params = AuthorizationParams(
        state="host-state",
        scopes=["pace:sync", "pace:connect"],
        code_challenge=challenge,
        redirect_uri="http://127.0.0.1:9000/callback",
        redirect_uri_provided_explicitly=True,
        resource=provider.resource,
    )
    await provider.register_client(host)
    url = await provider.authorize(host, params)
    flow = parse_qs(urlsplit(url).query)["flow"][0]
    await provider.google_redirect(flow)

    async def verified(code, payload):
        return {"email": "Cross.Platform+host@gmail.com", "sub": "verified-test-sub"}

    monkeypatch.setattr(provider, "google_claims", verified)
    raw, _ = await provider.complete_google(flow, "synthetic-google-code")
    code = await provider.load_authorization_code(host, raw)
    return (await provider.exchange_authorization_code(host, code) if exchange else code), raw, flow


async def test_cross_host_identity_rotation_revocation_and_one_time_code(sessions, monkeypatch):
    provider = GoogleOAuth(sessions, settings())
    one, code, flow = await grant(provider, client("host-one"), monkeypatch)
    two, _, _ = await grant(provider, client("host-two"), monkeypatch)
    first, second = await provider.verify(one.access_token), await provider.verify(two.access_token)
    assert first.user_id == second.user_id and first.client_id != second.client_id
    assert await provider.load_authorization_code(client("host-one"), code) is None
    with pytest.raises(AuthenticationRequired):
        await provider.complete_google(flow, "replay")
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Account)) == 1
        records = (await session.scalars(select(OAuthRecord))).all()
        assert all(one.access_token not in json.dumps(r.payload) for r in records)
    refresh = await provider.load_refresh_token(client("host-one"), one.refresh_token)
    rotated = await provider.exchange_refresh_token(client("host-one"), refresh, refresh.scopes)
    with pytest.raises(AuthenticationRequired):
        await provider.verify(one.access_token)
    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(client("host-one"), refresh, refresh.scopes)
    active = await provider.load_access_token(rotated.access_token)
    await provider.revoke_token(active)
    with pytest.raises(AuthenticationRequired):
        await provider.verify(rotated.access_token)
    assert await provider.verify(two.access_token) == second


async def test_subscription_refresh_ownership_rotation_and_delivery(sessions, monkeypatch):
    config = settings()
    provider = GoogleOAuth(sessions, config)
    token, _, _ = await grant(provider, client("events-host"), monkeypatch)
    principal = await provider.verify(token.access_token)
    posted = []

    async def post(url, secret, subscription_id, message_id, value, previous=None):
        posted.append((value, secret, previous))
        return 200, json.dumps({"challenge": value.get("challenge")}).encode()

    events = EventWebhooks(sessions, config.encryption_key, post)
    params = {
        "name": "connection.matched",
        "arguments": {},
        "delivery": {
            "mode": "webhook",
            "url": "https://receiver.example/hook",
            "secret": "whsec_" + base64.b64encode(b"a" * 32).decode(),
        },
    }
    first = await events.subscribe(principal, params)
    second = await events.subscribe(principal, params)
    assert first["id"] == second["id"] and len(posted) == 1
    params["delivery"]["secret"] = "whsec_" + base64.b64encode(b"b" * 32).decode()
    await events.subscribe(principal, params)
    payload = {
        "subscription_id": first["id"],
        "event": {
            "event_id": "event-123",
            "occurred_at": "2026-10-09T12:00:00Z",
            "type": "connection.matched",
            "connection_id": "connection-123",
            "requester": {"email": "test@gmail.com"},
            "request_summary": "synthetic",
        },
    }
    assert await events.deliver_subscription(payload) == "accepted_by_receiver"
    assert posted[-1][0]["eventId"] == "event-123" and posted[-1][2] is not None
    await events.unsubscribe(principal, first["id"])
    assert await events.deliver_subscription(payload) == "inactive"
    assert len(posted) == 3


async def test_credentials_cannot_cross_a_reconfigured_resource_origin(sessions, monkeypatch):
    config = settings()
    original = GoogleOAuth(sessions, config)
    host = client("resource-host")
    issued, _, _ = await grant(original, host, monkeypatch)
    refresh = await original.load_refresh_token(host, issued.refresh_token)
    moved = GoogleOAuth(
        sessions, config.model_copy(update={"public_base_url": "https://other.example"})
    )
    with pytest.raises(AuthenticationRequired):
        await moved.verify(issued.access_token)
    assert await moved.load_refresh_token(host, issued.refresh_token) is None
    with pytest.raises(TokenError):
        await moved.exchange_refresh_token(host, refresh, refresh.scopes)


async def test_official_token_endpoint_enforces_pkce_and_single_use(sessions, monkeypatch):
    import httpx

    provider = GoogleOAuth(sessions, settings())
    host = client("pkce-host")
    _, raw, _ = await grant(provider, host, monkeypatch, exchange=False)
    app = Starlette(routes=auth_routes(provider))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url=provider.base
    ) as browser:
        form = {
            "grant_type": "authorization_code",
            "client_id": host.client_id,
            "code": raw,
            "redirect_uri": "http://127.0.0.1:9000/callback",
            "code_verifier": "wrong",
        }
        assert (await browser.post("/token", data=form)).status_code == 400
        form["code_verifier"] = "v" * 50
        response = await browser.post("/token", data=form)
        assert response.status_code == 200, response.text
        principal = await provider.verify(response.json()["access_token"])
        assert principal.client_id == host.client_id
        assert (await browser.post("/token", data=form)).status_code == 400


def test_oauth_metadata_and_browser_flow_cookie(sessions):
    # 此测试 async fixture 需在事件循环内使用，路由无数据库访问的 metadata 可同步验证。
    provider = GoogleOAuth(sessions, settings())
    with TestClient(Starlette(routes=auth_routes(provider))) as browser:
        assert browser.get("/.well-known/oauth-authorization-server").status_code == 200
        assert browser.get("/.well-known/oauth-protected-resource/mcp").status_code == 200
        assert (
            browser.post("/auth/consent", data={"flow": "attacker", "consent": "yes"}).status_code
            == 400
        )
