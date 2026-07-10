from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from ..base import (
    ProviderEnvConfig,
    normalize_payment_currency_code,
    provider_env_file,
)

# Overpay is built on the BeGateway platform and settles in a broad set of
# currencies; which ones a given shop may actually charge depends on its
# contract. This list gates the payment methods the bot offers — keep it wide
# and let the gateway reject anything the shop is not enabled for.
OVERPAY_SUPPORTED_CURRENCIES = (
    "USD",
    "EUR",
    "RUB",
    "GBP",
    "PLN",
    "TRY",
    "KZT",
    "UAH",
    "AZN",
    "AMD",
    "KGS",
    "UZS",
    "GEL",
    "BYN",
)

# Currencies whose minimal unit equals the major unit (no cents). Overpay,
# like BeGateway, always transmits amounts in minimal currency units.
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


def overpay_amount_to_minor_units(amount: Any, currency: Any) -> int:
    """Convert a display amount into the integer minimal-unit amount Overpay expects."""
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


class OverpayConfig(ProviderEnvConfig):
    """All Overpay env vars. Lives inside the provider module."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="OVERPAY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    SHOP_ID: str | None = None
    SECRET_KEY: str | None = None
    CHECKOUT_URL: str = Field(default="https://checkout.overpay.io")
    GATEWAY_URL: str = Field(default="https://gateway.overpay.io")
    RETURN_URL: str | None = None
    SUCCESS_URL: str | None = None
    DECLINE_URL: str | None = None
    FAIL_URL: str | None = None
    LANGUAGE: str | None = None
    TEST_MODE: bool = Field(default=False)
    RECURRING_ENABLED: bool = Field(default=False)
    VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    TRUSTED_IPS: str = Field(default="")

    @field_validator(
        "SHOP_ID",
        "SECRET_KEY",
        "RETURN_URL",
        "SUCCESS_URL",
        "DECLINE_URL",
        "FAIL_URL",
        "LANGUAGE",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("LANGUAGE")
    @classmethod
    def _normalize_language(cls, v: Any) -> str | None:
        if v is None:
            return None
        language = str(v).strip().lower().split("-", 1)[0].split("_", 1)[0]
        return language or None

    @property
    def webhook_path(self) -> str:
        return "/webhook/overpay"

    def full_webhook_url(self, base: str | None) -> str | None:
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"

    @property
    def trusted_ips_list(self) -> list[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class OverpayPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for Overpay."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_OVERPAY_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None
