from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.orm import sessionmaker

if TYPE_CHECKING:
    from aiogram.fsm.storage.redis import RedisStorage
else:
    try:
        from aiogram.fsm.storage.redis import RedisStorage
    except ModuleNotFoundError:  # pragma: no cover - dependency is installed in Docker image
        RedisStorage = None

from bot.middlewares.action_logger_middleware import ActionLoggerMiddleware
from bot.middlewares.ban_check_middleware import BanCheckMiddleware
from bot.middlewares.channel_subscription import ChannelSubscriptionMiddleware
from bot.middlewares.db_session import DBSessionMiddleware
from bot.middlewares.i18n import I18nMiddleware, JsonI18n
from bot.middlewares.profile_sync import ProfileSyncMiddleware
from bot.middlewares.update_antiflood import UpdateAntiFloodMiddleware
from config.settings import Settings

from .dispatcher_context import set_dispatcher_core_context


def build_dispatcher(
    settings: Settings,
    async_session_factory: sessionmaker,
    *,
    bot: Bot,
    i18n_instance: JsonI18n,
) -> Dispatcher:
    storage = (
        RedisStorage.from_url(settings.REDIS_URL)
        if settings.REDIS_URL and RedisStorage is not None
        else MemoryStorage()
    )

    dp = Dispatcher(storage=storage)
    set_dispatcher_core_context(
        dp,
        bot=bot,
        settings=settings,
        i18n=i18n_instance,
        session_factory=async_session_factory,
    )

    dp.update.outer_middleware(UpdateAntiFloodMiddleware(settings=settings))
    dp.update.outer_middleware(DBSessionMiddleware(async_session_factory))
    dp.update.outer_middleware(I18nMiddleware(i18n=i18n_instance, settings=settings))
    dp.update.outer_middleware(ProfileSyncMiddleware())
    dp.update.outer_middleware(BanCheckMiddleware(settings=settings, i18n_instance=i18n_instance))
    dp.update.outer_middleware(
        ChannelSubscriptionMiddleware(settings=settings, i18n_instance=i18n_instance)
    )
    dp.update.outer_middleware(ActionLoggerMiddleware(settings=settings))

    return dp
