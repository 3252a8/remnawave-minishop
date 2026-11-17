import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.user.subscription import core_autorenew, core_topup
from bot.keyboards.inline.user_keyboards_context import (
    payment_methods_back_callback,
    payment_options_back_callback,
    payment_receipt_back_callback,
)
from bot.keyboards.inline.user_keyboards_payments import get_autorenew_confirm_keyboard


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
