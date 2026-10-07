"""Immutable checkout context adjustments after authoritative promo validation."""

from dataclasses import replace

from bot.payment_providers.base import WebAppPaymentContext

from .billing_checkout_adjustments import CheckoutPromoResult
from .billing_partner_checkout import balance_checkout_context_fields


def apply_checkout_promo_context(
    payment_context: WebAppPaymentContext,
    *,
    price: float,
    stars_price: int | None,
    promo_code_id: int | None,
    promo_result: CheckoutPromoResult | None,
) -> WebAppPaymentContext:
    return replace(
        payment_context,
        price=price,
        stars_price=stars_price,
        promo_code_id=promo_code_id,
        promo_effect_summary=promo_result.effect_summary if promo_result else None,
        promo_bonus_days=promo_result.effects.bonus_days if promo_result else None,
        promo_regular_traffic_gb=(
            promo_result.effects.regular_traffic_gb if promo_result else None
        ),
        promo_premium_traffic_gb=(
            promo_result.effects.premium_traffic_gb if promo_result else None
        ),
        promo_discount_percent=promo_result.effects.discount_percent if promo_result else None,
        promo_duration_multiplier=(
            promo_result.effects.duration_multiplier
            if promo_result and promo_result.effects.duration_multiplier != 1.0
            else None
        ),
        promo_traffic_multiplier=(
            promo_result.effects.traffic_multiplier
            if promo_result and promo_result.effects.traffic_multiplier != 1.0
            else None
        ),
        promo_applies_to=promo_result.effects.applies_to if promo_result else None,
        promo_min_subscription_months=promo_result.effects.min_subscription_months
        if promo_result
        else None,
        promo_min_traffic_gb=promo_result.effects.min_traffic_gb if promo_result else None,
        checkout_discount_amount=promo_result.discount_amount if promo_result else None,
        checkout_charged_months=promo_result.charged_months if promo_result else None,
        checkout_charged_gb=promo_result.charged_gb if promo_result else None,
        checkout_quoted_at=promo_result.quoted_at if promo_result else None,
        **balance_checkout_context_fields(
            None,
            promo_base_amount=promo_result.base_amount if promo_result else None,
        ),
    )
