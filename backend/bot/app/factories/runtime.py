from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from aiogram import Bot, Dispatcher
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n, get_i18n_instance
from bot.plugins import PluginContext, apply_plugin_locales
from bot.services.locale_override_service import load_locale_overrides
from config.settings import Settings
from db.database_setup import init_db, init_db_connection

from .build_services import build_core_services
from .core_services import CoreServices
from .telegram_bot import create_telegram_bot


@dataclass(frozen=True)
class RuntimeBootstrap:
    settings: Settings
    session_factory: sessionmaker
    bot: Bot | None
    i18n: JsonI18n


@dataclass(frozen=True)
class CoreRuntime:
    bootstrap: RuntimeBootstrap
    bot_username: str
    core_services: CoreServices
    plugin_context: PluginContext

    @property
    def services(self) -> dict[str, object]:
        return self.plugin_context.services


async def build_runtime_bootstrap(settings: Settings) -> RuntimeBootstrap:
    session_factory = cast(sessionmaker, init_db_connection(settings))
    await init_db(settings, session_factory)

    bot = create_telegram_bot(settings) if settings.TELEGRAM_ENABLED else None
    i18n = get_i18n_instance(path="locales", default=settings.DEFAULT_LANGUAGE)
    apply_plugin_locales(settings, i18n)
    await load_locale_overrides(i18n, session_factory)
    return RuntimeBootstrap(
        settings=settings,
        session_factory=session_factory,
        bot=bot,
        i18n=i18n,
    )


def build_core_runtime(
    runtime: RuntimeBootstrap,
    *,
    bot_username: str,
    dispatcher: Dispatcher | None = None,
) -> CoreRuntime:
    core_services = build_core_services(
        runtime.settings,
        runtime.bot,
        runtime.session_factory,
        runtime.i18n,
        bot_username,
    )
    plugin_context = build_plugin_context(runtime, core_services, dispatcher=dispatcher)
    return CoreRuntime(
        bootstrap=runtime,
        bot_username=bot_username,
        core_services=core_services,
        plugin_context=plugin_context,
    )


def build_plugin_context(
    runtime: RuntimeBootstrap,
    core_services: CoreServices,
    *,
    dispatcher: Dispatcher | None = None,
) -> PluginContext:
    return PluginContext(
        settings=runtime.settings,
        session_factory=runtime.session_factory,
        bot=runtime.bot,
        i18n=runtime.i18n,
        dispatcher=dispatcher,
        services=core_services.as_dict(),
    )
