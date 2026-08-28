"""RollyPay provider configuration."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, provider_env_file


class RollyPayConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="ROLLYPAY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    BASE_URL: str = Field(default="https://rollypay.io/api/v1")
    API_KEY: str | None = None
    SIGNING_SECRET: str | None = None
    TERMINAL_ID: str | None = None

    ALL_METHODS_ENABLED: bool = Field(default=True)
    ALL_METHODS_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    SBP_ENABLED: bool = Field(default=False)
    SBP_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    CARD_ENABLED: bool = Field(default=False)
    CARD_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    INTERNATIONAL_ENABLED: bool = Field(default=False)
    INTERNATIONAL_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    CRYPTO_ENABLED: bool = Field(default=False)
    CRYPTO_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    SUBSCRIPTION_ENABLED: bool = Field(default=False)
    SUBSCRIPTION_ADMIN_ONLY_ENABLED: bool = Field(default=False)

    TEST_MODE: bool = Field(default=False)
    WEBHOOK_TOLERANCE_SECONDS: int = Field(default=300, ge=30, le=3600)
    WEBHOOK_LOOKUP_TIMEOUT_SECONDS: float = Field(default=8, ge=1, le=9)
    PLAN_CACHE_SECONDS: int = Field(default=300, ge=30, le=3600)
    RECONCILE_INTERVAL_SECONDS: int = Field(default=300, ge=60)
    RECONCILE_BATCH_SIZE: int = Field(default=100, ge=1, le=500)
    SUCCESS_URL: str | None = None
    FAIL_URL: str | None = None

    @field_validator(
        "API_KEY",
        "SIGNING_SECRET",
        "TERMINAL_ID",
        "SUCCESS_URL",
        "FAIL_URL",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("BASE_URL", mode="before")
    @classmethod
    def _normalize_base_url(cls, value: Any) -> str:
        return str(value or "https://rollypay.io/api/v1").strip().rstrip("/")

    @property
    def webhook_path(self) -> str:
        return "/webhook/rollypay"


__all__ = ["RollyPayConfig"]
