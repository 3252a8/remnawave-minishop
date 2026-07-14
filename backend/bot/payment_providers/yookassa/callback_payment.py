"""YooKassa new-payment callback handlers."""

import contextlib
import logging
from typing import Any

from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_yk_autopay_choice_keyboard,
    payment_methods_back_callback,
)
from bot.middlewares.i18n import JsonI18n
from bot.utils.callback_answer import callback_message_or_none
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import user_billing_dal

from ..shared import PaymentCallbackParts, quote_hwid_callback_parts
from ..shared import sale_mode_base as _sale_mode_base
from .callback_common import _initiate_yk_payment, _yookassa_available_to_callback_user
from .router import router
from .service import YooKassaService
from .shared import _format_value, _parse_offer_payload

logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("pay_yk:"))
async def pay_yk_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    yookassa_service: YooKassaService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    message = callback_message_or_none(callback)
    if not i18n or message is None:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logger.error("YooKassa service is not configured or unavailable.")
        await message.edit_text(get_text("payment_service_unavailable"))
        with contextlib.suppress(Exception):
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        return

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logger.error("Invalid pay_yk data in callback: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    parsed = _parse_offer_payload(data_payload)
    if not parsed:
        logger.error("Invalid pay_yk payload structure: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    months, price_rub, sale_mode = parsed
    hwid_quote = None
    user_id = callback.from_user.id
    currency_code_for_yk = default_payment_currency_code_for_settings(settings)
    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    autopay_require_binding = bool(
        getattr(settings, "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING", True)
    )
    saved_methods: list = []
    if autopay_enabled:
        try:
            saved_methods = await user_billing_dal.list_user_payment_methods(
                session, user_id, provider="yookassa"
            )
        except Exception as e_list:
            logger.exception(
                "Failed to load saved payment methods for user %s: %s", user_id, e_list
            )
            saved_methods = []

    if autopay_enabled and saved_methods:
        try:
            await message.edit_text(
                get_text("yookassa_autopay_flow_prompt"),
                reply_markup=get_yk_autopay_choice_keyboard(
                    months,
                    price_rub,
                    current_lang,
                    i18n,
                    has_saved_cards=True,
                    sale_mode=sale_mode,
                    back_callback=payment_methods_back_callback(
                        _format_value(months), sale_mode, price_rub
                    ),
                ),
            )
        except Exception as e_edit:
            logger.warning("Failed to show autopay choice: %s. Sending new message.", e_edit)
            with contextlib.suppress(Exception):
                await message.answer(
                    get_text("yookassa_autopay_flow_prompt"),
                    reply_markup=get_yk_autopay_choice_keyboard(
                        months,
                        price_rub,
                        current_lang,
                        i18n,
                        has_saved_cards=True,
                        sale_mode=sale_mode,
                        back_callback=payment_methods_back_callback(
                            _format_value(months), sale_mode, price_rub
                        ),
                    ),
                )
        with contextlib.suppress(Exception):
            await callback.answer()
        return

    quoted_parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=PaymentCallbackParts(months=months, price=price_rub, sale_mode=sale_mode),
        subscription_service=yookassa_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
        settings=settings,
    )
    if not quoted_parts:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    months = quoted_parts.months
    price_rub = quoted_parts.price

    await _initiate_yk_payment(
        callback,
        settings=settings,
        session=session,
        yookassa_service=yookassa_service,
        i18n=i18n,
        current_lang=current_lang,
        get_text=get_text,
        user_id=user_id,
        months=months,
        price_rub=price_rub,
        currency_code_for_yk=currency_code_for_yk,
        save_payment_method=autopay_enabled and autopay_require_binding,
        back_callback=payment_methods_back_callback(_format_value(months), sale_mode, price_rub),
        sale_mode=sale_mode,
        hwid_quote=hwid_quote,
    )
    with contextlib.suppress(Exception):
        await callback.answer()


@router.callback_query(F.data.startswith("pay_yk_new:"))
async def pay_yk_new_card_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    yookassa_service: YooKassaService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    message = callback_message_or_none(callback)
    if not i18n or message is None:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logger.error("YooKassa service unavailable for pay_yk_new.")
        with contextlib.suppress(Exception):
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        with contextlib.suppress(Exception):
            await message.edit_text(get_text("payment_service_unavailable"))
        return

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logger.error("Invalid pay_yk_new data in callback: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    parsed = _parse_offer_payload(data_payload)
    if not parsed:
        logger.error("Invalid pay_yk_new payload structure: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    months, price_rub, sale_mode = parsed
    hwid_quote = None
    quoted_parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=PaymentCallbackParts(months=months, price=price_rub, sale_mode=sale_mode),
        subscription_service=yookassa_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
        settings=settings,
    )
    if not quoted_parts:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    months = quoted_parts.months
    price_rub = quoted_parts.price
    user_id = callback.from_user.id
    currency_code_for_yk = default_payment_currency_code_for_settings(settings)
    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    autopay_require_binding = bool(
        getattr(settings, "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING", True)
    )

    await _initiate_yk_payment(
        callback,
        settings=settings,
        session=session,
        yookassa_service=yookassa_service,
        i18n=i18n,
        current_lang=current_lang,
        get_text=get_text,
        user_id=user_id,
        months=months,
        price_rub=price_rub,
        currency_code_for_yk=currency_code_for_yk,
        save_payment_method=autopay_enabled and autopay_require_binding,
        back_callback=payment_methods_back_callback(_format_value(months), sale_mode, price_rub),
        sale_mode=sale_mode,
        hwid_quote=hwid_quote,
    )
    with contextlib.suppress(Exception):
        await callback.answer()
