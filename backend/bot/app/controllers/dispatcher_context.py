from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import cast

from aiogram import Bot, Dispatcher
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.utils.message_queue import MessageQueueManager
from config.settings import Settings

BOT_KEY = "bot_instance"
SETTINGS_KEY = "settings"
I18N_KEY = "i18n_instance"
SESSION_FACTORY_KEY = "async_session_factory"
BOT_USERNAME_KEY = "bot_username"
QUEUE_MANAGER_KEY = "queue_manager"


def workflow_data_for(dp: object) -> Mapping[str, object]:
    if isinstance(dp, Mapping):
        return dp
    workflow_data = getattr(dp, "workflow_data", {})
    if isinstance(workflow_data, Mapping):
        return workflow_data
    return {}


def _set_value(dp: Dispatcher, key: str, value: object) -> None:
    dp[key] = value


def get_dispatcher_bot(dp: object) -> Bot:
    return cast(Bot, workflow_data_for(dp)[BOT_KEY])


def get_dispatcher_settings(dp: object) -> Settings:
    return cast(Settings, workflow_data_for(dp)[SETTINGS_KEY])


def get_dispatcher_i18n(dp: object) -> JsonI18n:
    return cast(JsonI18n, workflow_data_for(dp)[I18N_KEY])


def get_dispatcher_session_factory(dp: object) -> sessionmaker:
    return cast(sessionmaker, workflow_data_for(dp)[SESSION_FACTORY_KEY])


def get_dispatcher_service(dp: object, key: str) -> object | None:
    return workflow_data_for(dp).get(key)


def iter_dispatcher_services(
    dp: object,
    keys: Iterable[str],
) -> Iterator[tuple[str, object]]:
    workflow_data = workflow_data_for(dp)
    for key in keys:
        if key in workflow_data:
            yield key, workflow_data[key]


def set_dispatcher_core_context(
    dp: Dispatcher,
    *,
    bot: Bot | None,
    settings: Settings,
    i18n: JsonI18n,
    session_factory: sessionmaker,
) -> None:
    if bot is not None:
        _set_value(dp, BOT_KEY, bot)
    _set_value(dp, SETTINGS_KEY, settings)
    _set_value(dp, I18N_KEY, i18n)
    _set_value(dp, SESSION_FACTORY_KEY, session_factory)


def set_dispatcher_services(dp: Dispatcher, services: Mapping[str, object]) -> None:
    for key, service in services.items():
        _set_value(dp, key, service)


def set_dispatcher_bot_username(dp: Dispatcher, username: str) -> None:
    _set_value(dp, BOT_USERNAME_KEY, username)


def get_dispatcher_bot_username(dp: object) -> str:
    value = workflow_data_for(dp).get(BOT_USERNAME_KEY)
    return str(value or "")


def set_dispatcher_queue_manager(dp: Dispatcher, queue_manager: MessageQueueManager) -> None:
    _set_value(dp, QUEUE_MANAGER_KEY, queue_manager)
