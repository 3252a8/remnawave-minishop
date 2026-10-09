from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, provider_env_file


class AnoreConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(), env_file_encoding="utf-8", env_prefix="ANORE_", extra="ignore"
    )
    ENABLED: bool = False
    API_KEY: str = ""
    WEBHOOK_SECRET: str = ""
    SHOP_ID: int | None = Field(default=None, gt=0)
    BASE_URL: str = "https://api.anore.cc/v1"
    RETURN_URL: str = ""
    METHODS: str = ""

    @field_validator("SHOP_ID", mode="before")
    @classmethod
    def empty_shop_id(cls, value: object) -> object:
        return None if value == "" else value


class AnorePresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_ANORE_",
        extra="ignore",
    )
    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None
