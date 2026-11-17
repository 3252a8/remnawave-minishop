from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, TelegramObject

_CHECKOUT_SCREENS = (
    "subscribe_period:",
    "tariff:select:",
    "tariff:period:",
    "tariff:package:",
    "tariff:premium_package:",
    "tariff_topup:list",
    "hwid_devices:list",
    "hwid_devices:package:",
    "hwid_devices:renewal_package:",
    "tariff_change:",
    "pm:",
    "toggle_autorenew:",
    "autorenew:confirm:",
)


class CheckoutNavigationMiddleware(BaseMiddleware):
    """Checkout screens and their return buttons leave any chat input flow."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if (
            isinstance(event, CallbackQuery)
            and (event.data or "").startswith(_CHECKOUT_SCREENS)
            and isinstance(state, FSMContext)
            and data.get("raw_state") is not None
        ):
            await state.clear()
            data["raw_state"] = None
        return await handler(event, data)
