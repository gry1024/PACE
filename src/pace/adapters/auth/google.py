# 模块说明：Google OIDC 只验证 Gmail；PACE 独立签发资源绑定的 opaque 凭据。
# 授权码 / bearer 仅存 Hash；client secret / Google PKCE verifier 使用 Fernet 密文。
"""Persistent OAuth provider for the official MCP authorization routes."""

import asyncio
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from functools import partial
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import requests
from authlib.integrations.httpx_client import AsyncOAuth2Client
from cryptography.fernet import Fernet
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import delete, select

from pace.adapters.db.business import advisory_lock, require_account
from pace.adapters.db.models import Account, OAuthRecord
from pace.domain.errors import AccountUnavailable, AuthenticationRequired
from pace.domain.gmail import canonical_gmail
from pace.domain.models import Principal

SCOPES = ["pace:sync", "pace:connect"]
CONSENT_VERSION = "gmail-connections-v1"


def verified_id_token(raw, audience):
    """限制官方证书抓取等待，并关闭 transport Session；JWT 检查由 Google SDK 执行。"""
    with requests.Session() as network:
        transport = partial(Request(session=network), timeout=10)
        return id_token.verify_oauth2_token(raw, transport, audience)


def key(kind, raw):
    """高熵 opaque 值只保留不可逆索引，避免 DB 泄漏直接获得 bearer。"""
    return f"{kind}:" + hashlib.sha256(raw.encode()).hexdigest()


class GoogleOAuth(OAuthAuthorizationServerProvider):
    """SDK 负责协议验证，本类负责身份、持久化、一次性消费和令牌族撤销。"""

    def __init__(self, sessions, settings):
        self.sessions, self.settings = sessions, settings
        self.base = settings.public_base_url.rstrip("/")
        self.resource = self.base + "/mcp"
        self.cipher = Fernet(settings.encryption_key.get_secret_value().encode())

    async def _read(self, kind, raw):
        async with self.sessions() as session:
            row = await session.get(OAuthRecord, key(kind, raw))
            if row is None or (row.expires_at and row.expires_at <= datetime.now(UTC)):
                return None
            return row

    def seal(self, data):
        return self.cipher.encrypt(json.dumps(data).encode()).decode()

    def unseal(self, data):
        return json.loads(self.cipher.decrypt(data.encode()))

    async def get_client(self, client_id):
        row = await self._read("client", client_id)
        return (
            OAuthClientInformationFull.model_validate(self.unseal(row.payload["sealed"]))
            if row
            else None
        )

    async def register_client(self, client):
        """DCR 仅允许配置的精确 Host 回跳地址或开发环境 loopback。"""
        if not client.redirect_uris or len(client.redirect_uris) > 10:
            raise RegistrationError("invalid_redirect_uri", "Registered redirects required.")
        for uri in client.redirect_uris:
            target = str(uri)
            parsed = urlsplit(target)
            loopback = (
                self.settings.app_env == "development"
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
            if (
                (not loopback and target not in self.settings.oauth_redirect_allowlist)
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise RegistrationError("invalid_redirect_uri", "Redirect is not allowed.")
        if client.token_endpoint_auth_method not in {
            "none",
            "client_secret_basic",
            "client_secret_post",
        }:
            raise RegistrationError("invalid_client_metadata", "Unsupported client authentication.")
        async with self.sessions.begin() as session:
            session.add(
                OAuthRecord(
                    key=key("client", client.client_id),
                    kind="client",
                    payload={"sealed": self.seal(client.model_dump(mode="json"))},
                )
            )

    async def authorize(self, client, params):
        """每次客户端授权都显示独立同意页；Google state 不复用 Host state。"""
        if params.resource not in {None, self.resource}:
            raise AuthorizeError("invalid_target", "Unknown PACE resource.")
        scopes = params.scopes or SCOPES
        if not set(scopes).issubset(SCOPES):
            raise AuthorizeError("invalid_scope", "Unknown PACE scope.")
        flow = secrets.token_urlsafe(32)
        async with self.sessions.begin() as session:
            session.add(
                OAuthRecord(
                    key=key("flow", flow),
                    kind="flow",
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    payload={
                        "client_id": client.client_id,
                        "client_name": client.client_name,
                        "params": params.model_dump(mode="json"),
                        "scopes": scopes,
                        "nonce": secrets.token_urlsafe(32),
                        "verifier": self.seal(secrets.token_urlsafe(48)),
                        "consented": False,
                    },
                )
            )
        return self.base + "/auth/consent?flow=" + flow

    async def google_redirect(self, flow):
        """同意后才启动 Google 登录；只申请 openid/email，不读取用户 Gmail。"""
        async with self.sessions.begin() as session:
            row = await session.get(OAuthRecord, key("flow", flow), with_for_update=True)
            if not row or row.expires_at <= datetime.now(UTC) or row.payload["consented"]:
                raise AuthenticationRequired()
            row.payload = {**row.payload, "consented": True}
            async with AsyncOAuth2Client(
                self.settings.google_client_id,
                scope="openid email",
                redirect_uri=self.base + "/auth/google/callback",
                code_challenge_method="S256",
            ) as client:
                url, _ = client.create_authorization_url(
                    "https://accounts.google.com/o/oauth2/v2/auth",
                    state=flow,
                    nonce=row.payload["nonce"],
                    code_verifier=self.unseal(row.payload["verifier"]),
                    prompt="select_account",
                )
                return url

    async def google_claims(self, code, payload):
        """Google 官方验证器校验签名 / aud / exp；额外检查 nonce 和 Gmail 资格。"""
        async with AsyncOAuth2Client(
            self.settings.google_client_id,
            self.settings.google_client_secret.get_secret_value(),
            redirect_uri=self.base + "/auth/google/callback",
            timeout=15,
        ) as client:
            token = await client.fetch_token(
                "https://oauth2.googleapis.com/token",
                code=code,
                code_verifier=self.unseal(payload["verifier"]),
            )
        claims = await asyncio.to_thread(
            verified_id_token,
            token["id_token"],
            self.settings.google_client_id,
        )
        if (
            claims.get("email_verified") is not True
            or claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
            or not secrets.compare_digest(str(claims.get("nonce", "")), payload["nonce"])
            or not claims.get("sub")
            or claims.get("azp", self.settings.google_client_id) != self.settings.google_client_id
        ):
            raise AuthenticationRequired()
        canonical_gmail(claims["email"])
        return claims

    async def complete_google(self, flow, code):
        """先原子消费 flow，再验证；失败不允许复用 Google callback。"""
        async with self.sessions.begin() as session:
            row = await session.get(OAuthRecord, key("flow", flow), with_for_update=True)
            if not row or row.expires_at <= datetime.now(UTC) or not row.payload["consented"]:
                raise AuthenticationRequired()
            payload = row.payload
            await session.delete(row)
        claims = await self.google_claims(code, payload)
        email, subject = canonical_gmail(claims["email"]), claims["sub"]
        raw = secrets.token_urlsafe(32)
        expires = datetime.now(UTC) + timedelta(minutes=2)
        async with self.sessions.begin() as session:
            # 双键按固定顺序锁定，禁止同邮箱不同 Google sub 自动合并。
            for lock in sorted(["gmail:" + email, "google:" + subject]):
                await advisory_lock(session, lock)
            accounts = (
                await session.scalars(
                    select(Account)
                    .where((Account.email == email) | (Account.google_subject == subject))
                    .with_for_update()
                )
            ).all()
            if accounts:
                account = accounts[0]
                if (
                    len(accounts) != 1
                    or account.email != email
                    or account.google_subject != subject
                    or not account.enabled
                ):
                    raise AccountUnavailable()
            else:
                account = Account(
                    email=email, google_subject=subject, enabled=True, host_bindings=[]
                )
                session.add(account)
                await session.flush()
            account.email_verified_at = account.consented_at = datetime.now(UTC)
            account.consent_version = CONSENT_VERSION
            binding = {"issuer": self.base, "client_id": payload["client_id"]}
            if binding not in account.host_bindings:
                account.host_bindings = [*account.host_bindings, binding]
            data = {
                **payload["params"],
                "code": "",
                "client_id": payload["client_id"],
                "scopes": payload["scopes"],
                "expires_at": expires.timestamp(),
                "resource": self.resource,
                "subject": str(account.id),
            }
            # SDK state 属于回跳参数，不进入 AuthorizationCode 的有效载荷。
            data.pop("state", None)
            session.add(
                OAuthRecord(
                    key=key("code", raw),
                    kind="code",
                    payload=data,
                    account_id=account.id,
                    expires_at=expires,
                )
            )
        return raw, payload["params"]

    async def load_authorization_code(self, client, authorization_code):
        row = await self._read("code", authorization_code)
        if (
            not row
            or row.payload["client_id"] != client.client_id
            or row.payload["resource"] != self.resource
        ):
            return None
        return AuthorizationCode.model_validate({**row.payload, "code": authorization_code})

    async def _issue(self, session, row, scopes):
        """重新核验账号，签发绑定 /mcp 的新令牌族；所有旧族成员可一致撤销。"""
        await require_account(session, row.account_id, lock=True)
        family = row.payload.get("family", str(uuid4()))
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        for kind, raw, seconds in (
            ("access", access, self.settings.oauth_access_seconds),
            ("refresh", refresh, self.settings.oauth_refresh_seconds),
        ):
            session.add(
                OAuthRecord(
                    key=key(kind, raw),
                    kind=kind,
                    account_id=row.account_id,
                    expires_at=datetime.now(UTC) + timedelta(seconds=seconds),
                    payload={
                        "client_id": row.payload["client_id"],
                        "scopes": scopes,
                        "resource": self.resource,
                        "family": family,
                    },
                )
            )
        return OAuthToken(
            access_token=access,
            refresh_token=refresh,
            expires_in=self.settings.oauth_access_seconds,
            scope=" ".join(scopes),
        )

    async def _exchange(self, kind, raw, client, scopes=None):
        """事务中再次查锁，避免 SDK 先 load 后 exchange 间隙的并发双花。"""
        async with self.sessions.begin() as session:
            if kind == "refresh":
                existing = await self._read(kind, raw)
                if existing is None:
                    raise TokenError("invalid_grant", "Expired or consumed credential.")
                await advisory_lock(session, "token-family:" + existing.payload["family"])
            row = await session.get(OAuthRecord, key(kind, raw), with_for_update=True)
            if (
                not row
                or row.expires_at <= datetime.now(UTC)
                or row.payload["client_id"] != client.client_id
                or row.payload["resource"] != self.resource
            ):
                raise TokenError("invalid_grant", "Expired or consumed credential.")
            granted = row.payload["scopes"] if scopes is None else scopes
            if not set(granted).issubset(row.payload["scopes"]):
                raise TokenError("invalid_scope", "Scope escalation is forbidden.")
            if kind == "refresh":
                # 删除整个旧族后再签发，轮换后旧 access 也立即失效。
                await session.execute(
                    delete(OAuthRecord).where(
                        OAuthRecord.payload["family"].astext == row.payload["family"]
                    )
                )
            else:
                await session.delete(row)
            return await self._issue(session, row, granted)

    async def exchange_authorization_code(self, client, authorization_code):
        return await self._exchange("code", authorization_code.code, client)

    async def load_refresh_token(self, client, refresh_token):
        row = await self._read("refresh", refresh_token)
        if (
            not row
            or row.payload["client_id"] != client.client_id
            or row.payload["resource"] != self.resource
        ):
            return None
        return RefreshToken(
            token=refresh_token,
            **row.payload,
            expires_at=int(row.expires_at.timestamp()),
            subject=str(row.account_id),
        )

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        return await self._exchange("refresh", refresh_token.token, client, scopes)

    async def load_access_token(self, token):
        row = await self._read("access", token)
        if not row or row.payload["resource"] != self.resource:
            return None
        async with self.sessions() as session:
            try:
                await require_account(session, row.account_id)
            except AccountUnavailable:
                return None
        return AccessToken(
            token=token,
            **row.payload,
            expires_at=int(row.expires_at.timestamp()),
            subject=str(row.account_id),
            claims={"iss": self.base},
        )

    async def revoke_token(self, token):
        kind = "access" if isinstance(token, AccessToken) else "refresh"
        row = await self._read(kind, token.token)
        if row:
            async with self.sessions.begin() as session:
                await advisory_lock(session, "token-family:" + row.payload["family"])
                await session.execute(
                    delete(OAuthRecord).where(
                        OAuthRecord.payload["family"].astext == row.payload["family"]
                    )
                )

    async def verify(self, bearer_token):
        """只接受 PACE 签发的有效凭据，Google ID/access token 不能直通 MCP。"""
        token = await self.load_access_token(bearer_token)
        if token is None:
            raise AuthenticationRequired()
        return Principal(UUID(token.subject), frozenset(token.scopes), token.client_id)
