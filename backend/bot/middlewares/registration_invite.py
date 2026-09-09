import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.registration_invite_gate import registration_invite_only_enabled
from config.settings import Settings
from db.dal import user_dal

from .i18n import JsonI18n

logger = logging.getLogger(__name__)

_START_COMMAND_RE = re.compile(
    r"^/start(?:@(?P<username>[A-Za-z0-9_]{1,32}))?(?:\s|$)",
    re.IGNORECASE,
)


def _is_start_command(message: Message | None, bot_username: object) -> bool:
    text = str(getattr(message, "text", "") or "")
    match = _START_COMMAND_RE.match(text)
    if not match:
        return False
    mentioned_username = match.group("username")
    if not mentioned_username:
        return True
    expected_username = str(bot_username or "").strip().lstrip("@")
    return bool(expected_username) and mentioned_username.casefold() == expected_username.casefold()


class RegistrationInviteMiddleware(BaseMiddleware):
    """Keep unregistered users out of public Telegram entry points.

    ``/start`` remains available because the start flow validates referral and
    partner invitations before creating a user. Admins and existing accounts
    continue through unchanged.
    """

    def __init__(self, settings: Settings, i18n_instance: JsonI18n):
        super().__init__()
        self.settings = settings
        self.i18n = i18n_instance

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not registration_invite_only_enabled(self.settings):
            return await handler(event, data)

        update = cast(Update, event)
        event_user: User | None = data.get("event_from_user")
        if not event_user or event_user.id in self.settings.ADMIN_IDS:
            return await handler(event, data)

        if not (update.message or update.callback_query or update.inline_query):
            return await handler(event, data)

        if _is_start_command(update.message, data.get("bot_username")):
            return await handler(event, data)

        session = cast(AsyncSession | None, data.get("session"))
        registered = False
        if session is None:
            logger.error(
                "RegistrationInviteMiddleware: no DB session for user %s; blocking access.",
                event_user.id,
            )
        else:
            try:
                db_user = await user_dal.get_user_by_telegram_id(session, event_user.id)
                if not db_user:
                    db_user = await user_dal.get_user_by_id(session, event_user.id)
                registered = db_user is not None
            except Exception as db_error:
                logger.exception(
                    "RegistrationInviteMiddleware: failed to check user %s: %s",
                    event_user.id,
                    db_error,
                )

        if registered:
            return await handler(event, data)

        i18n_data: dict[str, Any] = data.get("i18n_data", {})
        current_language = str(i18n_data.get("current_language") or self.settings.DEFAULT_LANGUAGE)
        prompt = self.i18n.gettext(current_language, "registration_invite_required")

        if update.message:
            await update.message.answer(prompt)
        elif update.callback_query:
            await update.callback_query.answer(prompt, show_alert=True)
        elif update.inline_query:
            await update.inline_query.answer(results=[], cache_time=1, is_personal=True)
        return None
