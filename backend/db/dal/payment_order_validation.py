from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from db.models import Payment

_PAYMENT_STATUS_SUCCEEDED = "succeeded"
_PAYMENT_IMMUTABLE_TERMINAL_STATUSES = frozenset({"refunded", "reversed"})


def normalize_payment_status(status: Any) -> str:
    return str(status or "").strip().lower()


def would_overwrite_succeeded_payment(current_status: Any, new_status: Any) -> bool:
    normalized_current_status = normalize_payment_status(current_status)
    normalized_new_status = normalize_payment_status(new_status)
    if normalized_current_status in _PAYMENT_IMMUTABLE_TERMINAL_STATUSES:
        return normalized_new_status != normalized_current_status
    return normalized_current_status == _PAYMENT_STATUS_SUCCEEDED and normalized_new_status not in {
        _PAYMENT_STATUS_SUCCEEDED,
        "refunded",
        "reversed",
    }


def _decimal_order_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return normalized if normalized.is_finite() else None


def _datetime_order_value(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_existing_provider_payment_order(
    payment: Payment,
    *,
    user_id: int,
    amount: float,
    currency: str,
    months: int,
    provider: str,
    sale_mode: str | None,
    tariff_key: str | None,
    purchased_gb: float | None,
    purchased_hwid_devices: int | None,
    hwid_valid_from: Any | None,
    hwid_valid_until: Any | None,
    hwid_pricing_period_months: int | None,
    hwid_proration_ratio: float | None,
    hwid_full_price: float | None,
    hwid_traffic_bonus_bytes: int | None,
    entitlement_context_snapshot: str | None,
    checkout_bundle_snapshot: str | None,
    checkout_bundle_hash: str | None,
) -> None:
    """Ensure a provider id cannot be rebound to a different entitlement."""
    comparisons = {
        "user_id": (int(getattr(payment, "user_id", 0)), int(user_id)),
        "amount": (
            _decimal_order_value(getattr(payment, "amount", None)),
            _decimal_order_value(amount),
        ),
        "currency": (
            str(getattr(payment, "currency", "") or "").strip().upper(),
            str(currency or "").strip().upper(),
        ),
        "subscription_duration_months": (
            getattr(payment, "subscription_duration_months", None),
            months,
        ),
        "provider": (
            str(getattr(payment, "provider", "") or "").strip().lower(),
            str(provider or "").strip().lower(),
        ),
        "sale_mode": (
            str(getattr(payment, "sale_mode", "") or "").strip() or None,
            str(sale_mode or "").strip() or None,
        ),
        "tariff_key": (
            str(getattr(payment, "tariff_key", "") or "").strip() or None,
            str(tariff_key or "").strip() or None,
        ),
        "purchased_gb": (
            _decimal_order_value(getattr(payment, "purchased_gb", None)),
            _decimal_order_value(purchased_gb),
        ),
        "purchased_hwid_devices": (
            getattr(payment, "purchased_hwid_devices", None),
            purchased_hwid_devices,
        ),
        "hwid_valid_from": (
            _datetime_order_value(getattr(payment, "hwid_valid_from", None)),
            _datetime_order_value(hwid_valid_from),
        ),
        "hwid_valid_until": (
            _datetime_order_value(getattr(payment, "hwid_valid_until", None)),
            _datetime_order_value(hwid_valid_until),
        ),
        "hwid_pricing_period_months": (
            getattr(payment, "hwid_pricing_period_months", None),
            hwid_pricing_period_months,
        ),
        "hwid_proration_ratio": (
            _decimal_order_value(getattr(payment, "hwid_proration_ratio", None)),
            _decimal_order_value(hwid_proration_ratio),
        ),
        "hwid_full_price": (
            _decimal_order_value(getattr(payment, "hwid_full_price", None)),
            _decimal_order_value(hwid_full_price),
        ),
        "hwid_traffic_bonus_bytes": (
            getattr(payment, "hwid_traffic_bonus_bytes", None),
            hwid_traffic_bonus_bytes,
        ),
        "entitlement_context_snapshot": (
            getattr(payment, "entitlement_context_snapshot", None),
            entitlement_context_snapshot,
        ),
        "checkout_bundle_snapshot": (
            getattr(payment, "checkout_bundle_snapshot", None),
            checkout_bundle_snapshot,
        ),
        "checkout_bundle_hash": (
            getattr(payment, "checkout_bundle_hash", None),
            checkout_bundle_hash,
        ),
    }
    mismatched = [field for field, (stored, expected) in comparisons.items() if stored != expected]
    if mismatched:
        raise ValueError(
            "Provider payment id already belongs to a different order: " + ", ".join(mismatched)
        )
