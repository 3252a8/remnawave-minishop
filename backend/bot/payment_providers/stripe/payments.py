from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from config.settings import Settings

from ..base import (
    WebAppPaymentContext,
)
from ..shared import (
    create_webapp_payment_record,
    finalize_webapp_link_payment,
    first_value,
    payment_failed,
    payment_record_amounts,
    payment_unavailable,
    sale_mode_base,
)
from ..shared.app_context import app_optional, app_required
from .service import StripeService


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = app_required(ctx.request, "settings", Settings)
    service: StripeService = app_required(ctx.request, "stripe_service", StripeService)
    if not service or not service.configured:
        return payment_unavailable()

    currency = ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    try:
        amounts = payment_record_amounts(
            months=ctx.months,
            sale_mode=ctx.sale_mode,
            traffic_gb=ctx.traffic_gb,
            hwid_device_count=ctx.hwid_device_count,
        )
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_stripe",
            provider="stripe",
        )
        success, response_data = await service.create_checkout_session(
            payment_db_id=payment.payment_id,
            user_id=ctx.user_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
            metadata={
                "subscription_months": str(int(float(ctx.months)))
                if sale_mode_base(ctx.sale_mode) == "subscription"
                else "0",
                "traffic_gb": str(ctx.traffic_gb or ctx.months) if amounts.traffic_sale else None,
                "hwid_devices": str(amounts.purchased_hwid_devices)
                if amounts.purchased_hwid_devices
                else None,
                "sale_mode": ctx.sale_mode,
                "source": "webapp",
            },
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Stripe WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(response_data, "url") if success else None,
        provider_payment_id=first_value(response_data, "id"),
        provider_response=response_data,
        log_prefix="Stripe",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    service = app_optional(ctx.request, "stripe_service", StripeService)
    if not service or not service.configured:
        return None
    return await service.try_reuse_pending_payment(payment)
