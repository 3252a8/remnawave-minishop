"""Normalize duration-bearing order writes before they reach any provider."""

from typing import Any

from config.subscription_periods import (
    days_to_legacy_months,
    positive_period,
    sale_mode_duration_days,
)


def normalize_payment_period(payment_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(payment_data)
    sale_mode = str(data.get("sale_mode") or "subscription")
    base = sale_mode.split("|", 1)[0].split("@", 1)[0]
    days = data.get("subscription_duration_days")
    encoded = sale_mode_duration_days(sale_mode)
    if base != "subscription":
        if days is not None or encoded is not None:
            raise ValueError("non-subscription order cannot contain a billing duration")
        return data
    if days is not None and encoded is not None and positive_period(days) != encoded:
        raise ValueError("order duration conflicts with callback duration")
    if days is None:
        days = encoded
    if days is None:
        return data
    days = positive_period(days)
    data["subscription_duration_days"] = days
    if data.get("period_semantics") not in (None, "fixed_days"):
        return data
    data["period_semantics"] = "fixed_days"
    data["subscription_duration_months"] = days_to_legacy_months(days)
    if data.get("checkout_charged_months") is not None:
        data["checkout_charged_days"] = days
        data["checkout_charged_months"] = days_to_legacy_months(days)
    return data
