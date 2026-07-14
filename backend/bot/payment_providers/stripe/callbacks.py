from __future__ import annotations

import logging
from typing import Any

from aiogram import F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal

from ..shared import (
    build_payment_record_payload,
    describe_payment,
    first_value,
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    parse_payment_callback,
    payment_record_amounts,
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
    safe_callback_answer,
)
from .router import router
from .service import StripeService

logger = logging.getLogger(__name__)

_LOG = "stripe"


@router.callback_query(F.data.startswith("pay_stripe:"))
async def pay_stripe_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    stripe_service: StripeService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return
    from .stripe import SPEC

    if not SPEC.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
        return
    if not stripe_service or not stripe_service.configured:
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=stripe_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
        settings=settings,
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = default_payment_currency_code_for_settings(settings)
    payment_description = describe_payment(translator, parts)
    reuse_amounts = payment_record_amounts(
        months=parts.months,
        sale_mode=parts.sale_mode,
        hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
    )
    reusable_payment = await payment_dal.find_recent_pending_provider_payment(
        session,
        user_id=callback.from_user.id,
        provider="stripe",
        pending_status="pending_stripe",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
    )
    if reusable_payment is not None:
        reusable_url = await stripe_service.try_reuse_pending_payment(reusable_payment)
        if reusable_url:
            await safe_callback_answer(callback)
            await render_payment_link(
                callback,
                translator=translator,
                current_lang=current_lang,
                i18n=i18n,
                parts=parts,
                payment_url=reusable_url,
                log_prefix=_LOG,
            )
            return

    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_stripe",
        description=payment_description,
        months=parts.months,
        provider="stripe",
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
    )
    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception(
            "Stripe: failed to create payment record for user %s.",
            callback.from_user.id,
        )
        await notify_payment_record_failure(callback, translator)
        return

    await safe_callback_answer(callback)
    success, response_data = await stripe_service.create_checkout_session(
        payment_db_id=payment_record.payment_id,
        user_id=payment_record.user_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        metadata={
            "subscription_months": str(int(float(parts.months)))
            if parts.sale_base == "subscription"
            else "0",
            "sale_mode": parts.sale_mode,
            "source": "telegram",
        },
    )
    await render_link_or_fail(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=parts,
        session=session,
        payment=payment_record,
        api_success=success,
        payment_url=first_value(response_data, "url") if success else None,
        provider_payment_id=first_value(response_data, "id"),
        provider_response=response_data,
        log_prefix=_LOG,
    )
