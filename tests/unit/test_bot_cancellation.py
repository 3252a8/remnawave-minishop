import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, User

from bot.handlers.admin import ads, broadcast
from bot.handlers.admin.promo import manage
from bot.handlers.admin.promo.draft import accept_promo_validity_callback
from bot.handlers.user import trial_captcha_handler
from bot.handlers.user.subscription import core_device_names
from bot.middlewares.checkout_navigation import CheckoutNavigationMiddleware
from bot.states.admin_states import AdminStates


def _i18n():
    return {
        "current_language": "en",
        "i18n_instance": SimpleNamespace(gettext=lambda lang, key: key),
    }


@pytest.mark.parametrize(
    "target", ["pm:view:7:p1:bot", "tariff_topup:list:bot", "hwid_devices:list:s:bot"]
)
def test_checkout_return_clears_pending_chat_input(target):
    async def check():
        state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))
        await state.set_state(AdminStates.waiting_for_user_search)
        await state.update_data(query="discard this")
        event = CallbackQuery(
            id="cb",
            from_user=User(id=2, first_name="Test", is_bot=False),
            chat_instance="chat",
            data=target,
        )

        async def render(_event, data):
            assert data["raw_state"] is None
            assert await state.get_state() is None
            assert await state.get_data() == {}

        await CheckoutNavigationMiddleware()(
            render,
            event,
            {
                "state": state,
                "raw_state": AdminStates.waiting_for_user_search.state,
            },
        )

    asyncio.run(check())


@pytest.mark.parametrize("stale", [False, True])
def test_broadcast_cancel_only_leaves_current_confirmation(stale):
    message = SimpleNamespace(message_id=15, edit_text=AsyncMock())
    callback = SimpleNamespace(
        data="broadcast_final_action:cancel", message=message, answer=AsyncMock()
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"broadcast_confirmation_message_id": 7 if stale else 15}),
        clear=AsyncMock(),
    )
    asyncio.run(
        broadcast.confirm_broadcast_callback_handler(
            callback,
            state,
            _i18n(),
            MagicMock(),
            SimpleNamespace(DEFAULT_LANGUAGE="en"),
            AsyncMock(),
        )
    )
    if stale:
        state.clear.assert_not_awaited()
        message.edit_text.assert_not_awaited()
    else:
        state.clear.assert_awaited_once()
        assert message.edit_text.await_args.args[0] == "admin_system_functions_section"


@pytest.mark.parametrize(
    ("context", "screen"), [(None, "send_main_menu"), ("bot", "send_bot_interface_menu")]
)
def test_trial_cancel_returns_to_origin_after_discarding_challenge(context, screen):
    settings = SimpleNamespace(TELEGRAM_BOT_MENU_DISABLED=False)
    callback = SimpleNamespace(data="trial_captcha:cancel:abc", message=None, answer=AsyncMock())
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=trial_captcha_handler.TrialCaptchaState.answer.state),
        get_data=AsyncMock(return_value={"trial_challenge_id": "abc", "trial_context": context}),
        clear=AsyncMock(),
    )
    service, session = MagicMock(), AsyncMock()
    with patch.object(trial_captcha_handler, screen, AsyncMock()) as show:
        asyncio.run(
            trial_captcha_handler.cancel_trial_captcha(
                callback, state, settings, service, session, {}
            )
        )
    state.clear.assert_awaited_once()
    show.assert_awaited_once_with(callback, settings, {}, service, session)


def test_renaming_cancel_restores_device_picker():
    callback = SimpleNamespace(data="rename_device:cancel:bot")
    state, settings, session, service, panel = (
        AsyncMock(),
        MagicMock(),
        AsyncMock(),
        MagicMock(),
        MagicMock(),
    )
    with patch.object(core_device_names, "rename_device_list_callback", AsyncMock()) as show:
        asyncio.run(
            core_device_names.rename_device_cancel_callback(
                callback, state, settings, {}, session, service, panel
            )
        )
    show.assert_awaited_once_with(callback, settings, {}, session, service, panel, state)


@pytest.mark.parametrize("feature", ["promo", "ads"])
def test_abandoned_admin_delete_does_not_mutate_record(feature):
    message = SimpleNamespace(message_id=91, edit_text=AsyncMock())
    callback = SimpleNamespace(message=message, answer=AsyncMock())
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=None),
        get_data=AsyncMock(return_value={}),
        clear=AsyncMock(),
    )
    settings, session = SimpleNamespace(DEFAULT_LANGUAGE="en"), AsyncMock()
    if feature == "promo":
        callback.data = "promo_delete_confirm:7:1"
        with patch.object(manage.promo_code_dal, "delete_promo_code", AsyncMock()) as delete:
            asyncio.run(manage.promo_delete_handler(callback, _i18n(), settings, session, state))
    else:
        callback.data = "admin_ads:delete_confirm:7:1"
        with patch.object(ads.ad_dal, "delete_campaign", AsyncMock()) as delete:
            asyncio.run(ads.ads_delete_confirm(callback, settings, _i18n(), session, state))
    delete.assert_not_awaited()
    session.commit.assert_not_awaited()
    callback.answer.assert_awaited_once_with("error_try_again", show_alert=True)


def test_previous_validity_buttons_cannot_finish_new_activation_code_draft():
    callback = SimpleNamespace(message=SimpleNamespace(message_id=7), answer=AsyncMock())
    settings = SimpleNamespace(DEFAULT_LANGUAGE="en")
    assert not asyncio.run(
        accept_promo_validity_callback(
            callback,
            {"promo_validity_message_id": 9},
            _i18n(),
            settings,
        )
    )
    callback.answer.assert_awaited_once_with("error_try_again", show_alert=True)
