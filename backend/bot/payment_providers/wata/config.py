from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional, Tuple

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from ..base import (
    ProviderEnvConfig,
    parse_supported_currency_codes,
    provider_env_file,
    provider_runtime_enabled,
)
from ..shared import first_value

WATA_PROVIDER = "wata"
WATA_CRYPTO_PROVIDER = "wata_crypto"
WATA_SUPPORTED_CURRENCIES = ("RUB", "USD", "EUR")
_WATA_SUPPORTED_CURRENCIES_DEFAULT = ",".join(WATA_SUPPORTED_CURRENCIES)
_WATA_IN_PROGRESS_STATUSES = {"created", "pending"}
_WATA_LINK_OPENED_STATUSES = {"opened", "open"}
_WATA_LINK_DEFAULT_TTL_MINUTES = 15
_WATA_LINK_MIN_TTL_MINUTES = 15
_WATA_LINK_MAX_TTL_MINUTES = 30 * 24 * 60


def _clamp_wata_link_ttl_minutes(value: Any, *, default: int) -> int:
    if isinstance(value, str):
        value = value.strip()
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return default
    return min(_WATA_LINK_MAX_TTL_MINUTES, max(_WATA_LINK_MIN_TTL_MINUTES, minutes))


def _parse_wata_datetime(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        iso_value = str(raw).strip()
        if iso_value.endswith("Z"):
            iso_value = iso_value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(iso_value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _wata_success_status(status: int, _body: Any) -> bool:
    return 200 <= status < 300


def _normalized_wata_status(payload: Optional[Mapping[str, Any]]) -> str:
    if not payload:
        return ""
    return (
        str(
            payload.get("transactionStatus")
            or payload.get("status")
            or payload.get("statusName")
            or ""
        )
        .strip()
        .lower()
    )


def _wata_transaction_id(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
    return first_value(payload, "transactionId", "id")


def _wata_payment_link_id(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
    return first_value(payload, "paymentLinkId", "payment_link_id")


def _normalize_terminal_public_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _wata_provider_from_method(method: Any) -> str:
    normalized = str(method or "").strip().lower()
    if normalized in {WATA_CRYPTO_PROVIDER, "crypto", "wata_crypto"}:
        return WATA_CRYPTO_PROVIDER
    return WATA_PROVIDER


@dataclass(frozen=True)
class WataTerminalProfile:
    provider: str
    api_token: str
    terminal_id: str = ""
    terminal_public_id: str = ""
    return_url: Optional[str] = None
    failed_url: Optional[str] = None
    link_ttl_minutes: int = _WATA_LINK_DEFAULT_TTL_MINUTES
    public_key: Optional[str] = None
    supported_currencies: Tuple[str, ...] = WATA_SUPPORTED_CURRENCIES

    @property
    def configured(self) -> bool:
        return bool(self.api_token)

    @property
    def log_label(self) -> str:
        return "Wata crypto" if self.provider == WATA_CRYPTO_PROVIDER else "Wata"


class WataConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="WATA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    API_TOKEN: Optional[str] = None
    TERMINAL_ID: Optional[str] = None
    TERMINAL_PUBLIC_ID: Optional[str] = None
    BASE_URL: str = Field(default="https://api.wata.pro/api/h2h")
    RETURN_URL: Optional[str] = None
    FAILED_URL: Optional[str] = None
    LINK_TTL_MINUTES: int = Field(default=_WATA_LINK_DEFAULT_TTL_MINUTES)
    SUPPORTED_CURRENCIES: str = Field(default=_WATA_SUPPORTED_CURRENCIES_DEFAULT)
    CRYPTO_ENABLED: bool = Field(default=False)
    CRYPTO_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    CRYPTO_API_TOKEN: Optional[str] = None
    CRYPTO_TERMINAL_ID: Optional[str] = None
    CRYPTO_TERMINAL_PUBLIC_ID: Optional[str] = None
    CRYPTO_RETURN_URL: Optional[str] = None
    CRYPTO_FAILED_URL: Optional[str] = None
    CRYPTO_LINK_TTL_MINUTES: Optional[int] = None
    CRYPTO_PUBLIC_KEY: Optional[str] = None
    CRYPTO_SUPPORTED_CURRENCIES: Optional[str] = None
    WEBHOOK_VERIFY_SIGNATURE: bool = Field(default=True)
    PUBLIC_KEY: Optional[str] = None
    TRUSTED_IPS: str = Field(default="62.84.126.140,51.250.106.150")

    @field_validator("LINK_TTL_MINUTES", mode="before")
    @classmethod
    def _clamp_link_ttl_minutes(cls, v):
        return _clamp_wata_link_ttl_minutes(v, default=_WATA_LINK_DEFAULT_TTL_MINUTES)

    @field_validator("CRYPTO_LINK_TTL_MINUTES", mode="before")
    @classmethod
    def _clamp_optional_link_ttl_minutes(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return _clamp_wata_link_ttl_minutes(v, default=_WATA_LINK_DEFAULT_TTL_MINUTES)

    @field_validator(
        "API_TOKEN",
        "TERMINAL_ID",
        "TERMINAL_PUBLIC_ID",
        "RETURN_URL",
        "FAILED_URL",
        "CRYPTO_API_TOKEN",
        "CRYPTO_TERMINAL_ID",
        "CRYPTO_TERMINAL_PUBLIC_ID",
        "CRYPTO_RETURN_URL",
        "CRYPTO_FAILED_URL",
        "CRYPTO_PUBLIC_KEY",
        "CRYPTO_SUPPORTED_CURRENCIES",
        "PUBLIC_KEY",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/wata"

    @property
    def trusted_ips_list(self) -> List[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]

    def profile_for_method(self, method: Any) -> WataTerminalProfile:
        provider = _wata_provider_from_method(method)
        if provider == WATA_CRYPTO_PROVIDER:
            supported = (
                parse_supported_currency_codes(
                    self.CRYPTO_SUPPORTED_CURRENCIES or self.SUPPORTED_CURRENCIES
                )
                or WATA_SUPPORTED_CURRENCIES
            )
            return WataTerminalProfile(
                provider=WATA_CRYPTO_PROVIDER,
                api_token=self.CRYPTO_API_TOKEN or "",
                terminal_id=self.CRYPTO_TERMINAL_ID or "",
                terminal_public_id=self.CRYPTO_TERMINAL_PUBLIC_ID or "",
                return_url=self.CRYPTO_RETURN_URL or self.RETURN_URL,
                failed_url=self.CRYPTO_FAILED_URL or self.FAILED_URL,
                link_ttl_minutes=self.CRYPTO_LINK_TTL_MINUTES or self.LINK_TTL_MINUTES,
                public_key=self.CRYPTO_PUBLIC_KEY or self.PUBLIC_KEY,
                supported_currencies=supported,
            )

        supported = (
            parse_supported_currency_codes(self.SUPPORTED_CURRENCIES) or WATA_SUPPORTED_CURRENCIES
        )
        return WataTerminalProfile(
            provider=WATA_PROVIDER,
            api_token=self.API_TOKEN or "",
            terminal_id=self.TERMINAL_ID or "",
            terminal_public_id=self.TERMINAL_PUBLIC_ID or "",
            return_url=self.RETURN_URL,
            failed_url=self.FAILED_URL,
            link_ttl_minutes=self.LINK_TTL_MINUTES,
            public_key=self.PUBLIC_KEY,
            supported_currencies=supported,
        )

    @property
    def fiat_profile(self) -> WataTerminalProfile:
        return self.profile_for_method(WATA_PROVIDER)

    @property
    def crypto_profile(self) -> WataTerminalProfile:
        return self.profile_for_method(WATA_CRYPTO_PROVIDER)

    @property
    def fiat_runtime_enabled(self) -> bool:
        return bool(provider_runtime_enabled(self) and self.fiat_profile.configured)

    @property
    def crypto_runtime_enabled(self) -> bool:
        return bool(
            (self.CRYPTO_ENABLED or self.CRYPTO_ADMIN_ONLY_ENABLED)
            and self.crypto_profile.configured
        )


class WataPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_WATA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class WataCryptoPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_WATA_CRYPTO_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None
