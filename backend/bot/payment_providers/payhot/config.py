from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, provider_env_file

PAYHOT_API_URL = "https://app.pay.hot/api/v2/payments"

PAYMENT_METHOD_CURRENCIES = {
    "card": ("RUB", "USD", "EUR"),
    "sbp": ("RUB",),
    "sberpay": ("RUB",),
    "applepay": ("RUB", "USD", "EUR"),
    "googlepay": ("RUB", "USD", "EUR"),
    "crypto": ("RUB",),
}


class PayHotConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYHOT_",
        extra="ignore",
    )

    ENABLED: bool = False
    API_KEY: str = ""
    WEBHOOK_SECRET: str = ""
    PAYMENT_METHOD: str = "card"

    @property
    def _trusted_api_urls(self) -> tuple[str, ...]:
        return (PAYHOT_API_URL,)

    @property
    def payment_method(self) -> str:
        return self.PAYMENT_METHOD.strip().lower()

    @property
    def supported_currencies(self) -> tuple[str, ...]:
        return PAYMENT_METHOD_CURRENCIES.get(self.payment_method, ())
