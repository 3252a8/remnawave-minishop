"""YooKassa saved-card callback handlers."""

import contextlib
import logging
from typing import Any

from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_yk_autopay_choice_keyboard,
    get_yk_saved_cards_keyboard,
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
from .shared import (
    _format_saved_payment_method_title,
    _format_value,
    _parse_saved_list_payload,
)

logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("pay_yk_saved_list:"))
async def pay_yk_saved_list_handler(
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

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logger.error("Invalid pay_yk_saved_list data: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    parsed_saved_list = _parse_saved_list_payload(data_payload)
    if not parsed_saved_list:
        logger.error("pay_yk_saved_list payload missing components: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    months, price_rub, page, sale_mode = parsed_saved_list

    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    if not autopay_enabled:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    user_id = callback.from_user.id
    try:
        saved_methods = await user_billing_dal.list_user_payment_methods(
            session, user_id, provider="yookassa"
        )
    except Exception as e_list:
        logger.exception("Failed to list saved payment methods for user %s: %s", user_id, e_list)
        saved_methods = []

    if not saved_methods:
        try:
            await message.edit_text(
                get_text("yookassa_autopay_no_saved_cards"),
                reply_markup=get_yk_autopay_choice_keyboard(
                    months,
                    price_rub,
                    current_lang,
                    i18n,
                    has_saved_cards=False,
                    sale_mode=sale_mode,
                    back_callback=payment_methods_back_callback(
                        _format_value(months), sale_mode, price_rub
                    ),
                ),
            )
        except Exception as e_edit:
            logger.warning("Failed to display no-saved-card notice: %s", e_edit)
            with contextlib.suppress(Exception):
                await message.answer(
                    get_text("yookassa_autopay_no_saved_cards"),
                    reply_markup=get_yk_autopay_choice_keyboard(
                        months,
                        price_rub,
                        current_lang,
                        i18n,
                        has_saved_cards=False,
                        sale_mode=sale_mode,
                        back_callback=payment_methods_back_callback(
                            _format_value(months), sale_mode, price_rub
                        ),
                    ),
                )
        with contextlib.suppress(Exception):
            await callback.answer()
        return

    cards: list[tuple[str, str]] = []
    for method in saved_methods:
        title = _format_saved_payment_method_title(
            get_text, method.card_network, method.card_last4, method.is_default
        )
        cards.append((str(method.method_id), title))

    per_page = 5
    max_page = max(0, (len(cards) - 1) // per_page)
    page = max(0, min(page, max_page))

    try:
        await message.edit_text(
            get_text("yookassa_autopay_choose_saved_card"),
            reply_markup=get_yk_saved_cards_keyboard(
                cards,
                months,
                price_rub,
                current_lang,
                i18n,
                page=page,
                sale_mode=sale_mode,
            ),
        )
    except Exception as e_edit:
        logger.warning("Failed to display saved card list: %s", e_edit)
        with contextlib.suppress(Exception):
            await message.answer(
                get_text("yookassa_autopay_choose_saved_card"),
                reply_markup=get_yk_saved_cards_keyboard(
                    cards,
                    months,
                    price_rub,
                    current_lang,
                    i18n,
                    page=page,
                    sale_mode=sale_mode,
                ),
            )
    with contextlib.suppress(Exception):
        await callback.answer()


@router.callback_query(F.data.startswith("pay_yk_use_saved:"))
async def pay_yk_use_saved_handler(
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
        logger.error("YooKassa service unavailable for pay_yk_use_saved.")
        with contextlib.suppress(Exception):
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        with contextlib.suppress(Exception):
            await message.edit_text(get_text("payment_service_unavailable"))
        return

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logger.error("Invalid pay_yk_use_saved data: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    parts = data_payload.split(":")
    if len(parts) < 3:
        logger.error("pay_yk_use_saved payload missing components: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    try:
        months = float(parts[0])
        price_rub = float(parts[1])
        sale_mode = parts[3] if len(parts) > 3 else "subscription"
    except (ValueError, IndexError):
        logger.error("pay_yk_use_saved months/price parsing error: %s", callback_data)
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    if not autopay_enabled:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    method_identifier = parts[2]
    user_id = callback.from_user.id
    base_months = months
    base_price_rub = price_rub
    hwid_quote = None
    quoted_parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=user_id,
        parts=PaymentCallbackParts(months=months, price=price_rub, sale_mode=sale_mode),
        subscription_service=yookassa_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not quoted_parts:
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    months = quoted_parts.months
    price_rub = quoted_parts.price

    try:
        saved_methods = await user_billing_dal.list_user_payment_methods(
            session, user_id, provider="yookassa"
        )
    except Exception as e_list:
        logger.exception("Failed to list saved payment methods for user %s: %s", user_id, e_list)
        saved_methods = []

    selected_method = None
    for method in saved_methods:
        if method_identifier.isdigit() and method.method_id == int(method_identifier):
            selected_method = method
            break
        if method.provider_payment_method_id == method_identifier:
            selected_method = method
            break

    if not selected_method:
        logger.warning(
            "Selected payment method not found for user %s: %s", user_id, method_identifier
        )
        with contextlib.suppress(Exception):
            await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    currency_code_for_yk = default_payment_currency_code_for_settings(settings)

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
        save_payment_method=False,
        back_callback=(
            f"pay_yk_saved_list:{_format_value(base_months)}:{base_price_rub}:0:{sale_mode}"
        ),
        payment_method_id=selected_method.provider_payment_method_id,
        selected_method_internal_id=selected_method.method_id,
        sale_mode=sale_mode,
        hwid_quote=hwid_quote,
    )
    with contextlib.suppress(Exception):
        await callback.answer()
