from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, provider_env_file


class OxaPayConfig(ProviderEnvConfig):
    """OxaPay Merchant API settings owned by the provider package."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="OXAPAY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    MERCHANT_API_KEY: str | None = None
    BASE_URL: str = Field(default="https://api.oxapay.com/v1")
    RETURN_URL: str | None = None
    LIFETIME_MINUTES: int = Field(default=60, ge=15, le=2880)
    FEE_PAID_BY_PAYER: bool | None = None
    UNDER_PAID_COVERAGE: float | None = Field(default=None, ge=0, le=60)
    TO_CURRENCY: str | None = None
    AUTO_WITHDRAWAL: bool | None = None
    MIXED_PAYMENT: bool | None = None
    SANDBOX: bool = Field(default=False)
    TRUSTED_IPS: str = Field(default="")

    @field_validator(
        "MERCHANT_API_KEY",
        "RETURN_URL",
        "TO_CURRENCY",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator(
        "FEE_PAID_BY_PAYER",
        "UNDER_PAID_COVERAGE",
        "AUTO_WITHDRAWAL",
        "MIXED_PAYMENT",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("TO_CURRENCY")
    @classmethod
    def _validate_to_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized != "USDT":
            raise ValueError("OxaPay invoice conversion supports only USDT")
        return normalized

    @property
    def webhook_path(self) -> str:
        return "/webhook/oxapay"

    def full_webhook_url(self, base: str | None) -> str | None:
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"

    @property
    def trusted_ips_list(self) -> list[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class OxaPayPresentation(ProviderEnvConfig):
    """Admin-tunable OxaPay button text and icon overrides."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_OXAPAY_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


__all__ = ["OxaPayConfig", "OxaPayPresentation"]
