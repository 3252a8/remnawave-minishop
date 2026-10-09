"""Settle authenticated hosted invoices against their immutable local order."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from db.dal import payment_dal

from .common import payment_amount_and_currency_match, payment_units_for_activation
from .success import PaymentSuccessRequest, finalize_successful_payment
from .webhooks import lookup_payment_by_order_or_provider_id, notify_user_payment_failed

logger = logging.getLogger(__name__)


async def settle_hosted_payment(
    service: Any,
    *,
    provider: str,
    provider_id: str,
    order_id: Any,
    state: str,
    amount: Any,
    currency: Any,
) -> web.Response:
    if not provider_id:
        return web.Response(status=400, text="missing_payment_id")
    async with service.async_session_factory() as session:
        payment = await lookup_payment_by_order_or_provider_id(
            session, providers=provider, order_id_raw=order_id, provider_payment_id=provider_id
        )
        if payment is None:
            return web.Response(status=404, text="payment_not_found")
        # Order lookup must never repoint an already bound invoice. Conversely,
        # provider-id fallback must not accept a conflicting order identifier.
        if (payment.provider_payment_id and str(payment.provider_payment_id) != provider_id) or (
            order_id is not None and str(order_id) != str(payment.payment_id)
        ):
            return web.Response(status=400, text="payment_identity_mismatch")
        if state == "succeeded" and not payment_amount_and_currency_match(
            expected_amount=payment.amount,
            expected_currency=payment.currency,
            received_amount=amount,
            received_currency=currency,
        ):
            return web.Response(status=400, text="amount_mismatch")
        if payment.status in {"succeeded", "succeeded_pending_review"}:
            return web.Response(text="ok")
        try:
            if state == "succeeded":
                claimed = await payment_dal.claim_payment_finalization(
                    session, payment.payment_id, provider_payment_id=provider_id
                )
                if claimed is None:
                    return web.Response(text="ok")
                sale_mode = claimed.sale_mode or (
                    "traffic" if service.settings.traffic_sale_mode else "subscription"
                )
                units = payment_units_for_activation(claimed, sale_mode)
                outcome = await finalize_successful_payment(
                    PaymentSuccessRequest(
                        bot=service.bot,
                        settings=service.settings,
                        i18n=service.i18n,
                        session=session,
                        subscription_service=service.subscription_service,
                        referral_service=service.referral_service,
                        payment=claimed,
                        user_id=claimed.user_id,
                        amount=float(claimed.amount),
                        currency=claimed.currency,
                        sale_mode=sale_mode,
                        months=units,
                        traffic_amount=float(units),
                        provider_subscription=provider,
                        provider_notification=provider,
                        db_user=claimed.user,
                        log_prefix=f"{provider} webhook",
                    )
                )
                return web.Response(
                    status=200 if outcome is not None else 500,
                    text="ok" if outcome is not None else "processing_error",
                )
            if state == "failed" and str(payment.status).startswith("pending_"):
                await payment_dal.update_provider_payment_and_status(
                    session, payment.payment_id, provider_id, "failed"
                )
                await session.commit()
                await notify_user_payment_failed(
                    bot=service.bot,
                    settings=service.settings,
                    i18n=service.i18n,
                    session=session,
                    payment=payment,
                )
            return web.Response(text="ok")
        except Exception:
            await session.rollback()
            logger.exception("%s: invoice settlement failed", provider)
            return web.Response(status=500, text="processing_error")
