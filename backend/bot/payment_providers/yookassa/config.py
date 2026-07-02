from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from ..base import (
    ProviderEnvConfig,
    provider_env_file,
)


class YooKassaConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="YOOKASSA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=True)
    SHOP_ID: str | None = None
    SECRET_KEY: str | None = None
    RETURN_URL: str | None = None
    DEFAULT_RECEIPT_EMAIL: str | None = None
    VAT_CODE: int = Field(default=1)
    PAYMENT_MODE: str = Field(default="full_prepayment")
    PAYMENT_SUBJECT: str = Field(default="service")
    AUTOPAYMENTS_ENABLED: bool = Field(default=False)
    AUTOPAYMENTS_REQUIRE_CARD_BINDING: bool = Field(default=True)

    @field_validator("SHOP_ID", "SECRET_KEY", "RETURN_URL", "DEFAULT_RECEIPT_EMAIL", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def autopayments_active(self) -> bool:
        return bool(self.ENABLED and self.AUTOPAYMENTS_ENABLED)

    @property
    def yk_receipt_payment_mode(self) -> str:
        return "service" if self.AUTOPAYMENTS_ENABLED else "full_prepayment"

    @property
    def yk_receipt_payment_subject(self) -> str:
        return "full_payment" if self.AUTOPAYMENTS_ENABLED else "payment"

    @property
    def webhook_path(self) -> str:
        return "/webhook/yookassa"


class YooKassaPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_YOOKASSA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None
