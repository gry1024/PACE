# 模块说明
# 集中装配具体依赖，保持业务代码与外部 SDK 分离。
#
# 本模块知道具体 DB / Jev Adapter；应用规则只依赖 Port，不自己读取 Key 或实例化 SDK。
# 配置完整时装配持久用例与 Gmail OAuth；缺配置使用明确失败实现。
# Container 管理 API 进程拥有的资源，其关闭由 FastAPI lifespan 触发。

"""Composition root: only this module selects concrete infrastructure adapters."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from pace.adapters.auth.google import GoogleOAuth
from pace.adapters.db.business import BusinessRepository
from pace.adapters.db.handlers import BusinessHandlers
from pace.adapters.db.session import Database
from pace.adapters.delivery.capture import CaptureEmail
from pace.adapters.delivery.events import EventWebhooks
from pace.adapters.delivery.gmail import GmailEmail
from pace.adapters.providers.jev import JevChoiceProvider
from pace.adapters.providers.ontology import LLMOntologyBuilder
from pace.application.business import PersistentCommands
from pace.application.ports import BusinessCommands, IdentityVerifier
from pace.application.services import UnconfiguredCommands, UnconfiguredIdentity
from pace.application.tournament import Tournament
from pace.config import Settings
from pace.domain.errors import FeatureUnavailable


# 实现说明：Container
# API 进程持有的依赖集合。
#
# identity 决定可信 Principal；commands 提供两项业务用例；database / choice 可缺省。
# 持久命令通过业务 Repository 与 Tournament 使用 DB / Choice。
@dataclass
class Container:
    settings: Settings
    identity: IdentityVerifier
    commands: BusinessCommands
    database: Database | None
    choice: JevChoiceProvider | None
    ontology: LLMOntologyBuilder | None = None
    oauth: GoogleOAuth | None = None
    events: EventWebhooks | None = None
    handlers: BusinessHandlers | None = None

    # 实现说明：Container.close
    # 释放本 Container 创建的模型连接和数据库连接池。
    #
    # 并行关闭全部已创建资源，单个关闭失败不阻断其他清理。
    # 清理异常集中返回 ExceptionGroup，不丢弃失败信息。
    async def close(self):
        results = await asyncio.gather(
            *(
                resource.close()
                for resource in (self.choice, self.ontology, self.database)
                if resource is not None
            ),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            raise ExceptionGroup("Resource shutdown failed", errors)


class MissingChoice:
    """无 Key 明确失败；零候选仍可以合法返回 No Match。"""

    async def choose(self, *args, **kwargs):
        raise FeatureUnavailable()


# 实现说明：build_container
# 根据配置选择具体 Adapter，并保留显式注入的应用 Port。
#
# 配置缺失时不隐式改用内存数据库或伪造模型；可选依赖保持 None。
# Jev 使用官方 SDK，超时和输入预算来自已校验 Settings。
# 默认 Unconfigured 实现是可观察失败边界，不是临时成功桩。
def build_container(
    settings: Settings,
    identity: IdentityVerifier | None = None,
    commands: BusinessCommands | None = None,
) -> Container:
    # 构造本地依赖不发网络请求，真实迁移和模型验收由显式命令触发。
    database = Database(settings) if settings.database_url else None
    choice = (
        JevChoiceProvider(
            settings.jev_api_key.get_secret_value(),
            settings.jev_model,
            timeout=settings.provider_timeout_seconds,
            input_bytes=settings.jev_input_bytes,
        )
        if settings.jev_api_key
        else None
    )
    ontology = (
        LLMOntologyBuilder(settings)
        if (settings.openai_api_key and settings.openai_model_name)
        else None
    )
    oauth = (
        GoogleOAuth(database.sessions, settings)
        if database
        and all(
            (
                settings.google_client_id,
                settings.google_client_secret,
                settings.encryption_key,
            )
        )
        else None
    )
    events = (
        EventWebhooks(database.sessions, settings.encryption_key)
        if database and settings.encryption_key
        else None
    )
    if settings.email_delivery_mode == "gmail":
        email = (
            GmailEmail(settings)
            if all(
                (
                    settings.gmail_sender,
                    settings.gmail_refresh_token,
                    settings.gmail_client_id,
                    settings.gmail_client_secret,
                )
            )
            else None
        )
    else:
        email = CaptureEmail(Path(settings.capture_directory))
    if commands is None:
        commands = (
            PersistentCommands(
                BusinessRepository(database.sessions),
                Tournament(choice or MissingChoice(), settings.selection_concurrency),
                settings.connect_timeout_seconds,
                settings.max_candidates,
            )
            if database
            else UnconfiguredCommands()
        )
    handlers = BusinessHandlers(database.sessions, ontology, email, events) if database else None
    return Container(
        settings,
        identity or oauth or UnconfiguredIdentity(),
        commands,
        database,
        choice,
        ontology,
        oauth,
        events,
        handlers,
    )
