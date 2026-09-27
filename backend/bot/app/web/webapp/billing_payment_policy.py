from __future__ import annotations

from typing import Any

from config.settings import Settings

from .billing_checkout_adjustments import CheckoutPromoError, CheckoutPromoResult


def _active_tribute_recurrence(subscription: Any | None) -> bool:
    return bool(
        subscription is not None
        and str(subscription.provider or "").strip().lower() == "tribute"
        and bool(subscription.auto_renew_enabled)
    )


def _payment_promo_error(
    *,
    settings: Settings,
    method: str,
    months: Any,
    sale_mode: str,
    promo_result: CheckoutPromoResult | None,
) -> CheckoutPromoError | None:
    if promo_result is None:
        return None
    from .billing_balance_method import checkout_provider_spec

    provider_spec = checkout_provider_spec(method)
    if provider_spec is None or not provider_spec.create_webapp_payment:
        return CheckoutPromoError(400, "payment_unavailable", "Payment method unavailable")
    if provider_spec.is_checkout_promo_supported(
        settings,
        months,
        sale_mode,
        promo_result,
    ):
        return None
    return CheckoutPromoError(
        400,
        "promo_not_supported_by_payment_method",
        "Promo code is not supported by this payment method",
    )
