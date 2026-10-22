"""Telegram alternatives reuse only payment actions already offered for this order."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from aiogram import types

from bot.keyboards.inline.user_keyboards_context import payment_methods_back_callback
from bot.utils.callback_answer import callback_message_or_none
from config.settings import Settings
from config.tariffs_config import default_payment_currency_code_for_settings

from .common import Translator

if TYPE_CHECKING:
    from .callbacks import PaymentCallbackParts


def payment_fallback_keyboard(
    callback: types.CallbackQuery,
    *,
    settings: Settings,
    parts: PaymentCallbackParts,
    translator: Translator,
    language: str,
) -> tuple[types.InlineKeyboardMarkup, bool]:
    # Import lazily: the registry imports the provider modules using this helper.
    from bot.payment_providers import get_provider_spec, provider_telegram_button_text

    message = callback_message_or_none(callback)
    markup = message.reply_markup if message is not None else None
    original_buttons = {
        button.callback_data.split(":", 1)[0]: button
        for row in (markup.inline_keyboard if markup else [])
        for button in row
        if button.callback_data
    }
    failed_prefix = (callback.data or "").split(":", 1)[0]
    ordered_specs = [
        spec for method in settings.payment_methods_order if (spec := get_provider_spec(method))
    ]
    failed_index = next(
        (
            index
            for index, spec in enumerate(ordered_specs)
            if spec.callback_prefix == failed_prefix
        ),
        -1,
    )
    failed_spec = ordered_specs[failed_index] if failed_index >= 0 else None
    ordered_specs = ordered_specs[failed_index + 1 :] + ordered_specs[: failed_index + 1]
    rows: list[list[types.InlineKeyboardButton]] = []
    seen: set[str] = set()
    for spec in ordered_specs:
        prefix = spec.callback_prefix
        if (
            not prefix
            or prefix == failed_prefix
            or prefix in seen
            or failed_spec is None
            or failed_spec.payment_group is None
            or spec.payment_group != failed_spec.payment_group
            or spec.provider_id == failed_spec.provider_id
        ):
            continue
        seen.add(prefix)
        button = original_buttons.get(prefix)
        if button is None or not button.callback_data:
            continue
        data = button.callback_data.split(":", 3)
        try:
            same_order = len(data) == 4 and float(data[1]) == parts.months
            amount = float(data[2])
        except (ValueError, IndexError):
            continue
        if (
            not same_order
            or data[3] != parts.sale_mode
            or not math.isfinite(amount)
            or not spec.is_available_to_user(settings, require_configured=False)
            or not spec.is_usable_for_payment(
                settings, default_payment_currency_code_for_settings(settings), amount
            )
            or not spec.is_usable_for_payment_context(settings, parts.months, parts.sale_mode)
            or not spec.is_checkout_promo_supported(
                settings, parts.months, parts.sale_mode, parts.checkout_promo
            )
        ):
            continue
        label = provider_telegram_button_text(spec, settings, language=language)
        rows.append(
            [
                types.InlineKeyboardButton(
                    text=translator("payment_try_alternative", method=label) if not rows else label,
                    callback_data=button.callback_data,
                )
            ]
        )
    has_alternative = bool(rows)
    if not rows and callback.data:
        rows.append(
            [
                types.InlineKeyboardButton(
                    text=translator("payment_retry"), callback_data=callback.data
                )
            ]
        )
    rows.append(
        [
            types.InlineKeyboardButton(
                text=translator("back_to_payment_methods_button"),
                callback_data=payment_methods_back_callback(
                    parts.human_value, parts.sale_mode, parts.price
                ),
            )
        ]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=rows), has_alternative
