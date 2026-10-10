# 模块说明：持久 MCP webhook 订阅；每次网络连接解析并固定公网 IP，保留 TLS SNI。
"""Verified, encrypted, account/client-owned Standard Webhooks subscriptions."""

import asyncio
import base64
import ipaddress
import json
import secrets
import socket
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from standardwebhooks import Webhook

from pace.adapters.db.business import advisory_lock, require_account
from pace.adapters.db.models import EventSubscription
from pace.domain.errors import DeliveryUnavailable, PermanentDeliveryError


class CallbackError(Exception):
    """仅保留可公开的 callback 错误类别。"""

    def __init__(self, reason):
        self.reason = reason


async def public_destination(url):
    """拒绝任一非公网 DNS 结果，返回固定 IP，防止验证后再次 DNS 解析。"""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.port not in {None, 443}
        or len(url) > 2048
    ):
        raise CallbackError("invalid_url")
    try:
        infos = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(
                parsed.hostname,
                443,
                type=socket.SOCK_STREAM,
            ),
            timeout=5,
        )
    except (OSError, TimeoutError) as exc:
        raise CallbackError("dns_failed") from exc
    addresses = sorted({info[4][0] for info in infos})
    if not addresses or any(
        not (address.is_global and not address.is_multicast and not address.is_reserved)
        for address in (ipaddress.ip_address(a) for a in addresses)
    ):
        raise CallbackError("non_public_address")
    ip = addresses[0]
    netloc = f"[{ip}]" if ":" in ip else ip
    return parsed._replace(netloc=netloc).geturl(), parsed.hostname.encode("idna").decode()


async def signed_post(url, secret, subscription_id, message_id, value, previous=None):
    """一次序列化即签名 / 发送；阻止重定向、环境代理和无上限响应体。"""
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(body.encode()) > 262144:
        raise PermanentDeliveryError()
    destination, hostname = await public_destination(url)
    now = datetime.now(UTC)
    signature = Webhook(secret).sign(message_id, now, body)
    if previous:
        signature += " " + Webhook(previous).sign(message_id, now, body)
    headers = {
        "Host": f"[{hostname}]" if ":" in hostname else hostname,
        "Content-Type": "application/json",
        "webhook-id": message_id,
        "webhook-timestamp": str(int(now.timestamp())),
        "webhook-signature": signature,
        "X-MCP-Subscription-Id": str(subscription_id),
    }
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
            async with client.stream(
                "POST",
                destination,
                content=body.encode(),
                headers=headers,
                extensions={"sni_hostname": hostname},
            ) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 8192:
                        raise CallbackError("response_too_large")
                return response.status_code, bytes(content)
    except httpx.TimeoutException as exc:
        raise CallbackError("timeout") from exc
    except httpx.HTTPError as exc:
        raise CallbackError("connection_failed") from exc


def subscription_id(principal, url):
    """订阅与官方复合参数退订共用稳定键；身份只能来自 Principal。"""
    return uuid5(
        NAMESPACE_URL,
        json.dumps(
            [str(principal.user_id), principal.client_id, url, "connection.matched", {}],
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


class EventWebhooks:
    """每个 account/client/destination 独立订阅；无 replay，有期限且必须 challenge。"""

    def __init__(self, sessions, encryption_key, post=signed_post):
        self.sessions = sessions
        self.cipher = Fernet(encryption_key.get_secret_value().encode())
        self.post = post

    def _seal(self, value):
        return self.cipher.encrypt(json.dumps(value).encode()).decode()

    def _open(self, value):
        return json.loads(self.cipher.decrypt(value.encode()))

    async def subscribe(self, principal, params):
        """验证参数及 24–64 byte secret；成功 challenge 后原子创建 / 刷新。"""
        delivery = params.get("delivery", {})
        secret = delivery.get("secret", "")
        try:
            valid_secret = (
                isinstance(secret, str)
                and secret.startswith("whsec_")
                and 24 <= len(base64.b64decode(secret[6:], validate=True)) <= 64
            )
        except (ValueError, TypeError):
            valid_secret = False
        ttl = params.get("ttlMs", 86400000)
        if (
            not principal.client_id
            or params.get("name") != "connection.matched"
            or params.get("arguments", {}) != {}
            or params.get("cursor") is not None
            or delivery.get("mode") != "webhook"
            or not valid_secret
            or (ttl is not None and (type(ttl) is not int or ttl < 1000))
        ):
            raise ValueError("Invalid subscription input.")
        url = delivery.get("url", "")
        if not isinstance(url, str):
            raise ValueError("Invalid subscription input.")
        identifier = subscription_id(principal, url)
        expires = datetime.now(UTC) + timedelta(milliseconds=min(ttl or 86400000, 86400000))
        async with self.sessions.begin() as session:
            await require_account(session, principal.user_id)
            await advisory_lock(session, f"subscription:{identifier}")
            row = await session.get(EventSubscription, identifier)
            previous = self._open(row.signing_secret_ciphertext) if row else {}
            # 相同 URL / secret 的有效订阅五分钟内复用已验证结果；换密钥重新 challenge。
            cached = bool(
                row
                and not row.revoked_at
                and row.verified_at
                and row.verified_at > datetime.now(UTC) - timedelta(minutes=5)
                and previous.get("current") == secret
            )
            if not cached:
                challenge = secrets.token_urlsafe(32)
                status, body = await self.post(
                    url,
                    secret,
                    identifier,
                    "verify_" + uuid4().hex,
                    {"type": "verification", "challenge": challenge},
                )
                try:
                    echoed = json.loads(body).get("challenge", "")
                except (ValueError, AttributeError):
                    echoed = ""
                if (
                    not 200 <= status < 300
                    or not isinstance(echoed, str)
                    or not secrets.compare_digest(challenge, echoed)
                ):
                    raise CallbackError("challenge_failed")
            value = {"current": secret}
            if previous.get("current") and previous["current"] != secret:
                value.update(previous=previous["current"], rotated=datetime.now(UTC).timestamp())
            elif previous.get("previous"):
                value.update(previous=previous["previous"], rotated=previous["rotated"])
            if row is None:
                row = EventSubscription(
                    id=identifier,
                    account_id=principal.user_id,
                    client_id=principal.client_id,
                    subscription_key=str(identifier),
                    event_type="connection.matched",
                    callback_url=url,
                )
                session.add(row)
            row.signing_secret_ciphertext = self._seal(value)
            row.expires_at, row.revoked_at = expires, None
            if not cached:
                row.verified_at = datetime.now(UTC)
        return {
            "id": str(identifier),
            "refreshBefore": expires.isoformat(),
            "cursor": None,
            "truncated": False,
        }

    async def unsubscribe(self, principal, identifier):
        """只操作当前 account/client 的订阅；不存在与不属于自己同样幂等返回。"""
        # 对外使用官方 name/arguments/delivery；内部终止投递仍可用已保存 UUID。
        if isinstance(identifier, dict):
            delivery = identifier.get("delivery", {})
            url = delivery.get("url")
            if (
                not principal.client_id
                or identifier.get("name") != "connection.matched"
                or identifier.get("arguments", {}) != {}
                or delivery.get("mode") != "webhook"
                or not isinstance(url, str)
                or not url
            ):
                raise ValueError("Invalid unsubscribe input.")
            identifier = subscription_id(principal, url)
        else:
            identifier = UUID(identifier)
        async with self.sessions.begin() as session:
            row = (
                await session.scalars(
                    select(EventSubscription)
                    .where(
                        EventSubscription.id == identifier,
                        EventSubscription.account_id == principal.user_id,
                        EventSubscription.client_id == principal.client_id,
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if row:
                row.revoked_at = datetime.now(UTC)
        return {}

    async def deliver_subscription(self, payload):
        """Worker 重查资格 / 到期 / 撤销；每次签名用新时间但保留同一 eventId。"""
        async with self.sessions() as session:
            row = await session.get(EventSubscription, UUID(payload["subscription_id"]))
            if (
                not row
                or row.revoked_at
                or row.expires_at <= datetime.now(UTC)
                or not row.verified_at
            ):
                return "inactive"
            await require_account(session, row.account_id)
            secrets_value = self._open(row.signing_secret_ciphertext)
            event = payload["event"]
            data = {k: v for k, v in event.items() if k not in {"event_id", "occurred_at", "type"}}
            envelope = {
                "eventId": event["event_id"],
                "name": "connection.matched",
                "timestamp": event["occurred_at"],
                "data": data,
                "cursor": None,
            }
            old = (
                secrets_value.get("previous")
                if datetime.now(UTC).timestamp() - secrets_value.get("rotated", 0) < 300
                else None
            )
            status, _ = await self.post(
                row.callback_url, secrets_value["current"], row.id, event["event_id"], envelope, old
            )
        if status in {410, 413}:
            await self.unsubscribe(
                type("Owner", (), {"user_id": row.account_id, "client_id": row.client_id}),
                str(row.id),
            )
            raise PermanentDeliveryError()
        if not 200 <= status < 300:
            raise DeliveryUnavailable()
        return "accepted_by_receiver"
