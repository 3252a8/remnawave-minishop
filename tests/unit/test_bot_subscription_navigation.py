import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.admin.user_management_cards import get_user_card_keyboard, user_card_back_callback
from bot.handlers.user.subscription import core_autorenew, core_topup
from bot.keyboards.inline.user_keyboards_context import (
    payment_methods_back_callback,
    payment_options_back_callback,
    payment_receipt_back_callback,
)
from bot.keyboards.inline.user_keyboards_payments import (
    get_autorenew_confirm_keyboard,
    get_back_to_payment_method_details_keyboard,
    get_bind_url_keyboard,
    get_payment_method_delete_confirm_keyboard,
    get_payment_method_details_keyboard,
    get_payment_methods_list_keyboard,
)
from bot.payment_providers.yookassa.payment_methods import _payment_method_navigation


@pytest.mark.parametrize("context", [None, "bot"])
def test_saved_cards_keep_page_from_details_history_and_binding(context):
    i18n = SimpleNamespace(gettext=lambda lang, key: key)
    cards = [(str(i), f"Card {i}") for i in range(1, 8)]
    methods = get_payment_methods_list_keyboard(cards, 1, "en", i18n, context=context)
    target = methods.inline_keyboard[0][0].callback_data
    assert _payment_method_navigation(target) == ("pm:view:6", 1, context)
    suffix = ":bot" if context else ""
    assert methods.inline_keyboard[-1][0].callback_data == (
        "main_action:bot_my_subscription" if context else "main_action:my_subscription"
    )
    details = get_payment_method_details_keyboard("6", "en", i18n, page=1, context=context)
    assert details.inline_keyboard[-1][0].callback_data == f"pm:list:1{suffix}"
    history = get_back_to_payment_method_details_keyboard("6", "en", i18n, page=1, context=context)
    assert history.inline_keyboard[0][0].callback_data == target
    delete = get_payment_method_delete_confirm_keyboard("6", "en", i18n, page=1, context=context)
    assert delete.inline_keyboard[0][1].callback_data == target
    bind = get_bind_url_keyboard("https://example.com", "en", i18n, page=1, context=context)
    assert bind.inline_keyboard[-1][0].callback_data == f"pm:list:1{suffix}"


@pytest.mark.parametrize(
    ("origin", "target"),
    [
        ("b2", "admin_action:view_banned:2"),
        ("l3", "admin_action:users_list:3"),
        ("s", "admin_action:users_search_prompt"),
        ("i25.2.l3", "ui:25:2:l3"),
    ],
)
def test_admin_card_refresh_keeps_original_screen(origin, target):
    i18n = SimpleNamespace(gettext=lambda lang, key: key)
    markup = get_user_card_keyboard(42, i18n, "en", origin=origin).as_markup()
    callback = SimpleNamespace(data=None, message=SimpleNamespace(reply_markup=markup))
    assert user_card_back_callback(callback, 42) == f"uc:42:{origin}"
    assert markup.inline_keyboard[-1][-1].callback_data == target


@pytest.mark.parametrize("suffix", ["", ":bot"])
@pytest.mark.parametrize(
    ("sale_mode", "provider_back", "options_back"),
    [
        ("topup@plan", "tariff:package:plan:10", "tariff_topup:list"),
        ("premium_topup@plan", "tariff:premium_package:plan:10", "tariff_topup:list"),
        ("hwid_devices@plan", "hwid_devices:package:plan:10", "hwid_devices:list"),
        ("hwid_devices@plan|s", "hwid_devices:package:plan:10:s", "hwid_devices:list:s"),
        (
            "traffic_package@plan|sw",
            "tariff:package:plan:10{suffix}:sw",
            "tariff_change:select:plan",
        ),
        ("subscription@plan|sw", "tariff:period:plan:10{suffix}:sw", "tariff_change:select:plan"),
        ("tariff_upgrade@plan", "tariff_change:pay:plan:150.0", None),
    ],
)
def test_checkout_back_preserves_origin(sale_mode, provider_back, options_back, suffix):
    sale_mode += "|bot" if suffix else ""
    expected = (
        provider_back.format(suffix=suffix)
        if "{suffix}" in provider_back
        else provider_back + suffix
    )
    price = 150.0 if sale_mode.startswith("tariff_upgrade") else None
    assert payment_methods_back_callback("10", sale_mode, price=price) == expected
    if options_back:
        assert payment_options_back_callback(sale_mode) == options_back + suffix


@pytest.mark.parametrize(
    ("sale_mode", "callback"),
    [
        ("premium_topup@plan|t", "main_action:my_subscription:keep"),
        ("topup@plan|bot|t", "main_action:bot_my_subscription:keep"),
        ("tariff_upgrade@plan|bot|t", "main_action:bot_my_subscription:keep"),
        ("subscription@plan|sw", "main_action:my_subscription:keep"),
        ("traffic_package@plan|sw|bot", "main_action:bot_my_subscription:keep"),
        ("hwid_devices@plan|s|bot", "main_action:bot_my_subscription:keep"),
        ("hwid_devices@plan|t", "main_action:my_devices:keep"),
        ("hwid_devices@plan|t|bot", "main_action:my_devices:keep:bot"),
        ("subscription@plan|bot", None),
        ("topup@plan", None),
        ("subscription@plan|cs|bot", "main_action:bot_my_subscription:keep"),
    ],
)
def test_receipt_back_opens_origin_without_replacing_receipt(sale_mode, callback):
    assert payment_receipt_back_callback(sale_mode) == callback


@pytest.mark.parametrize(
    ("context", "status", "menu"),
    [
        (None, "main_action:my_subscription", "back_to_main"),
        ("bot", "main_action:bot_my_subscription", "bot_interface"),
    ],
)
@pytest.mark.parametrize("enable", [False, True])
def test_autorenew_yes_and_no_preserve_menu(context, status, menu, enable):
    i18n = SimpleNamespace(gettext=lambda lang, key: key)
    yes, no = get_autorenew_confirm_keyboard(
        enable, 42, "en", i18n, context=context
    ).inline_keyboard[0]
    suffix = f":{context}" if context else ""
    assert yes.callback_data == f"autorenew:confirm:42:{int(enable)}{suffix}"
    assert no.callback_data == status

    @asynccontextmanager
    async def lock(*args, **kwargs):
        yield True

    callback = SimpleNamespace(
        data=yes.callback_data, from_user=SimpleNamespace(id=1), answer=AsyncMock()
    )
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(user_id=2, subscription_id=42)
    settings = SimpleNamespace(DEFAULT_LANGUAGE="en")
    with (
        patch.object(core_autorenew, "require_telegram_account_id", AsyncMock(return_value=2)),
        patch.object(core_autorenew, "renewal_provider", return_value="balance"),
        patch.object(core_autorenew, "auto_renew_toggle_allowed", return_value=True),
        patch.object(core_autorenew, "redis_lock", lock),
        patch.object(
            core_autorenew, "stop_provider_managed_recurrence", AsyncMock(return_value=True)
        ),
        patch.object(core_autorenew.subscription_dal, "set_auto_renew", AsyncMock()) as save,
        patch.object(core_autorenew, "my_subscription_command_handler", AsyncMock()) as show,
    ):
        asyncio.run(
            core_autorenew.confirm_autorenew_handler(
                callback, settings, {}, session, MagicMock(), MagicMock(), MagicMock()
            )
        )
    save.assert_awaited_once_with(session, 42, enable)
    assert show.await_args.kwargs["back_callback"] == f"main_action:{menu}"


@pytest.mark.parametrize(
    ("callback_mode", "mode", "suffix", "menu"),
    [
        ("recalc_days", "recalc_days", "", "back_to_main"),
        ("d", "recalc_days", ":bot", "bot_interface"),
        ("g", "convert_days_to_gb", ":bot", "bot_interface"),
    ],
)
def test_applied_tariff_change_reopens_originating_subscription(callback_mode, mode, suffix, menu):
    callback = SimpleNamespace(
        data=f"tariff_change:apply:plan:{callback_mode}{suffix}",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
        bot=MagicMock(),
    )
    settings = SimpleNamespace(DEFAULT_LANGUAGE="en")
    session = AsyncMock()
    service = MagicMock(switch_tariff_without_payment=AsyncMock(return_value=True))
    with (
        patch.object(core_topup, "require_telegram_account_id", AsyncMock(return_value=2)),
        patch.object(core_topup, "my_subscription_command_handler", AsyncMock()) as show,
    ):
        asyncio.run(
            core_topup.tariff_change_apply_callback(callback, {}, settings, service, session)
        )
    service.switch_tariff_without_payment.assert_awaited_once_with(session, 2, "plan", mode)
    assert show.await_args.kwargs["back_callback"] == f"main_action:{menu}"
