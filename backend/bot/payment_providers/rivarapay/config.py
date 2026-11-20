"""RivaraPay settings for the two hosted checkout methods."""

from pydantic_settings import SettingsConfigDict

from ..base import ProviderEnvConfig, ProviderManifestField, ReportingFeePercent, provider_env_file

INTENTS_URL = "https://api.rivarapay.io/api/v1/payment-intents"


class RivaraPayConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="RIVARAPAY_",
        extra="ignore",
        str_strip_whitespace=True,
    )

    API_KEY: str = ""
    WEBHOOK_SECRET: str = ""
    RETURN_URL: str = ""
    SBP_ENABLED: bool = False
    SBP_ADMIN_ONLY_ENABLED: bool = False
    SBP_REPORTING_FEE_PERCENT: ReportingFeePercent = None
    CRYPTO_ENABLED: bool = False
    CRYPTO_ADMIN_ONLY_ENABLED: bool = False
    CRYPTO_REPORTING_FEE_PERCENT: ReportingFeePercent = None

    @property
    def _trusted_api_urls(self) -> tuple[str, ...]:
        return (INTENTS_URL,)

    @property
    def credentials_configured(self) -> bool:
        return self.API_KEY.startswith("live_") and bool(self.WEBHOOK_SECRET)


CONFIG_MANIFEST = tuple(
    ProviderManifestField(
        f"RIVARAPAY_{attr}",
        field_type,
        label,
        description=description,
        secret=secret,
        subsection="RivaraPay",
        attr=attr,
    )
    for attr, field_type, label, description, secret in (
        ("API_KEY", "string", "Live API key", "Requires payments:write and payments:read.", True),
        ("WEBHOOK_SECRET", "string", "Webhook signing secret", "", True),
        ("RETURN_URL", "url", "Return URL", "", False),
    )
)
