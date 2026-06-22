from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, List, Mapping, Optional

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from .base import (
    ProviderEnvConfig,
    normalize_payment_currency_code,
    provider_env_file,
)

_SUCCESS_EVENT_TYPES = {"checkout.session.completed", "payment_intent.succeeded"}
_FAILED_EVENT_TYPES = {
    "checkout.session.expired",
    "payment_intent.canceled",
    "payment_intent.payment_failed",
}
_SUCCESS_PAYMENT_INTENT_STATUSES = {"succeeded", "processing", "requires_capture"}
_FAILED_PAYMENT_INTENT_STATUSES = {
    "canceled",
    "requires_action",
    "requires_payment_method",
}

# Stripe expects these currencies in whole units instead of hundredths.
_ZERO_DECIMAL_CURRENCIES = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}


def _stripe_amount_to_minor_units(amount: Any, currency: Any) -> int:
    """Convert a display amount into the integer amount Stripe expects."""
    currency_code = normalize_payment_currency_code(currency)
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid_amount") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("invalid_amount")
    if currency_code in _ZERO_DECIMAL_CURRENCIES:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _metadata_pairs(
    metadata: Mapping[str, Any],
    *,
    prefix: str = "metadata",
) -> List[tuple[str, str]]:
    pairs: List[tuple[str, str]] = []
    for key, value in metadata.items():
        if value is None:
            continue
        clean_key = "".join(ch for ch in str(key) if ch.isalnum() or ch in {"_", "-"}).strip()
        if not clean_key:
            continue
        pairs.append((f"{prefix}[{clean_key[:40]}]", str(value)[:500]))
    return pairs


def _stripe_json_success(status: int, data: Any) -> bool:
    return 200 <= status < 300 and not (isinstance(data, dict) and data.get("error"))


def _encode_saved_method(customer_id: str, payment_method_id: str) -> str:
    return f"{customer_id}|{payment_method_id}"


def _decode_saved_method(value: Any) -> tuple[Optional[str], Optional[str]]:
    text = str(value or "").strip()
    if not text:
        return None, None
    if "|" in text:
        customer_id, payment_method_id = text.split("|", 1)
        return customer_id.strip() or None, payment_method_id.strip() or None
    return None, text


class StripeConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="STRIPE_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    SECRET_KEY: Optional[str] = None
    WEBHOOK_SECRET: Optional[str] = None
    BASE_URL: str = Field(default="https://api.stripe.com")
    RETURN_URL: Optional[str] = None
    CANCEL_URL: Optional[str] = None
    PAYMENT_METHOD_TYPES: str = Field(default="card")
    SUPPORTED_CURRENCIES: str = Field(default="")
    RECURRING_ENABLED: bool = Field(default=False)
    VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    WEBHOOK_TOLERANCE_SECONDS: int = Field(default=300, ge=0)

    @field_validator(
        "SECRET_KEY",
        "WEBHOOK_SECRET",
        "RETURN_URL",
        "CANCEL_URL",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def payment_method_types_list(self) -> tuple[str, ...]:
        values: List[str] = []
        for item in (self.PAYMENT_METHOD_TYPES or "").replace(";", ",").split(","):
            value = item.strip().lower()
            if value and value not in values:
                values.append(value)
        return tuple(values or ["card"])

    @property
    def webhook_path(self) -> str:
        return "/webhook/stripe"


class StripePresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_STRIPE_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None
