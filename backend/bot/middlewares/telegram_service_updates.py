"""Keep service updates transactional without running user access flows."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.services.telegram_notifications import (
    mark_telegram_notifications_enabled_for_telegram_user,
)

logger = logging.getLogger(__name__)


class UserInteractionMiddleware(BaseMiddleware):
    def __init__(self, middleware: BaseMiddleware):
        self.middleware = middleware

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and (event.my_chat_member or event.chat_member):
            return await handler(event, data)
        return await self.middleware(handler, event, data)


class TelegramInteractionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and event.message:
            message = event.message
            if (
                message.chat.type == "private"
                and message.from_user
                and not message.from_user.is_bot
            ):
                await mark_telegram_notifications_enabled_for_telegram_user(
                    data["session"],
                    message.chat.id,
                    checked_at=message.date,
                    update_id=event.update_id,
                )
                logger.info("metric telegram_private_interactions_total=1")
        return await handler(event, data)
