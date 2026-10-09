# 模块说明：邮箱规范化不等于验证；拒绝非个人 Gmail，通知不真实发送。

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from standardwebhooks import Webhook

from pace.adapters.delivery.events import CallbackError, public_destination, signed_post
from pace.adapters.delivery.gmail import GmailEmail
from pace.config import Settings
from pace.domain.gmail import canonical_gmail


def test_gmail_aliases_and_excluded_domains():
    assert canonical_gmail(" User.Name+pace@GMAIL.com ") == "username@gmail.com"
    for value in ("user@googlemail.com", "user@example.com", "@gmail.com", "a@b@gmail.com"):
        with pytest.raises(ValueError):
            canonical_gmail(value)


async def test_callback_private_ip_blocked():
    for url in (
        "http://example.com/hook",
        "https://127.0.0.1/hook",
        "https://[::1]/hook",
        "https://user:pass@example.com/hook",
        "https://example.com:444/hook",
        "https://224.0.0.1/hook",
    ):
        with pytest.raises(CallbackError):
            await public_destination(url)


def test_config_rejects_untrusted_issuer_and_mode():
    for values in (
        {"public_base_url": "http://external.example"},
        {"public_base_url": "https://example.com/path"},
        {"email_delivery_mode": "pretend"},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)
    assert len(Fernet.generate_key()) == 44


async def test_gmail_adapter_uses_separate_system_credentials(monkeypatch):
    settings = Settings(
        _env_file=None,
        gmail_sender="system@gmail.com",
        gmail_refresh_token="synthetic",
        gmail_client_id="synthetic",
        gmail_client_secret="synthetic",
    )
    email = GmailEmail(settings)
    messages = []
    monkeypatch.setattr(email, "_send", messages.append)
    assert (
        await email.deliver(
            "user@gmail.com", "subject", "body", "00000000-0000-0000-0000-000000000001"
        )
        == "provider_accepted"
    )
    assert messages[0]["To"] == "user@gmail.com"
    assert messages[0]["From"] == "system@gmail.com"


async def test_signed_delivery_pins_ip_and_preserves_tls_hostname(monkeypatch):
    from pace.adapters.delivery import events

    sent = {}

    async def destination(url):
        return "https://8.8.8.8/hook", "receiver.example"

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, **kwargs):
            sent.update(method=method, url=url, **kwargs)
            return Response()

    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_bytes(self):
            yield b"{}"

    monkeypatch.setattr(events, "public_destination", destination)
    monkeypatch.setattr(events.httpx, "AsyncClient", Client)
    secret = "whsec_" + __import__("base64").b64encode(b"a" * 32).decode()
    assert await signed_post(
        "https://receiver.example/hook", secret, "subscription", "evt-id", {"eventId": "evt-id"}
    ) == (200, b"{}")
    assert sent["url"] == "https://8.8.8.8/hook"
    assert sent["headers"]["Host"] == "receiver.example"
    assert sent["extensions"]["sni_hostname"] == "receiver.example"
    assert Webhook(secret).verify(sent["content"], sent["headers"])["eventId"] == "evt-id"


@pytest.mark.parametrize(
    "changed",
    [
        {"email_verified": False},
        {"email": "user@example.com"},
        {"nonce": "replayed"},
        {"iss": "https://evil.example"},
        {"azp": "other-client"},
        {"sub": ""},
    ],
)
async def test_google_extra_claim_checks_reject_unverified_or_wrong_identity(monkeypatch, changed):
    from pace.adapters.auth import google
    from pace.domain.errors import AuthenticationRequired

    claims = {
        "email_verified": True,
        "email": "user@gmail.com",
        "nonce": "expected",
        "iss": "https://accounts.google.com",
        "sub": "subject",
        **changed,
    }
    config = Settings(
        _env_file=None,
        google_client_id="client",
        google_client_secret="synthetic",
        encryption_key=Fernet.generate_key().decode(),
    )
    provider = google.GoogleOAuth(None, config)

    class GoogleClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def fetch_token(self, *args, **kwargs):
            return {"id_token": "synthetic-id-token"}

    monkeypatch.setattr(google, "AsyncOAuth2Client", GoogleClient)
    monkeypatch.setattr(google, "verified_id_token", lambda raw, audience: claims)
    with pytest.raises((AuthenticationRequired, ValueError)):
        await provider.google_claims(
            "google-code", {"nonce": "expected", "verifier": provider.seal("verifier")}
        )
