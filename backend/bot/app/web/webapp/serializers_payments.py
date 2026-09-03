from __future__ import annotations

from typing import Any

from bot.services.checkout_addons import parse_checkout_bundle_snapshot


def _serialize_pending_promo_payment(payment: Any | None) -> dict[str, Any] | None:
    if payment is None:
        return None

    promo = getattr(payment, "promo_code_used", None)
    promo_code = str(
        getattr(promo, "archived_code", None) or getattr(promo, "code", None) or ""
    ).strip()
    amount = float(getattr(payment, "amount", 0) or 0)
    discount_amount = max(
        0.0,
        float(getattr(payment, "checkout_discount_amount", 0) or 0),
    )
    base_amount_raw = getattr(payment, "checkout_base_amount", None)
    base_amount = (
        float(base_amount_raw) if base_amount_raw is not None else amount + discount_amount
    )
    base_amount = max(amount, base_amount)
    total_discount_amount = max(discount_amount, base_amount - amount)
    partner_balance_minor = max(
        0,
        int(getattr(payment, "partner_balance_amount_minor", 0) or 0),
    )
    partner_balance_scale = max(
        0,
        int(getattr(payment, "partner_balance_currency_scale", 0) or 0),
    )
    partner_balance_amount = partner_balance_minor / (10**partner_balance_scale)
    created_at = getattr(payment, "created_at", None)
    checkout_bundle = parse_checkout_bundle_snapshot(
        getattr(payment, "checkout_bundle_snapshot", None)
    )
    return {
        "payment_id": int(payment.payment_id),
        "payment_url": str(payment.provider_payment_url),
        "provider": str(payment.provider or ""),
        "status": str(payment.status or ""),
        "amount": amount,
        "base_amount": base_amount,
        "currency": str(payment.currency or ""),
        "discount_amount": total_discount_amount,
        "discount_percent": float(getattr(payment, "promo_discount_percent", 0) or 0),
        "partner_balance_amount": partner_balance_amount,
        "partner_balance_amount_minor": partner_balance_minor,
        "partner_balance_currency_scale": partner_balance_scale,
        "months": getattr(payment, "subscription_duration_months", None),
        "duration_days": getattr(payment, "subscription_duration_days", None),
        "period_semantics": getattr(payment, "period_semantics", None),
        "purchased_gb": getattr(payment, "purchased_gb", None),
        "purchased_hwid_devices": getattr(payment, "purchased_hwid_devices", None),
        "sale_mode": str(getattr(payment, "sale_mode", None) or ""),
        "tariff_key": getattr(payment, "tariff_key", None),
        "promo_code": promo_code,
        "promo_effect_summary": str(getattr(payment, "promo_effect_summary", None) or ""),
        "checkout_addons": list(checkout_bundle.get("items") or []) if checkout_bundle else [],
        "checkout_addons_amount": float(checkout_bundle.get("addons_amount") or 0)
        if checkout_bundle
        else 0.0,
        "created_at": created_at.isoformat() if created_at is not None else "",
    }
