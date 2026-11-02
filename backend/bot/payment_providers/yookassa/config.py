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
    PAYMENT_MODE: str | None = None
    PAYMENT_SUBJECT: str | None = None
    AUTOPAYMENTS_ENABLED: bool = Field(default=False)
    AUTOPAYMENTS_REQUIRE_CARD_BINDING: bool = Field(default=True)
    PAYMENT_METHODS: str = ""

    @field_validator("PAYMENT_METHODS", mode="before")
    @classmethod
    def _normalize_payment_methods(cls, value: Any) -> str:
        methods = list(dict.fromkeys(str(value or "").lower().replace(" ", "").split(",")))
        methods = [method for method in methods if method]
        if any(method not in {"sbp", "bank_card", "other"} for method in methods):
            raise ValueError("Expected sbp, bank_card or other")
        return ",".join(methods)

    @property
    def checkout_methods(self) -> list[str]:
        # DB overrides are assigned directly by the shared settings layer.
        methods = [part.strip().lower() for part in str(self.PAYMENT_METHODS or "").split(",")]
        return list(
            dict.fromkeys(method for method in methods if method in {"sbp", "bank_card", "other"})
        ) or ["other"]

    @field_validator("SHOP_ID", "SECRET_KEY", "RETURN_URL", "DEFAULT_RECEIPT_EMAIL", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("PAYMENT_MODE", "PAYMENT_SUBJECT", mode="before")
    @classmethod
    def _normalize_optional_receipt_field(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip() or None
        return v

    @property
    def autopayments_active(self) -> bool:
        return bool(self.ENABLED and self.AUTOPAYMENTS_ENABLED)

    @property
    def yk_receipt_payment_mode(self) -> str:
        if self.PAYMENT_MODE:
            return self.PAYMENT_MODE
        return "full_payment" if self.AUTOPAYMENTS_ENABLED else "full_prepayment"

    @property
    def yk_receipt_payment_subject(self) -> str:
        if self.PAYMENT_SUBJECT:
            return self.PAYMENT_SUBJECT
        return "service" if self.AUTOPAYMENTS_ENABLED else "payment"

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


class YooKassaSbpPresentation(YooKassaPresentation):
    model_config = SettingsConfigDict(env_prefix="PAYMENT_YOOKASSA_SBP_")


class YooKassaCardPresentation(YooKassaPresentation):
    model_config = SettingsConfigDict(env_prefix="PAYMENT_YOOKASSA_BANK_CARD_")


def order_checkout_methods(methods: list[str]) -> list[str]:
    """Expand the YooKassa slot using its configured order on every checkout surface."""
    from ..registry import get_provider_bundle

    bundle = get_provider_bundle("yookassa_service")
    if (
        not bundle
        or not isinstance(bundle.config, YooKassaConfig)
        or not bundle.config.PAYMENT_METHODS
    ):
        return methods
    ids = {"other": "yookassa", "sbp": "yookassa_sbp", "bank_card": "yookassa_bank_card"}
    selected = [ids[method] for method in bundle.config.checkout_methods]
    result: list[str] = []
    inserted = False
    for method in methods:
        if method in ids.values():
            if not inserted:
                result.extend(selected)
                inserted = True
        else:
            result.append(method)
    return result
