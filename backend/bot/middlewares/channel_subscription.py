from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.handlers.user.start_channel import ensure_required_channel_subscription
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings


class ChannelSubscriptionMiddleware(BaseMiddleware):
    """Reconcile channel membership on protected messages and callbacks."""

    def __init__(self, settings: Settings, i18n_instance: JsonI18n):
        self.settings = settings
        self.i18n_main_instance = i18n_instance

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        interaction = event.callback_query or event.message
        # Payment acknowledgements and inline updates are not user navigation.
        if interaction is None or (
            event.message and (event.message.successful_payment or event.message.refunded_payment)
        ):
            return await handler(event, data)
        if event.message and event.message.text and event.message.text.startswith("/start"):
            return await handler(event, data)
        if event.callback_query and (
            event.callback_query.data == "channel_subscription:verify"
            or str(event.callback_query.data or "").startswith("gift:claim:")
        ):
            return await handler(event, data)
        payload = data.get("i18n_data", {})
        if await ensure_required_channel_subscription(
            interaction,
            self.settings,
            self.i18n_main_instance,
            payload.get("current_language", self.settings.DEFAULT_LANGUAGE),
            data["session"],
        ):
            return await handler(event, data)
        return None
