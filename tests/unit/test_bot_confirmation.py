import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Update

from bot.middlewares.confirmation import ConfirmationMiddleware, protect_confirmation


@pytest.mark.parametrize(
    "action",
    [
        "autorenew:confirm:5:0:bot",
        "tariff_change:apply:standard:d:bot",
        "tariff_change:pay:premium:49:bot",
        "trial_action:confirm_activate",
        "pm:delete:8:p1:bot",
        "pay_yk_use_saved:8:1:100:subscription",
        "broadcast_final_action:send",
        "promo_unlimited_validity",
        "bulk_promo_unlimited_validity",
        "promo_delete_confirm:8:1",
        "admin_ads:delete_confirm:8:1",
        "user_action:set_tariff:8:standard",
    ],
)
def test_confirmation_can_dispatch_once_on_the_bound_message(action):
    async def check():
        storage = MemoryStorage()
        dispatcher = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())
        root = Router()
        root.callback_query.outer_middleware(ConfirmationMiddleware())
        child = Router()
        root.include_router(child)
        dispatcher.include_router(root)
        mutations = []

        @child.callback_query(F.data == action)
        async def apply(callback):
            await asyncio.sleep(0)
            assert callback.bot is not None
            mutations.append(callback.data)

        @child.callback_query(F.data == "return")
        async def return_to_original_view(callback):
            return callback.data

        bot = Bot("123:testing")
        state = FSMContext(storage, StorageKey(bot_id=123, chat_id=42, user_id=42))
        i18n = SimpleNamespace(gettext=lambda lang, key: key)
        settings = SimpleNamespace(DEFAULT_LANGUAGE="en")

        async def tap(n, value, message_id=20):
            update = Update.model_validate(
                {
                    "update_id": n,
                    "callback_query": {
                        "id": str(n),
                        "chat_instance": "chat",
                        "from": {"id": 42, "first_name": "Test", "is_bot": False},
                        "data": value,
                        "message": {
                            "message_id": message_id,
                            "chat": {"id": 42, "type": "private"},
                            "date": 1_700_000_000,
                            "text": "Confirm",
                        },
                    },
                }
            )
            await dispatcher.feed_update(bot, update, settings=settings, i18n_instance=i18n)

        async def render():
            original = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Yes", callback_data=action)]]
            )
            protected = await protect_confirmation(state, original, message_id=20)
            token = protected.inline_keyboard[0][0].callback_data
            assert token and token.startswith("confirm:") and len(token.encode()) <= 64
            assert original.inline_keyboard[0][0].callback_data == action
            return token

        try:
            with patch.object(Bot, "__call__", new_callable=AsyncMock, return_value=True) as answer:
                old_token = await render()
                token = await render()
                assert token != old_token
                await tap(1, old_token)
                await tap(2, token, message_id=21)
                await tap(3, action)
                assert mutations == []
                await asyncio.gather(tap(4, token), tap(5, token))
                assert mutations == [action]
                token = await render()
                await tap(6, "return")
                await tap(7, token)
                assert mutations == [action]
                assert answer.await_count == 5
        finally:
            await bot.session.close()

    asyncio.run(check())
