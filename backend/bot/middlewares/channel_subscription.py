import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    Update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import get_channel_subscription_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.utils.channel_subscription import (
    normalize_required_channel_id,
    resolve_required_channel_link,
)
from config.settings import Settings
from db.dal import user_dal


class ChannelSubscriptionMiddleware(BaseMiddleware):
    """
    Blocks access to handlers for users who have not yet passed the required channel subscription check.
    The /start command is allowed through so that the handler can re-run the verification.
    """  # noqa: E501

    def __init__(self, settings: Settings, i18n_instance: JsonI18n):
        super().__init__()
        self.settings = settings
        self.i18n_main_instance = i18n_instance

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = cast(Update, event)

        required_channel_id = normalize_required_channel_id(self.settings.REQUIRED_CHANNEL_ID)
        if not required_channel_id:
            return await handler(event, data)

        event_user = data.get("event_from_user")
        if not event_user or event_user.id in self.settings.ADMIN_IDS:
            return await handler(event, data)

        callback_query = update.callback_query
        if (
            callback_query
            and callback_query.data
            and callback_query.data == "channel_subscription:verify"
        ):
            return await handler(event, data)

        # Allow /start to reach the handler so the check can be re-run.
        message_object: Message | None = update.message
        if message_object and message_object.text and message_object.text.startswith("/start"):
            return await handler(event, data)

        session: AsyncSession = data["session"]
        try:
            db_user = await user_dal.get_user_by_id(session, event_user.id)
        except Exception as db_error:
            logging.error(
                "ChannelSubscriptionMiddleware: failed to fetch user %s: %s",
                event_user.id,
                db_error,
                exc_info=True,
            )
            return await handler(event, data)

        if not db_user:
            return await handler(event, data)

        if (
            db_user.channel_subscription_verified
            and db_user.channel_subscription_verified_for == required_channel_id
        ):
            return await handler(event, data)

        i18n_payload: dict[str, Any] = data.get("i18n_data", {})
        current_lang = str(i18n_payload.get("current_language") or self.settings.DEFAULT_LANGUAGE)
        raw_i18n = i18n_payload.get("i18n_instance")
        i18n_instance: JsonI18n | None = (
            raw_i18n if isinstance(raw_i18n, JsonI18n) else self.i18n_main_instance
        )

        def translate(key: str) -> str:
            if i18n_instance:
                return str(i18n_instance.gettext(current_lang, key))
            return key

        bot_instance = data.get("bot") or data.get("bot_instance")
        channel_link = await resolve_required_channel_link(
            bot_instance,
            required_channel_id,
            self.settings.REQUIRED_CHANNEL_LINK,
        )
        keyboard = (
            get_channel_subscription_keyboard(current_lang, i18n_instance, channel_link)
            if i18n_instance
            else None
        )
        prompt_text = translate("channel_subscription_required")

        if update.callback_query:
            await self._handle_callback(update.callback_query, prompt_text, keyboard, data)
            return

        if message_object:
            await message_object.answer(prompt_text, reply_markup=keyboard)
        else:
            bot_instance = data["bot"]
            await bot_instance.send_message(
                chat_id=event_user.id,
                text=prompt_text,
                reply_markup=keyboard,
            )
        return

    async def _handle_callback(
        self,
        callback: CallbackQuery,
        prompt_text: str,
        keyboard: InlineKeyboardMarkup | None,
        data: dict[str, Any],
    ) -> None:
        with contextlib.suppress(Exception):
            await callback.answer(prompt_text, show_alert=True)

        if callback.message:
            try:
                await callback.message.answer(prompt_text, reply_markup=keyboard)
            except Exception as send_error:
                logging.error(
                    "ChannelSubscriptionMiddleware: failed to send prompt for callback in chat %s: %s",  # noqa: E501
                    callback.message.chat.id,
                    send_error,
                    exc_info=True,
                )
        else:
            bot_instance = data["bot"]
            await bot_instance.send_message(
                chat_id=callback.from_user.id,
                text=prompt_text,
                reply_markup=keyboard,
            )
