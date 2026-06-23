import logging
from typing import Any, Callable, List, Optional, Tuple

from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_back_to_main_menu_markup,
    get_payment_url_keyboard,
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
from db.dal import payment_dal, user_billing_dal

from ..base import (
    PaymentProviderSpec,
)
from ..shared import (
    PaymentCallbackParts,
    parse_positive_int_units,
    quote_hwid_callback_parts,
)
from ..shared import (
    sale_mode_base as _sale_mode_base,
)
from .router import router
from .service import YooKassaService
from .shared import (
    _format_saved_payment_method_title,
    _format_value,
    _metadata_iso,
    _parse_offer_payload,
    _parse_saved_list_payload,
)
from .success import HWID_DEVICE_SALE_BASES


def _provider_spec() -> PaymentProviderSpec:
    from . import SPEC

    return SPEC


async def _initiate_yk_payment(
    callback: types.CallbackQuery,
    *,
    settings: Settings,
    session: AsyncSession,
    yookassa_service: YooKassaService,
    i18n: Optional[JsonI18n],
    current_lang: str,
    get_text: Callable[..., str],
    user_id: int,
    months: float,
    price_rub: float,
    currency_code_for_yk: str,
    save_payment_method: bool,
    back_callback: str,
    payment_method_id: Optional[str] = None,
    selected_method_internal_id: Optional[int] = None,
    sale_mode: str = "subscription",
    hwid_quote: Optional[dict[str, Any]] = None,
) -> bool:
    """Create payment record and initiate YooKassa payment (new card or saved card)."""
    message = callback_message_or_none(callback)
    if message is None:
        return False

    sale_base = _sale_mode_base(sale_mode)
    hwid_device_count = None
    if hwid_quote:
        hwid_device_count = parse_positive_int_units(hwid_quote.get("device_count"))
    payment_description = (
        get_text("payment_description_traffic", traffic_gb=_format_value(months))
        if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
        else (
            get_text("payment_description_hwid_devices", count=int(months))
            if sale_base in HWID_DEVICE_SALE_BASES
            else get_text("payment_description_subscription", months=int(months))
        )
    )
    payment_record_data = {
        "user_id": user_id,
        "amount": price_rub,
        "currency": currency_code_for_yk,
        "status": "pending_yookassa",
        "description": payment_description,
        "subscription_duration_months": int(months) if sale_base == "subscription" else None,
        "sale_mode": sale_mode,
        "tariff_key": sale_mode.split("@", 1)[1].split("|", 1)[0] if "@" in sale_mode else None,
        "purchased_gb": float(months)
        if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
        else None,
        "purchased_hwid_devices": (
            int(months) if sale_base in HWID_DEVICE_SALE_BASES else hwid_device_count
        ),
        "hwid_valid_from": hwid_quote.get("valid_from") if hwid_quote else None,
        "hwid_valid_until": hwid_quote.get("valid_until") if hwid_quote else None,
        "hwid_pricing_period_months": hwid_quote.get("pricing_period_months")
        if hwid_quote
        else None,
        "hwid_proration_ratio": hwid_quote.get("proration_ratio") if hwid_quote else None,
        "hwid_full_price": hwid_quote.get("full_price") if hwid_quote else None,
    }

    db_payment_record = None
    try:
        db_payment_record = await payment_dal.create_payment_record(session, payment_record_data)
        await session.commit()
        logging.info(
            f"Payment record {db_payment_record.payment_id} created for user {user_id} with status 'pending_yookassa'."  # noqa: E501
        )
    except Exception as e_db_payment:
        await session.rollback()
        logging.error(
            f"Failed to create payment record in DB for user {user_id}: {e_db_payment}",
            exc_info=True,
        )
        try:
            await message.edit_text(get_text("error_creating_payment_record"))
        except Exception:
            pass
        return False

    if not db_payment_record:
        try:
            await message.edit_text(get_text("error_creating_payment_record"))
        except Exception:
            pass
        return False

    yookassa_metadata = {
        "user_id": str(user_id),
        "subscription_months": str(months),
        "payment_db_id": str(db_payment_record.payment_id),
        "sale_mode": sale_mode,
    }
    if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}:
        yookassa_metadata["traffic_gb"] = str(months)
    if sale_base in HWID_DEVICE_SALE_BASES:
        yookassa_metadata["hwid_devices"] = str(months)
    elif hwid_device_count:
        yookassa_metadata["hwid_devices"] = str(hwid_device_count)
    if hwid_quote and hwid_device_count:
        hwid_metadata = {
            "hwid_valid_from": _metadata_iso(hwid_quote.get("valid_from")),
            "hwid_valid_until": _metadata_iso(hwid_quote.get("valid_until")),
            "hwid_pricing_period_months": hwid_quote.get("pricing_period_months"),
            "hwid_proration_ratio": hwid_quote.get("proration_ratio"),
            "hwid_full_price": hwid_quote.get("full_price"),
        }
        yookassa_metadata.update(
            {key: str(value) for key, value in hwid_metadata.items() if value is not None}
        )
    if payment_method_id:
        yookassa_metadata["used_saved_payment_method_id"] = payment_method_id

    receipt_email_for_yk = yookassa_service.config.DEFAULT_RECEIPT_EMAIL

    payment_response_yk = await yookassa_service.create_payment(
        amount=price_rub,
        currency=currency_code_for_yk,
        description=payment_description,
        metadata=yookassa_metadata,
        receipt_email=receipt_email_for_yk,
        save_payment_method=save_payment_method,
        payment_method_id=payment_method_id,
    )

    if payment_response_yk and payment_response_yk.get("confirmation_url"):
        pm = payment_response_yk.get("payment_method")
        try:
            if pm and pm.get("id"):
                pm_type = pm.get("type")
                title = pm.get("title")
                card = pm.get("card") or {}
                account_number = pm.get("account_number") or pm.get("account")
                if isinstance(card, dict) and (pm_type or "").lower() in {
                    "bank_card",
                    "bank-card",
                    "card",
                }:
                    display_network = card.get("card_type") or title or "Card"
                    display_last4 = card.get("last4")
                elif (pm_type or "").lower() in {"yoo_money", "yoomoney", "yoo-money", "wallet"}:
                    display_network = "YooMoney"
                    display_last4 = (
                        account_number[-4:]
                        if isinstance(account_number, str) and len(account_number) >= 4
                        else None
                    )
                else:
                    display_network = title or (pm_type.upper() if pm_type else "Payment method")
                    display_last4 = None
                await user_billing_dal.upsert_yk_payment_method(
                    session,
                    user_id=user_id,
                    payment_method_id=pm["id"],
                    card_last4=display_last4,
                    card_network=display_network,
                )
                try:
                    await user_billing_dal.upsert_user_payment_method(
                        session,
                        user_id=user_id,
                        provider_payment_method_id=pm["id"],
                        provider="yookassa",
                        card_last4=display_last4,
                        card_network=display_network,
                        set_default=save_payment_method,
                    )
                except Exception:
                    pass
                await session.commit()
        except Exception:
            await session.rollback()
            logging.exception("Failed to save YooKassa payment method preliminarily")
        try:
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id=db_payment_record.payment_id,
                new_status="pending_yookassa",
                yk_payment_id=payment_response_yk.get("id"),
            )
            if selected_method_internal_id is not None:
                try:
                    await user_billing_dal.set_user_default_payment_method(
                        session, user_id, selected_method_internal_id
                    )
                except Exception:
                    logging.exception(
                        "Failed to set default payment method after initiating payment"
                    )
            await session.commit()
        except Exception as e_db_update_ykid:
            await session.rollback()
            logging.error(
                f"Failed to update payment record {db_payment_record.payment_id} with YK ID: {e_db_update_ykid}",  # noqa: E501
                exc_info=True,
            )
            try:
                await message.edit_text(get_text("error_payment_gateway_link_failed"))
            except Exception:
                pass
            return False

        try:
            await message.edit_text(
                get_text(
                    key="payment_link_message_traffic"
                    if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
                    else "payment_link_message",
                    months=int(months),
                    traffic_gb=_format_value(months),
                ),
                reply_markup=get_payment_url_keyboard(
                    payment_response_yk["confirmation_url"],
                    current_lang,
                    i18n,
                    back_callback=back_callback,
                    back_text_key="back_to_payment_methods_button",
                ),
                disable_web_page_preview=False,
            )
        except Exception as e_edit:
            logging.warning(f"Edit message for payment link failed: {e_edit}. Sending new one.")
            try:
                await message.answer(
                    get_text(
                        key="payment_link_message_traffic"
                        if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
                        else "payment_link_message",
                        months=int(months),
                        traffic_gb=_format_value(months),
                    ),
                    reply_markup=get_payment_url_keyboard(
                        payment_response_yk["confirmation_url"],
                        current_lang,
                        i18n,
                        back_callback=back_callback,
                        back_text_key="back_to_payment_methods_button",
                    ),
                    disable_web_page_preview=False,
                )
            except Exception:
                pass
        return True

    if payment_response_yk and payment_method_id:
        try:
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id=db_payment_record.payment_id,
                new_status="pending_yookassa",
                yk_payment_id=payment_response_yk.get("id"),
            )
            if selected_method_internal_id is not None:
                try:
                    await user_billing_dal.set_user_default_payment_method(
                        session, user_id, selected_method_internal_id
                    )
                except Exception:
                    logging.exception(
                        "Failed to set default payment method after saved-card payment start"
                    )
            await session.commit()
        except Exception as e_db_update_saved:
            await session.rollback()
            logging.error(
                f"Failed to update saved-card payment record {db_payment_record.payment_id}: {e_db_update_saved}",  # noqa: E501
                exc_info=True,
            )
            try:
                await message.edit_text(get_text("error_payment_gateway"))
            except Exception:
                pass
            return False

        message_text = get_text("yookassa_autopay_charge_initiated")
        try:
            await message.edit_text(
                message_text,
                reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
            )
        except Exception as e_edit:
            logging.warning(f"Failed to notify about saved-card charge start: {e_edit}")
            try:
                await message.answer(
                    message_text,
                    reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
                )
            except Exception:
                pass
        return True

    try:
        await payment_dal.update_payment_status_by_db_id(
            session, db_payment_record.payment_id, "failed_creation"
        )
        await session.commit()
    except Exception as e_db_fail_create:
        await session.rollback()
        logging.error(
            f"Additionally failed to update payment record to 'failed_creation': {e_db_fail_create}",  # noqa: E501
            exc_info=True,
        )
    logging.error(
        f"Failed to create payment in YooKassa for user {user_id}, payment_db_id {db_payment_record.payment_id}. Response: {payment_response_yk}"  # noqa: E501
    )
    try:
        await message.edit_text(get_text("error_payment_gateway"))
    except Exception:
        pass
    return False


async def _yookassa_available_to_callback_user(
    callback: types.CallbackQuery,
    settings: Settings,
    get_text: Callable[..., str],
) -> bool:
    if _provider_spec().is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        return True
    try:
        await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
    except Exception:
        pass
    message = callback_message_or_none(callback)
    if message is not None:
        try:
            await message.edit_text(get_text("payment_service_unavailable"))
        except Exception:
            pass
    return False


@router.callback_query(F.data.startswith("pay_yk:"))
async def pay_yk_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    yookassa_service: YooKassaService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    message = callback_message_or_none(callback)
    if not i18n or message is None:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logging.error("YooKassa service is not configured or unavailable.")
        await message.edit_text(get_text("payment_service_unavailable"))
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        return

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk data in callback: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parsed = _parse_offer_payload(data_payload)
    if not parsed:
        logging.error(f"Invalid pay_yk payload structure: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
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
    saved_methods: List = []
    if autopay_enabled:
        try:
            saved_methods = await user_billing_dal.list_user_payment_methods(
                session, user_id, provider="yookassa"
            )
        except Exception as e_list:
            logging.exception(f"Failed to load saved payment methods for user {user_id}: {e_list}")
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
            logging.warning(f"Failed to show autopay choice: {e_edit}. Sending new message.")
            try:
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
            except Exception:
                pass
        try:
            await callback.answer()
        except Exception:
            pass
        return

    quoted_parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=PaymentCallbackParts(months=months, price=price_rub, sale_mode=sale_mode),
        subscription_service=yookassa_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not quoted_parts:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
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
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_yk_new:"))
async def pay_yk_new_card_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    yookassa_service: YooKassaService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    message = callback_message_or_none(callback)
    if not i18n or message is None:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logging.error("YooKassa service unavailable for pay_yk_new.")
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        try:
            await message.edit_text(get_text("payment_service_unavailable"))
        except Exception:
            pass
        return

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk_new data in callback: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parsed = _parse_offer_payload(data_payload)
    if not parsed:
        logging.error(f"Invalid pay_yk_new payload structure: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    months, price_rub, sale_mode = parsed
    hwid_quote = None
    quoted_parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=PaymentCallbackParts(months=months, price=price_rub, sale_mode=sale_mode),
        subscription_service=yookassa_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not quoted_parts:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
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
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_yk_saved_list:"))
async def pay_yk_saved_list_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    yookassa_service: YooKassaService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    message = callback_message_or_none(callback)
    if not i18n or message is None:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk_saved_list data: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parsed_saved_list = _parse_saved_list_payload(data_payload)
    if not parsed_saved_list:
        logging.error(f"pay_yk_saved_list payload missing components: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return
    months, price_rub, page, sale_mode = parsed_saved_list

    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    if not autopay_enabled:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    user_id = callback.from_user.id
    try:
        saved_methods = await user_billing_dal.list_user_payment_methods(
            session, user_id, provider="yookassa"
        )
    except Exception as e_list:
        logging.exception(f"Failed to list saved payment methods for user {user_id}: {e_list}")
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
            logging.warning(f"Failed to display no-saved-card notice: {e_edit}")
            try:
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
            except Exception:
                pass
        try:
            await callback.answer()
        except Exception:
            pass
        return

    cards: List[Tuple[str, str]] = []
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
        logging.warning(f"Failed to display saved card list: {e_edit}")
        try:
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
        except Exception:
            pass
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_yk_use_saved:"))
async def pay_yk_use_saved_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    yookassa_service: YooKassaService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    message = callback_message_or_none(callback)
    if not i18n or message is None:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logging.error("YooKassa service unavailable for pay_yk_use_saved.")
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        try:
            await message.edit_text(get_text("payment_service_unavailable"))
        except Exception:
            pass
        return

    callback_data = callback.data or ""
    try:
        _, data_payload = callback_data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk_use_saved data: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parts = data_payload.split(":")
    if len(parts) < 3:
        logging.error(f"pay_yk_use_saved payload missing components: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    try:
        months = float(parts[0])
        price_rub = float(parts[1])
        sale_mode = parts[3] if len(parts) > 3 else "subscription"
    except (ValueError, IndexError):
        logging.error(f"pay_yk_use_saved months/price parsing error: {callback_data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    if not autopay_enabled:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
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
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return
    months = quoted_parts.months
    price_rub = quoted_parts.price

    try:
        saved_methods = await user_billing_dal.list_user_payment_methods(
            session, user_id, provider="yookassa"
        )
    except Exception as e_list:
        logging.exception(f"Failed to list saved payment methods for user {user_id}: {e_list}")
        saved_methods = []

    selected_method = None
    for method in saved_methods:
        if method_identifier.isdigit():
            if method.method_id == int(method_identifier):
                selected_method = method
                break
        if method.provider_payment_method_id == method_identifier:
            selected_method = method
            break

    if not selected_method:
        logging.warning(
            f"Selected payment method not found for user {user_id}: {method_identifier}"
        )
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
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
    try:
        await callback.answer()
    except Exception:
        pass
