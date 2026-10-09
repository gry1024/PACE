# 模块说明：系统 Gmail 通过独立 OAuth refresh token 发信，登录用户无需授予 Gmail 权限。
"""Gmail API acceptance is not proof of receipt; retry may duplicate a sent message."""

import asyncio
import base64
from email.message import EmailMessage
from uuid import UUID

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from pace.domain.errors import DeliveryUnavailable, FeatureUnavailable
from pace.domain.gmail import canonical_gmail


class GmailEmail:
    """最小 gmail.send 权限，稳定 Message-ID 用于追踪而非承诺服务商 exactly-once。"""

    def __init__(self, settings):
        if not all(
            (
                settings.gmail_sender,
                settings.gmail_refresh_token,
                settings.gmail_client_id,
                settings.gmail_client_secret,
            )
        ):
            raise FeatureUnavailable()
        self.sender = canonical_gmail(settings.gmail_sender)
        self.credentials = Credentials(
            None,
            refresh_token=settings.gmail_refresh_token.get_secret_value(),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret.get_secret_value(),
            scopes=["https://www.googleapis.com/auth/gmail.send"],
        )
        self.lock = asyncio.Lock()

    def _send(self, message):
        """官方 google-auth 刷新与 HTTPS 授权；限制网络超时，不打印响应正文。"""
        with AuthorizedSession(
            self.credentials, refresh_timeout=15, max_refresh_attempts=1
        ) as session:
            response = session.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                json={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()},
                timeout=20,
            )
            if not response.ok or not response.json().get("id"):
                raise DeliveryUnavailable()

    async def deliver(self, recipient, subject, body, delivery_id):
        """仅向 Gmail 发送；外部异常归一化，避免正文 / Token 进入任务错误日志。"""
        message = EmailMessage()
        message["From"], message["To"] = self.sender, canonical_gmail(recipient)
        message["Subject"] = subject
        message["Message-ID"] = f"<{UUID(delivery_id)}@pace.local>"
        message.set_content(body)
        try:
            async with self.lock:
                await asyncio.to_thread(self._send, message)
        except Exception as exc:
            raise DeliveryUnavailable() from exc
        return "provider_accepted"
