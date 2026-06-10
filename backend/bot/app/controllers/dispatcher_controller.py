from typing import Dict

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.orm import sessionmaker

try:
    from aiogram.fsm.storage.redis import RedisStorage
except ModuleNotFoundError:  # pragma: no cover - dependency is installed in Docker image
    RedisStorage = None  # type: ignore[assignment]

from bot.middlewares.action_logger_middleware import ActionLoggerMiddleware
from bot.middlewares.ban_check_middleware import BanCheckMiddleware
from bot.middlewares.channel_subscription import ChannelSubscriptionMiddleware
from bot.middlewares.db_session import DBSessionMiddleware
from bot.middlewares.i18n import I18nMiddleware, get_i18n_instance
from bot.middlewares.profile_sync import ProfileSyncMiddleware
from bot.middlewares.update_antiflood import UpdateAntiFloodMiddleware
from config.settings import Settings


def build_dispatcher(
    settings: Settings, async_session_factory: sessionmaker
) -> tuple[Dispatcher, Bot, Dict]:
    storage = (
        RedisStorage.from_url(settings.REDIS_URL)
        if settings.REDIS_URL and RedisStorage is not None
        else MemoryStorage()
    )
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=settings.BOT_TOKEN, default=default_props)

    dp = Dispatcher(storage=storage, settings=settings, bot_instance=bot)

    i18n_instance = get_i18n_instance(path="locales", default=settings.DEFAULT_LANGUAGE)

    dp["i18n_instance"] = i18n_instance
    dp["async_session_factory"] = async_session_factory

    dp.update.outer_middleware(UpdateAntiFloodMiddleware(settings=settings))
    dp.update.outer_middleware(DBSessionMiddleware(async_session_factory))
    dp.update.outer_middleware(I18nMiddleware(i18n=i18n_instance, settings=settings))
    dp.update.outer_middleware(ProfileSyncMiddleware())
    dp.update.outer_middleware(BanCheckMiddleware(settings=settings, i18n_instance=i18n_instance))
    dp.update.outer_middleware(
        ChannelSubscriptionMiddleware(settings=settings, i18n_instance=i18n_instance)
    )
    dp.update.outer_middleware(ActionLoggerMiddleware(settings=settings))

    return dp, bot, {"i18n_instance": i18n_instance}
