from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_session_factory, get_settings, get_subscription_service
from bot.app.web.webapp.auth import _require_user_id
from bot.app.web.webapp.common import _json_error, _parse_model_payload
from bot.app.web.webapp.payloads import WebAppSubscriptionQuotePayload
from bot.services.checkout_addons import parse_checkout_bundle_snapshot
from bot.services.subscription_gifts import gift_payment_method_available
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from config.subscription_periods import add_period_days, multiplied_bonus_days
from db.dal import subscription_dal, user_dal

from .billing_checkout_adjustments import _resolve_checkout_promo
from .billing_payment_policy import _payment_promo_error
from .billing_promo_quote import _payment_amount_error
from .billing_quotes import _resolve_base_payment_quote
from .response_helpers import json_response


async def _resolve_quote_period_start(
    session: AsyncSession,
    user_id: int,
    panel_user_uuid: str | None,
    subscription_service: SubscriptionService,
    known_start: datetime | None,
) -> datetime | None:
    if known_start is not None:
        return known_start
    active_sub = await subscription_dal.get_active_subscription_by_user_id(
        session, user_id, panel_user_uuid
    )
    if (
        active_sub is not None
        and subscription_service._subscription_billing_model(active_sub) != "traffic"
    ):
        return active_sub.end_date
    return None


async def subscription_quote_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await _parse_model_payload(request, WebAppSubscriptionQuotePayload)
    method = str(payload.method or "").strip().lower()
    if payload.gift and (
        str(payload.sale_mode or "subscription").split("@", 1)[0].split("|", 1)[0] != "subscription"
        or payload.renew_hwid_devices
        or not gift_payment_method_available(method)
    ):
        return _json_error(400, "gift_purchase_unavailable", "Unsupported gift purchase options")
    settings: Settings = get_settings(request)
    if payload.gift and not settings.GIFTS_ENABLED:
        return _json_error(400, "gift_purchase_unavailable", "Gift purchases are disabled")
    subscription_service: SubscriptionService = get_subscription_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        quote, quote_error = await _resolve_base_payment_quote(
            request=request,
            session=session,
            user_id=user_id,
            db_user=db_user,
            payment_payload=payload,
            method=method,
            settings=settings,
            subscription_service=subscription_service,
        )
        if quote_error is not None:
            return quote_error
        if quote is None:
            return _json_error(400, "invalid_plan", "Plan is not available")

        from bot.payment_providers import get_provider_spec

        provider_spec = get_provider_spec(method)
        if provider_spec is None or not provider_spec.create_webapp_payment:
            return _json_error(400, "payment_unavailable", "Payment method unavailable")
        from bot.services.account_roles import is_admin as account_is_admin

        is_admin = await account_is_admin(session, user_id)
        payment_currency = "XTR" if method == "stars" else quote.default_currency_code
        if not provider_spec.is_visible_for_user(settings, request.app, is_admin=is_admin):
            return _json_error(400, "payment_unavailable", "Payment method unavailable")
        if not provider_spec.is_usable_for_payment_currency(settings, payment_currency):
            return _json_error(
                400,
                "unsupported_currency",
                "Payment method does not support this currency",
            )
        if not provider_spec.is_usable_for_payment_context(
            settings,
            quote.payment_units,
            quote.sale_mode,
        ):
            return _json_error(
                400,
                "payment_unavailable",
                "Payment method unavailable for this plan",
            )
        if quote.checkout_bundle_snapshot and not provider_spec.is_checkout_addon_supported(
            settings,
            quote.payment_units,
            quote.sale_mode,
        ):
            return _json_error(
                400,
                "checkout_addons_payment_unavailable",
                "Payment method does not support subscription add-ons",
            )

        effective_amount = float(quote.price)
        effective_stars = quote.stars_price
        discount_amount = 0.0
        promo_code = str(payload.promo_code or "").strip()
        promo_payload: dict[str, object] = {}
        bonus_days = 0
        if promo_code:
            promo_result, promo_error = await _resolve_checkout_promo(
                session=session,
                settings=settings,
                user_id=user_id,
                code_input=promo_code,
                sale_mode=quote.sale_mode,
                payment_units=quote.payment_units,
                traffic_gb=quote.traffic_gb_for_payment,
                method=method,
                base_amount=quote.price,
                base_stars=quote.stars_price,
            )
            if promo_error is not None or promo_result is None:
                return _json_error(
                    promo_error.status if promo_error else 400,
                    promo_error.code if promo_error else "promo_code_not_applicable",
                    promo_error.message if promo_error else "Code does not apply",
                )
            promo_support_error = _payment_promo_error(
                settings=settings,
                method=method,
                months=quote.payment_units,
                sale_mode=quote.sale_mode,
                promo_result=promo_result,
            )
            if promo_support_error is not None:
                return _json_error(
                    promo_support_error.status,
                    promo_support_error.code,
                    promo_support_error.message,
                )
            if quote.duration_days:
                bonus_days = promo_result.effects.bonus_days + multiplied_bonus_days(
                    quote.duration_days, promo_result.effects.duration_multiplier
                )
            effective_amount = float(promo_result.effective_amount)
            effective_stars = promo_result.effective_stars
            discount_amount = float(promo_result.discount_amount)
            promo_payload = {
                "promo_code": promo_result.code,
                "discount_percent": promo_result.discount_percent,
                "effect_summary": promo_result.effect_summary,
                "applies_to": promo_result.effects.applies_to,
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

        payable_amount = (
            float(effective_stars or 0) if method == "stars" else float(effective_amount)
        )
        amount_error = _payment_amount_error(
            request=request,
            settings=settings,
            method=method,
            currency=payment_currency,
            amount=payable_amount,
            is_admin=is_admin,
        )
        if amount_error is not None:
            return _json_error(amount_error.status, amount_error.code, amount_error.message)

        end_date = None
        if quote.duration_days and not payload.gift:
            try:
                period_start = await _resolve_quote_period_start(
                    session,
                    user_id,
                    db_user.panel_user_uuid,
                    subscription_service,
                    quote.period_start,
                ) or datetime.now(UTC)
                if period_start.tzinfo is None:
                    period_start = period_start.replace(tzinfo=UTC)
                end_date = add_period_days(
                    max(datetime.now(UTC), period_start), quote.duration_days + bonus_days
                ).isoformat()
            except ValueError:
                return _json_error(400, "invalid_plan", "Subscription end date is out of range")
        snapshot = parse_checkout_bundle_snapshot(quote.checkout_bundle_snapshot) or {}
        base_amount = float(snapshot.get("base_subscription_amount", quote.price) or 0)
        return json_response(
            {
                "ok": True,
                "payable": True,
                "duration_days": quote.duration_days,
                "bonus_days": bonus_days,
                "end_date": end_date,
                "quote_key": quote.checkout_bundle_hash or "base",
                "currency": payment_currency,
                "base_amount": base_amount,
                "addons_amount": float(quote.checkout_addon_amount),
                "subtotal_amount": float(quote.price),
                "discount_amount": discount_amount,
                "effective_amount": effective_amount,
                "base_stars": snapshot.get("base_subscription_stars", quote.stars_price),
                "addons_stars": int(quote.checkout_addon_stars),
                "effective_stars": effective_stars,
                "renewal_amount": base_amount,
                "items": snapshot.get("items", []),
                **promo_payload,
            }
        )
