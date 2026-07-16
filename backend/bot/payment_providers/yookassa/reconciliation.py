from __future__ import annotations

from typing import Any


def normalize_yookassa_payment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize SDK polling output to the webhook payload shape."""

    normalized = dict(payload or {})
    if not isinstance(normalized.get("amount"), dict):
        amount_value = normalized.get("amount_value")
        amount_currency = normalized.get("amount_currency")
        if amount_value is not None or amount_currency:
            normalized["amount"] = {
                "value": str(amount_value if amount_value is not None else 0),
                "currency": amount_currency or "RUB",
            }
    return normalized
