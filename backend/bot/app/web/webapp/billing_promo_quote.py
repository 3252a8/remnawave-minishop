"""Read-only promo quote for the checkout screen.

The screen asks "what would this cost with this code" before anything is
created, so this route resolves the same base quote the create path uses and
then reports whether the code applies and whether the chosen provider can
actually take the resulting amount. Nothing is written here.
"""

import logging

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.webapp.auth import _require_user_id
from bot.app.web.webapp.common import (
    _json_error,
    _parse_model_payload,
)
from bot.app.web.webapp.payloads import WebAppPromoQuotePayload
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.dal import user_dal

from .billing_checkout_adjustments import (
    CheckoutPromoError,
    _resolve_checkout_promo,
)
from .billing_payments import _payment_promo_error, _resolve_base_payment_quote
from .response_helpers import json_response

logger = logging.getLogger(__name__)


def _payment_amount_error(
    *,
    request: web.Request,
    settings: Settings,
    method: str,
    currency: str,
    amount: float,
    is_admin: bool = False,
) -> CheckoutPromoError | None:
    from bot.payment_providers import get_provider_spec

    provider_spec = get_provider_spec(method)
    if provider_spec is None or not provider_spec.create_webapp_payment:
        return CheckoutPromoError(400, "payment_unavailable", "Payment method unavailable")
    if not provider_spec.is_usable_for_payment_amount(settings, currency, amount):
        return CheckoutPromoError(
            400,
            "payment_amount_below_minimum",
            "Payment amount is below the provider minimum",
        )
    if not provider_spec.is_visible_for_user(settings, request.app, is_admin=is_admin):
        return CheckoutPromoError(400, "payment_unavailable", "Payment method unavailable")
    return None


async def quote_promo_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payment_payload = await _parse_model_payload(request, WebAppPromoQuotePayload)
    method = str(payment_payload.method or "").strip().lower()
    settings: Settings = get_settings(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        from bot.services.account_roles import is_admin as account_is_admin

        is_admin = await account_is_admin(session, user_id)

        base_quote, quote_error = await _resolve_base_payment_quote(
            request=request,
            session=session,
            user_id=user_id,
            db_user=db_user,
            payment_payload=payment_payload,
            method=method,
            settings=settings,
            subscription_service=subscription_service,
        )
        if quote_error is not None:
            return quote_error
        if base_quote is None:
            return _json_error(400, "invalid_plan", "Plan is not available")

        promo_result, promo_error = await _resolve_checkout_promo(
            session=session,
            settings=settings,
            user_id=user_id,
            code_input=payment_payload.promo_code,
            sale_mode=base_quote.sale_mode,
            payment_units=base_quote.payment_units,
            traffic_gb=base_quote.traffic_gb_for_payment,
            method=method,
            base_amount=base_quote.price,
            base_stars=base_quote.stars_price,
        )
        if promo_error is not None or promo_result is None:
            reason = promo_error.message if promo_error is not None else "Code does not apply"
            reason_key = (
                promo_error.code if promo_error is not None else "promo_code_not_applicable"
            )
            return json_response(
                {
                    "ok": True,
                    "valid": False,
                    "reason": reason,
                    "reason_key": reason_key,
                }
            )

        promo_support_error = _payment_promo_error(
            settings=settings,
            method=method,
            months=base_quote.payment_units,
            sale_mode=base_quote.sale_mode,
            promo_result=promo_result,
        )
        if promo_support_error is not None:
            return json_response(
                {
                    "ok": True,
                    "valid": False,
                    "payable": False,
                    "reason": promo_support_error.message,
                    "reason_key": promo_support_error.code,
                }
            )

        payment_error = _payment_amount_error(
            request=request,
            settings=settings,
            method=method,
            currency=base_quote.default_currency_code,
            amount=promo_result.effective_amount,
            is_admin=is_admin,
        )
        if payment_error is not None:
            return json_response(
                {
                    "ok": True,
                    "valid": False,
                    "payable": False,
                    "reason": payment_error.message,
                    "reason_key": payment_error.code,
                }
            )

        return json_response(
            {
                "ok": True,
                "valid": True,
                "payable": True,
                "code": promo_result.code,
                "promo_code_id": promo_result.promo_code_id,
                "currency": base_quote.default_currency_code,
                "discount_percent": promo_result.discount_percent,
                "base_amount": base_quote.price,
                "effective_amount": promo_result.effective_amount,
                "base_stars": base_quote.stars_price,
                "effective_stars": promo_result.effective_stars,
                "discount_amount": promo_result.discount_amount,
                "effect_summary": promo_result.effect_summary,
                "applies_to": promo_result.effects.applies_to,
                "bonus_days": promo_result.effects.bonus_days,
                "regular_traffic_gb": promo_result.effects.regular_traffic_gb,
                "premium_traffic_gb": promo_result.effects.premium_traffic_gb,
                "duration_multiplier": (
                    promo_result.effects.duration_multiplier
                    if promo_result.effects.duration_multiplier != 1.0
                    else None
                ),
                "traffic_multiplier": (
                    promo_result.effects.traffic_multiplier
                    if promo_result.effects.traffic_multiplier != 1.0
                    else None
                ),
                "min_subscription_months": promo_result.effects.min_subscription_months,
                "min_subscription_days": promo_result.effects.min_subscription_days,
                "min_traffic_gb": promo_result.effects.min_traffic_gb,
            }
        )
