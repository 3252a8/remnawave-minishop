from pydantic import Field
from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, provider_env_file


class CryptomusConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="CRYPTOMUS_",
        extra="ignore",
    )
    ENABLED: bool = False
    MERCHANT_ID: str = ""
    API_KEY: str = ""
    BASE_URL: str = "https://api.cryptomus.com/v1"
    RETURN_URL: str = ""
    TO_CURRENCY: str = ""
    NETWORK: str = ""
    LIFETIME_SECONDS: int = Field(default=3600, ge=300, le=43200)
    SUBSCRIPTION_ENABLED: bool = False
    SUBSCRIPTION_ADMIN_ONLY_ENABLED: bool = False


class CryptomusPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_CRYPTOMUS_",
        extra="ignore",
    )
    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None
