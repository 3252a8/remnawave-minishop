"""Platega provider configuration and presentation models."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, ReportingFeePercent, provider_env_file
from .subscriptions import DEFAULT_SUBSCRIPTION_METHOD


class PlategaConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PLATEGA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    BASE_URL: str = Field(default="https://app.platega.io")
    MERCHANT_ID: str | None = None
    SECRET: str | None = None
    PAYMENT_METHOD: int = Field(default=2)
    SBP_ENABLED: bool = Field(default=False)
    SBP_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    CARD_ENABLED: bool = Field(default=False)
    CARD_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    CRYPTO_ENABLED: bool = Field(default=False)
    CRYPTO_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    INTERNATIONAL_ENABLED: bool = Field(default=False)
    INTERNATIONAL_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    ALL_METHODS_ENABLED: bool = Field(default=False)
    ALL_METHODS_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    SUBSCRIPTION_ENABLED: bool = Field(default=False)
    SUBSCRIPTION_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    SBP_METHOD: int = Field(default=2)
    CARD_METHOD: int = Field(default=11)
    CRYPTO_METHOD: int = Field(default=13)
    INTERNATIONAL_METHOD: int = Field(default=12)
    SUBSCRIPTION_METHOD: int = Field(default=DEFAULT_SUBSCRIPTION_METHOD)
    SBP_REPORTING_FEE_PERCENT: ReportingFeePercent = None
    CARD_REPORTING_FEE_PERCENT: ReportingFeePercent = None
    CRYPTO_REPORTING_FEE_PERCENT: ReportingFeePercent = None
    INTERNATIONAL_REPORTING_FEE_PERCENT: ReportingFeePercent = None
    SUBSCRIPTION_REPORTING_FEE_PERCENT: ReportingFeePercent = None
    RETURN_URL: str | None = None
    FAILED_URL: str | None = None
    SUPPORTED_CURRENCIES: str = Field(default="RUB")

    @field_validator("MERCHANT_ID", "SECRET", "RETURN_URL", "FAILED_URL", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def sbp_method_resolved(self) -> int:
        """Falls back to the legacy ``PAYMENT_METHOD`` for backwards compat."""
        if self.SBP_METHOD != 2:
            return self.SBP_METHOD
        return self.PAYMENT_METHOD or 2

    @property
    def webhook_path(self) -> str:
        return "/webhook/platega"


class _PlategaPresentation(ProviderEnvConfig):
    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None


class PlategaSbpPresentation(_PlategaPresentation):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_SBP_",
        extra="ignore",
    )


class PlategaCardPresentation(_PlategaPresentation):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_CARD_",
        extra="ignore",
    )


class PlategaCryptoPresentation(_PlategaPresentation):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_CRYPTO_",
        extra="ignore",
    )


class PlategaInternationalPresentation(_PlategaPresentation):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_INTERNATIONAL_",
        extra="ignore",
    )


class PlategaAllMethodsPresentation(_PlategaPresentation):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_ALL_METHODS_",
        extra="ignore",
    )


class PlategaSubscriptionPresentation(_PlategaPresentation):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PLATEGA_SUBSCRIPTION_",
        extra="ignore",
    )


__all__ = [
    "PlategaAllMethodsPresentation",
    "PlategaCardPresentation",
    "PlategaConfig",
    "PlategaCryptoPresentation",
    "PlategaInternationalPresentation",
    "PlategaSbpPresentation",
    "PlategaSubscriptionPresentation",
]
