import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Union, cast

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import (
    AiogramError,
    TelegramAPIError,
    TelegramForbiddenError,
)
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject, Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import get_user_banned_keyboard
from config.settings import Settings
from db.dal import user_dal

from .i18n import JsonI18n


class BanCheckMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, i18n_instance: JsonI18n):
        super().__init__()
        self.settings = settings
        self.i18n_main_instance = i18n_instance

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        update = cast(Update, event)

        session: AsyncSession = data["session"]
        event_user: Optional[User] = data.get("event_from_user")
        bot_instance: Bot = data["bot"]

        if not event_user:
            return await handler(event, data)

        if event_user.id in self.settings.ADMIN_IDS:
            return await handler(event, data)

        try:
            db_user_model = await user_dal.get_user_by_id(session, event_user.id)
        except Exception as e_db:
            logging.error(
                f"BanCheckMiddleware: DB error fetching user {event_user.id}: {e_db}", exc_info=True
            )
            return await handler(event, data)

        if db_user_model and db_user_model.is_banned:
            logging.info(
                f"User {event_user.id} ({event_user.username or 'NoUsername'}) is banned. Blocking access."  # noqa: E501
            )

            i18n_data_from_event = data.get("i18n_data", {})
            current_lang = i18n_data_from_event.get(
                "current_language", self.settings.DEFAULT_LANGUAGE
            )
            i18n_to_use: Optional[JsonI18n] = i18n_data_from_event.get(
                "i18n_instance", self.i18n_main_instance
            )

            ban_message_text = "You are banned. Please contact support."
            keyboard: Optional[InlineKeyboardMarkup] = None
            support_link = self.settings.support_settings.link

            if i18n_to_use:
                _ = lambda k, **kw: i18n_to_use.gettext(current_lang, k, **kw)
                ban_message_text = _("user_is_banned")
                keyboard = get_user_banned_keyboard(support_link, current_lang, i18n_to_use)
            elif support_link:
                from aiogram.utils.keyboard import InlineKeyboardBuilder

                builder = InlineKeyboardBuilder()
                builder.button(text="Support", url=support_link)
                keyboard = builder.as_markup()

            actual_event_object: Optional[Union[Message, CallbackQuery]] = None
            if update.message:
                actual_event_object = update.message
            elif update.callback_query:
                actual_event_object = update.callback_query

            try:
                if isinstance(actual_event_object, Message):
                    await actual_event_object.answer(ban_message_text, reply_markup=keyboard)
                elif isinstance(actual_event_object, CallbackQuery):
                    await actual_event_object.answer(ban_message_text, show_alert=True)
                    if isinstance(actual_event_object.message, Message):
                        try:
                            await actual_event_object.message.edit_text(
                                ban_message_text, reply_markup=keyboard
                            )
                        except (TelegramAPIError, AiogramError):
                            await bot_instance.send_message(
                                actual_event_object.from_user.id,
                                ban_message_text,
                                reply_markup=keyboard,
                            )
                    else:
                        await bot_instance.send_message(
                            actual_event_object.from_user.id,
                            ban_message_text,
                            reply_markup=keyboard,
                        )
                else:
                    await bot_instance.send_message(
                        event_user.id, ban_message_text, reply_markup=keyboard
                    )
                logging.info(f"Ban notification sent to user {event_user.id}.")
            except TelegramForbiddenError:
                logging.warning(f"BanCheck: Bot is blocked by user {event_user.id}.")
            except Exception as e_send:
                logging.error(
                    f"BanCheck: Failed to notify banned user {event_user.id}: {type(e_send).__name__} - {e_send}",  # noqa: E501
                    exc_info=True,
                )

            return
        return await handler(event, data)
