"""Shared YooKassa callback helpers."""

import contextlib
import logging
from collections.abc import Callable
from typing import Any

from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_back_to_main_menu_markup,
    get_payment_url_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.utils.callback_answer import callback_message_or_none
from config.settings import Settings
from db.dal import payment_dal, user_billing_dal

from ..base import PaymentProviderSpec
from ..shared import parse_positive_int_units
from ..shared import sale_mode_base as _sale_mode_base
from .service import YooKassaService
from .shared import _format_value, _metadata_iso
from .success import HWID_DEVICE_SALE_BASES

logger = logging.getLogger(__name__)


def _provider_spec() -> PaymentProviderSpec:
    from . import SPEC

    return SPEC


async def _initiate_yk_payment(
    callback: types.CallbackQuery,
    *,
    settings: Settings,
    session: AsyncSession,
    yookassa_service: YooKassaService,
    i18n: JsonI18n | None,
    current_lang: str,
    get_text: Callable[..., str],
    user_id: int,
    months: float,
    price_rub: float,
    currency_code_for_yk: str,
    save_payment_method: bool,
    back_callback: str,
    payment_method_id: str | None = None,
    selected_method_internal_id: int | None = None,
    sale_mode: str = "subscription",
    hwid_quote: dict[str, Any] | None = None,
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
        "hwid_traffic_bonus_bytes": hwid_quote.get("traffic_bonus_bytes") if hwid_quote else None,
    }

    db_payment_record = None
    try:
        db_payment_record = await payment_dal.create_payment_record(session, payment_record_data)
        await session.commit()
        logger.info(
            "Payment record %s created for user %s with status 'pending_yookassa'.",
            db_payment_record.payment_id,
            user_id,
        )
    except Exception as e_db_payment:
        await session.rollback()
        logger.exception(
            "Failed to create payment record in DB for user %s: %s", user_id, e_db_payment
        )
        with contextlib.suppress(Exception):
            await message.edit_text(get_text("error_creating_payment_record"))
        return False

    if not db_payment_record:
        with contextlib.suppress(Exception):
            await message.edit_text(get_text("error_creating_payment_record"))
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
            "hwid_traffic_bonus_bytes": hwid_quote.get("traffic_bonus_bytes"),
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
                with contextlib.suppress(Exception):
                    await user_billing_dal.upsert_user_payment_method(
                        session,
                        user_id=user_id,
                        provider_payment_method_id=pm["id"],
                        provider="yookassa",
                        card_last4=display_last4,
                        card_network=display_network,
                        set_default=save_payment_method,
                    )
                await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to save YooKassa payment method preliminarily")
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
                    logger.exception(
                        "Failed to set default payment method after initiating payment"
                    )
            await session.commit()
        except Exception as e_db_update_ykid:
            await session.rollback()
            logger.exception(
                "Failed to update payment record %s with YK ID: %s",
                db_payment_record.payment_id,
                e_db_update_ykid,
            )
            with contextlib.suppress(Exception):
                await message.edit_text(get_text("error_payment_gateway_link_failed"))
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
            logger.warning("Edit message for payment link failed: %s. Sending new one.", e_edit)
            with contextlib.suppress(Exception):
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
                    logger.exception(
                        "Failed to set default payment method after saved-card payment start"
                    )
            await session.commit()
        except Exception as e_db_update_saved:
            await session.rollback()
            logger.exception(
                "Failed to update saved-card payment record %s: %s",
                db_payment_record.payment_id,
                e_db_update_saved,
            )
            with contextlib.suppress(Exception):
                await message.edit_text(get_text("error_payment_gateway"))
            return False

        message_text = get_text("yookassa_autopay_charge_initiated")
        try:
            await message.edit_text(
                message_text,
                reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
            )
        except Exception as e_edit:
            logger.warning("Failed to notify about saved-card charge start: %s", e_edit)
            with contextlib.suppress(Exception):
                await message.answer(
                    message_text,
                    reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
                )
        return True

    try:
        await payment_dal.update_payment_status_by_db_id(
            session, db_payment_record.payment_id, "failed_creation"
        )
        await session.commit()
    except Exception as e_db_fail_create:
        await session.rollback()
        logger.exception(
            "Additionally failed to update payment record to 'failed_creation': %s",
            e_db_fail_create,
        )
    logger.error(
        "Failed to create payment in YooKassa for user %s, payment_db_id %s. Response: %s",
        user_id,
        db_payment_record.payment_id,
        payment_response_yk,
    )
    with contextlib.suppress(Exception):
        await message.edit_text(get_text("error_payment_gateway"))
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
    with contextlib.suppress(Exception):
        await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
    message = callback_message_or_none(callback)
    if message is not None:
        with contextlib.suppress(Exception):
            await message.edit_text(get_text("payment_service_unavailable"))
    return False
