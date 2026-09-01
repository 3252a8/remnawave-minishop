from __future__ import annotations

import logging

from aiohttp import web

from bot.app.web.context import (
    get_bot,
    get_i18n,
    get_referral_service,
    get_settings,
    get_subscription_service,
)
from bot.payment_providers.base import WebAppPaymentContext
from bot.payment_providers.shared import create_webapp_payment_record
from bot.payment_providers.shared.success import (
    PaymentSuccessRequest,
    finalize_successful_payment,
)
from db.dal import payment_dal

from .common import _json_error
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def create_fully_discounted_payment(
    *,
    request: web.Request,
    payment_context: WebAppPaymentContext,
) -> web.Response:
    try:
        payment = await create_webapp_payment_record(
            payment_context,
            amount=0.0,
            currency=payment_context.currency,
            status="succeeded_pending_finalization",
            provider="promo",
            funding_source="checkout_promo",
        )
    except Exception:
        await payment_context.session.rollback()
        logger.exception(
            "Failed to create fully discounted checkout: user_id=%s",
            payment_context.user_id,
        )
        return _json_error(409, "promo_checkout_failed", "Checkout could not be created")

    referral_service = get_referral_service(request)
    if referral_service is None:
        await payment_dal.update_payment_status_by_db_id(
            payment_context.session,
            int(payment.payment_id),
            "activation_failed",
        )
        await payment_context.session.commit()
        return _json_error(503, "payment_service_unavailable", "Payment service unavailable")

    try:
        outcome = await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=get_bot(request),
                settings=get_settings(request),
                i18n=get_i18n(request),
                session=payment_context.session,
                subscription_service=get_subscription_service(request),
                referral_service=referral_service,
                payment=payment,
                user_id=payment_context.user_id,
                amount=0.0,
                currency=payment_context.currency,
                sale_mode=payment_context.sale_mode,
                months=payment_context.months,
                traffic_amount=payment_context.traffic_gb,
                provider_subscription="promo",
                provider_notification="promo",
                skip_referral_bonus=True,
            )
        )
    except Exception:
        await payment_context.session.rollback()
        logger.exception(
            "Fully discounted checkout finalization crashed for payment %s",
            payment.payment_id,
        )
        try:
            await payment_dal.update_payment_status_by_db_id(
                payment_context.session,
                int(payment.payment_id),
                "activation_failed",
            )
            await payment_context.session.commit()
        except Exception:
            await payment_context.session.rollback()
            logger.exception(
                "Failed to mark fully discounted checkout %s for reconciliation",
                payment.payment_id,
            )
        return _json_error(
            409,
            "subscription_activation_failed",
            "Purchase activation failed",
        )

    if outcome is None:
        current = await payment_dal.get_payment_by_db_id(
            payment_context.session,
            int(payment.payment_id),
        )
        if current is None or str(current.status).strip().lower() != "succeeded":
            return _json_error(
                409,
                "subscription_activation_failed",
                "Purchase activation failed",
            )

    return json_response(
        {
            "ok": True,
            "action": "completed",
            "payment_id": int(payment.payment_id),
            "status": "succeeded",
            "paid": True,
        }
    )
