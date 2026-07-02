import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.message_log_notifier import notify_message_log
from config.settings import Settings
from db.dal import message_log_dal, user_dal


def _source_chat_id(update: Update) -> int | None:
    if update.message:
        return update.message.chat.id
    if update.callback_query and update.callback_query.message:
        chat = getattr(update.callback_query.message, "chat", None)
        chat_id = getattr(chat, "id", None)
        if isinstance(chat_id, int):
            return chat_id
    return None


class ActionLoggerMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:

        result = await handler(event, data)

        if data.get("skip_action_log") or data.get("antiflood_dropped"):
            return result
        update = cast(Update, event)

        session: AsyncSession = data["session"]
        event_user: User | None = data.get("event_from_user")

        user_id: int | None = None
        telegram_username: str | None = None
        telegram_first_name: str | None = None
        content: str | None = None
        is_admin_event_flag: bool = False
        target_user_id_for_log: int | None = None

        if event_user:
            user_id = event_user.id
            telegram_username = event_user.username
            telegram_first_name = event_user.first_name
            if user_id in self.settings.ADMIN_IDS:
                is_admin_event_flag = True

        if is_admin_event_flag and not self.settings.LOG_ADMIN_ACTIONS:
            return result

        raw_update_snippet = None
        try:
            raw_update_snippet = update.model_dump_json(exclude_none=True, indent=None)[:1000]
        except AttributeError:
            raw_update_snippet = str(update)[:1000]
        except Exception:
            raw_update_snippet = str(update)[:1000]

        current_event_type = update.event_type

        if update.message:
            msg: Message = update.message
            if msg.text:
                content = msg.text
                if msg.text.startswith("/"):
                    current_event_type = f"command:{msg.text.split()[0]}"

            else:
                content = f"[{msg.content_type or 'unknown_content_type'}]"
                current_event_type = f"message:{msg.content_type or 'unknown'}"
        elif update.callback_query:
            cb: CallbackQuery = update.callback_query
            content = cb.data
            action_part = cb.data.split(":")[0] if cb.data and ":" in cb.data else cb.data
            current_event_type = f"callback:{action_part}"

        if user_id or current_event_type not in ["update"]:
            log_user_id_for_db = user_id
            if user_id:
                user_exists = await user_dal.get_user_by_id(session, user_id)
                if not user_exists:
                    logging.warning(
                        f"ActionLoggerMiddleware: User {user_id} not found in DB. Logging action with user_id=NULL."  # noqa: E501
                    )
                    log_user_id_for_db = None

            log_payload = {
                "user_id": log_user_id_for_db,
                "telegram_username": telegram_username,
                "telegram_first_name": telegram_first_name,
                "event_type": current_event_type,
                "content": content[:1000] if content else "N/A",
                "raw_update_preview": raw_update_snippet,
                "is_admin_event": is_admin_event_flag,
                "target_user_id": target_user_id_for_log,
                "timestamp": datetime.now(UTC),
            }
            try:
                await message_log_dal.create_message_log_no_commit(session, log_payload)
                if _source_chat_id(update) != self.settings.LOG_CHAT_ID:
                    bot_candidate = data.get("bot")
                    bot = bot_candidate if isinstance(bot_candidate, Bot) else None
                    await notify_message_log(log_payload, settings=self.settings, bot=bot)
            except Exception as e_log:
                logging.error(
                    f"ActionLoggerMiddleware: Failed to add log to session for user {user_id}, type {current_event_type}: {e_log}",  # noqa: E501
                    exc_info=True,
                )

        return result
