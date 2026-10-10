# 模块说明：隔离 PostgreSQL 合成闭环，--live 最多两次 Jev，后端零 LLM；只捕获邮件。
"""Exercise sync, ontology publication, connect replay and private capture in an isolated schema."""

import argparse
import asyncio
import json
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pace.adapters.db.business import BusinessRepository
from pace.adapters.db.handlers import BusinessHandlers
from pace.adapters.db.jobs import JobQueue
from pace.adapters.db.models import Account, EventSubscription, Match
from pace.adapters.db.session import database_url
from pace.adapters.delivery.capture import CaptureEmail
from pace.adapters.providers.jev import JevChoiceProvider
from pace.application.business import PersistentCommands
from pace.application.contracts import ConnectInput, SyncEntityInput
from pace.application.tournament import Tournament
from pace.config import Settings
from pace.domain.errors import PaceError
from pace.domain.models import CONSENT_VERSION, ChoiceDecision, Principal
from pace.interfaces.worker import Worker


class CountedChoice:
    """费用硬上限；发生异常也计一次，不自动扩大模型重试。"""

    def __init__(self, real=None):
        self.real, self.calls, self.usage = real, 0, []

    async def choose(self, requester, request_text, candidates, context=None):
        self.calls += 1
        if self.calls > 2:
            raise RuntimeError("Demo choice budget exhausted.")
        if self.real:
            result = await self.real.choose(requester, request_text, candidates, context)
        else:
            winner = "no_match" if "Rust" in request_text else str(candidates[0].user_id)
            keys = [str(c.user_id) for c in candidates] + ["no_match"]
            result = ChoiceDecision(winner, {k: float(k == winner) for k in keys}, "fixture")
        self.usage.append(result.usage)
        return result


async def demo(sessions, live, settings, directory):
    """无真人账号 / 邮件；走真实用例及 Worker，OAuth 另外由离线协议测试验收。"""
    real = (
        JevChoiceProvider(
            settings.jev_api_key.get_secret_value(),
            settings.jev_model,
            timeout=settings.provider_timeout_seconds,
            input_bytes=settings.jev_input_bytes,
        )
        if live
        else None
    )
    choice = CountedChoice(real)
    service = PersistentCommands(BusinessRepository(sessions), Tournament(choice))

    class OfflineEvents:
        async def deliver_subscription(self, payload):
            return "accepted_by_receiver"

    handlers = BusinessHandlers(sessions, email=CaptureEmail(directory), events=OfflineEvents())
    worker = Worker(JobQueue(sessions), handlers.registry())
    try:
        principals = []
        async with sessions.begin() as session:
            for name in ("pacesyntheticrequester", "pacesyntheticcandidate"):
                row = Account(
                    email=name + "@gmail.com",
                    google_subject="demo-" + name,
                    enabled=True,
                    email_verified_at=datetime.now(UTC),
                    consented_at=datetime.now(UTC),
                    consent_version=CONSENT_VERSION,
                    host_bindings=[],
                )
                session.add(row)
                await session.flush()
                principals.append(Principal(row.id, frozenset({"pace:sync", "pace:connect"})))
                # 演示仅模拟 Host 订阅 / 接收，不对公网发送或冒充真实平台验收。
                session.add(
                    EventSubscription(
                        account_id=row.id,
                        client_id="demo-host",
                        subscription_key=str(uuid4()),
                        callback_url="https://receiver.example/hook",
                        signing_secret_ciphertext="synthetic",
                        verified_at=datetime.now(UTC),
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    )
                )
        profile = (
            "I teach Python to beginners remotely. Available 2026-10-10 10:00-11:00 "
            "Asia/Shanghai. I do not teach Rust. This is a synthetic test profile."
        )
        # PA 完整画像同步立即可用，不需要 Worker，也不会调用后端 LLM。
        version = None
        for principal, ontology in zip(principals, ("Python beginner", profile), strict=True):
            data = SyncEntityInput(request_id=uuid4(), ontology=ontology, demands=[], supplies=[])
            accepted = await service.sync_entity(principal, data)
            assert await service.sync_entity(principal, data) == accepted
            assert accepted.entity_status == "ready"
            version = accepted.entity_version
        context = {"observed_at": datetime.now(UTC), "timezone": "Asia/Shanghai"}
        wanted = ConnectInput(
            request_id=uuid4(),
            entity_version=version,
            request_text=(
                "Find a Python beginner teacher for a remote lesson on 2026-10-10 "
                "10:00-11:00 Asia/Shanghai."
            ),
            context=context,
        )
        match = await service.connect(principals[0], wanted)
        assert await service.connect(principals[0], wanted) == match
        assert choice.calls == 1
        mismatch = await service.connect(
            principals[0],
            ConnectInput(
                request_id=uuid4(),
                entity_version=version,
                request_text="I need a Rust teacher; Python teaching is not acceptable.",
                context=context,
            ),
        )
        while await worker.run_once():
            pass
        async with sessions() as session:
            stored = (await session.scalars(select(Match))).all()
            captured = [row.email_status for row in stored]
        return {
            "mode": "live_synthetic" if live else "offline_synthetic",
            "match_status": match.status,
            "hard_conflict_status": mismatch.status,
            "replay_extra_calls": 0,
            "jev_calls": choice.calls,
            "backend_llm_calls": 0,
            "jev_usage": choice.usage,
            "notification_states": captured,
            "expected_cases_passed": match.status == "matched" and mismatch.status == "no_match",
            "actual_emails_sent": 0,
            "actual_webhooks_sent": 0,
        }
    finally:
        if real:
            await real.close()


async def run(live):
    settings = Settings()
    if live and not settings.jev_api_key:
        print(json.dumps({"error": "provider_configuration_missing"}))
        return 1
    schema = "pace_demo_" + uuid4().hex
    assert re.fullmatch(r"pace_demo_[0-9a-f]{32}", schema)
    admin = create_async_engine(database_url(settings))
    engine = None
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            database_url(settings), connect_args={"options": f"-csearch_path={schema}"}
        )

        def migrate(connection):
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        with tempfile.TemporaryDirectory(prefix="pace-demo-") as directory:
            result = await demo(
                async_sessionmaker(engine, expire_on_commit=False), live, settings, Path(directory)
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(not result["expected_cases_passed"])
    except Exception as exc:
        # 不打印 Provider 异常、私有内容或连接串。
        print(json.dumps({"error": exc.code if isinstance(exc, PaceError) else type(exc).__name__}))
        return 1
    finally:
        if engine:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="At most two Jev calls; no backend LLM."
    )
    raise SystemExit(asyncio.run(run(parser.parse_args().live)))
