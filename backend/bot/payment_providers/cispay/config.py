from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, provider_env_file


class CisPayConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="CISPAY_",
        extra="ignore",
    )
    ENABLED: bool = False
    SHOP_ID: str = ""
    API_KEY: str = ""
    BASE_URL: str = "https://api.cispay.app"
    RETURN_URL: str = ""
    ALLOW_SANDBOX_PAYMENTS: bool = False
    SUBSCRIPTION_CARD_ENABLED: bool = False
    SUBSCRIPTION_CARD_ADMIN_ONLY_ENABLED: bool = False
    SUBSCRIPTION_SBP_ENABLED: bool = False
    SUBSCRIPTION_SBP_ADMIN_ONLY_ENABLED: bool = False


class CisPayPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_CISPAY_",
        extra="ignore",
    )
    WEBAPP_LABEL_RU: str | None = None
    WEBAPP_LABEL_EN: str | None = None
    WEBAPP_ICON: str | None = None
    TELEGRAM_LABEL_RU: str | None = None
    TELEGRAM_LABEL_EN: str | None = None
    TELEGRAM_EMOJI: str | None = None
