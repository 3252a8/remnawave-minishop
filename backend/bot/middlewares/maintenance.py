"""Pause interactive bot traffic before registration, profile sync, or panel calls."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import TelegramObject, Update
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.account_roles import is_admin
from config.settings import Settings
from db.dal import user_dal

logger = logging.getLogger(__name__)


class MaintenanceMiddleware(BaseMiddleware):
    def __init__(
        self, settings: Settings, session_factory: sessionmaker, i18n_instance: JsonI18n
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.i18n = i18n_instance

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.settings.MAINTENANCE_MODE_ENABLED:
            return await handler(event, data)

        update = cast(Update, event)
        message = update.message or update.edited_message
        callback = update.callback_query
        inline = update.inline_query
        # These updates settle an already-started invoice. Dropping them can lose
        # a confirmed payment, a refund, or Telegram's checkout acknowledgement.
        if message and (message.successful_payment or message.refunded_payment):
            return await handler(event, data)
        if not message and not callback and not inline:
            return await handler(event, data)
        chat = (
            message.chat
            if message
            else callback.message.chat
            if callback and callback.message
            else None
        )
        actor = (
            message.from_user
            if message
            else callback.from_user
            if callback
            else inline.from_user
            if inline
            else None
        )
        if actor is None:
            return await handler(event, data)

        language = actor.language_code or self.settings.DEFAULT_LANGUAGE
        authorized = False
        try:
            async with self.session_factory() as session:
                user = await user_dal.get_user_by_telegram_id(session, actor.id)
                if user is not None:
                    language = user.language_code or language
                    authorized = not user.is_banned and await is_admin(session, int(user.user_id))
        except Exception:
            logger.exception("Could not resolve maintenance access for Telegram user %s", actor.id)
        if authorized:
            return await handler(event, data)

        data["skip_action_log"] = True
        if message and chat is not None and chat.type != "private":
            return None
        text = self.i18n.gettext(language, "maintenance_mode_message")
        try:
            if callback:
                await callback.answer(text=text, show_alert=True)
            elif inline:
                await inline.answer(results=[], cache_time=0, is_personal=True)
            elif message:
                await message.answer(text=text)
        except TelegramAPIError:
            logger.warning("Could not deliver maintenance notice to Telegram user %s", actor.id)
        return None
