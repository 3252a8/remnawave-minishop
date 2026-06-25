from __future__ import annotations

import logging
import re
import secrets
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    TypeVar,
    overload,
)

from pydantic import field_validator

from config.settings_models import (
    CompatibilitySettings,
    DBSettings,
    EmailSettings,
    PanelSettings,
    PaymentSettings,
    ReferralSettings,
    SupportSettings,
    WebAppSettings,
)
from config.tariffs_config import TariffsConfig, load_tariffs_config
from config.traffic_strategy import normalize_traffic_limit_strategy
from config.webapp_themes_config import WebappThemesConfig, resolved_webapp_themes_catalog

_T = TypeVar("_T")
_Owner = TypeVar("_Owner")

if TYPE_CHECKING:

    class _ComputedField(Generic[_T]):
        @overload
        def __get__(self, obj: None, owner: type[_Owner]) -> property: ...

        @overload
        def __get__(self, obj: _Owner, owner: type[_Owner] | None = None) -> _T: ...

        def __get__(
            self,
            obj: object | None,
            owner: type[object] | None = None,
        ) -> object: ...

    def computed_field(func: Callable[[Any], _T]) -> _ComputedField[_T]: ...

    class _SettingsFieldsProtocol(Protocol):
        POSTGRES_USER: str
        POSTGRES_PASSWORD: str
        POSTGRES_HOST: str
        POSTGRES_PORT: int
        POSTGRES_DB: str
        SMTP_HOST: str
        SMTP_PORT: int
        SMTP_FALLBACK_PORTS: Optional[str]
        SMTP_TIMEOUT_SECONDS: int
        SMTP_USERNAME: Optional[str]
        SMTP_PASSWORD: Optional[str]
        SMTP_FROM_EMAIL: Optional[str]
        SMTP_FROM_NAME: Optional[str]
        SMTP_STARTTLS: bool
        SMTP_USE_SSL: bool
        EMAIL_CODE_TTL_SECONDS: int
        EMAIL_CODE_RESEND_SECONDS: int
        EMAIL_CODE_MAX_ATTEMPTS: int
        BRUTE_FORCE_MAX_FAILURES: int
        BRUTE_FORCE_WINDOW_SECONDS: int
        BRUTE_FORCE_LOCK_SECONDS: int
        WEBAPP_TITLE: str
        WEBAPP_PRIMARY_COLOR: str
        WEBAPP_LOGO_URL: Optional[str]
        WEBAPP_FAVICON_USE_CUSTOM: bool
        WEBAPP_FAVICON_URL: Optional[str]
        WEBAPP_LOGO_FAVICON_URL: Optional[str]
        WEBAPP_SESSION_TTL_SECONDS: int
        WEBAPP_SESSION_SECRET: str
        WEBHOOK_SECRET_TOKEN: str
        WEBAPP_AUTH_MAX_AGE_SECONDS: int
        WEBAPP_LOGIN_TOKEN_TTL_SECONDS: int
        WEBAPP_SERVER_HOST: str
        WEBAPP_SERVER_PORT: int
        WEBAPP_ENABLED: bool
        DEFAULT_CURRENCY_SYMBOL: str
        PAYMENT_REQUEST_TIMEOUT_SECONDS: float
        ADMIN_IDS_STR: str
        PANEL_WRITE_MODE: str
        PANEL_API_URL: Optional[str]
        PANEL_API_KEY: Optional[str]
        PANEL_API_COOKIE: Optional[str]
        PANEL_WEBHOOK_SECRET: Optional[str]
        PANEL_API_TOTAL_TIMEOUT_SECONDS: float
        PANEL_API_CONNECT_TIMEOUT_SECONDS: float
        PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS: float
        PANEL_API_SOCK_READ_TIMEOUT_SECONDS: float
        APP_RUNTIME_MODE: str
        TRIAL_TRAFFIC_LIMIT_GB: Optional[float]
        TRIAL_PREMIUM_TRAFFIC_LIMIT_GB: Optional[float]
        USER_TRAFFIC_LIMIT_GB: Optional[float]
        USER_SQUAD_UUIDS: Optional[str]
        TRIAL_SQUAD_UUIDS: Optional[str]
        TRIAL_PREMIUM_SQUAD_UUIDS: Optional[str]
        DISPOSABLE_EMAIL_DOMAINS: str
        USER_EXTERNAL_SQUAD_UUID: Optional[str]
        TRUSTED_PROXIES: Optional[str]
        WEBHOOK_BASE_URL: Optional[str]
        MONTH_1_ENABLED: bool
        RUB_PRICE_1_MONTH: Optional[int]
        MONTH_3_ENABLED: bool
        RUB_PRICE_3_MONTHS: Optional[int]
        MONTH_6_ENABLED: bool
        RUB_PRICE_6_MONTHS: Optional[int]
        MONTH_12_ENABLED: bool
        RUB_PRICE_12_MONTHS: Optional[int]
        STARS_ENABLED: bool
        STARS_ADMIN_ONLY_ENABLED: bool
        STARS_PRICE_1_MONTH: Optional[int]
        STARS_PRICE_3_MONTHS: Optional[int]
        STARS_PRICE_6_MONTHS: Optional[int]
        STARS_PRICE_12_MONTHS: Optional[int]
        TRAFFIC_PACKAGES: Optional[str]
        STARS_TRAFFIC_PACKAGES: Optional[str]
        TARIFF_TRAFFIC_WARNING_LEVELS: str
        TARIFFS_CONFIG_PATH: str
        WEBAPP_DEFAULT_THEME: Optional[str]
        WEBAPP_THEMES_DIR: str
        REFERRAL_BONUS_DAYS_INVITER_1_MONTH: Optional[int]
        REFERRAL_BONUS_DAYS_INVITER_3_MONTHS: Optional[int]
        REFERRAL_BONUS_DAYS_INVITER_6_MONTHS: Optional[int]
        REFERRAL_BONUS_DAYS_INVITER_12_MONTHS: Optional[int]
        REFERRAL_BONUS_DAYS_REFEREE_1_MONTH: Optional[int]
        REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS: Optional[int]
        REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS: Optional[int]
        REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS: Optional[int]
        REFERRAL_ONE_BONUS_PER_REFEREE: bool
        REFERRAL_WELCOME_BONUS_DAYS: int
        REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED: bool
        LEGACY_REFS: bool
        MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED: bool
        MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED: bool
        MIGRATION_REMNASHOP_IMPORTED_AT: Optional[str]
        MIGRATION_REMNASHOP_NOTES: Optional[str]
        SUPPORT_LINK: Optional[str]
        SUPPORT_TICKETS_ENABLED: bool
        SUPPORT_TICKET_MAX_BODY_LENGTH: int
        SUPPORT_TICKET_MAX_SUBJECT_LENGTH: int
        SUPPORT_TICKET_RATE_LIMIT_PER_HOUR: int
        SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED: bool
        SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS: int
        SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS: int
        PAYMENT_METHODS_ORDER: Optional[str]
        SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED: bool
        DEFAULT_LANGUAGE: str
        SUBSCRIPTION_PURCHASE_DESCRIPTION_EN: str
        SUBSCRIPTION_PURCHASE_DESCRIPTION_RU: str

    class _SettingsComputedMixinBase(_SettingsFieldsProtocol):
        pass

else:
    from pydantic import computed_field

    class _SettingsComputedMixinBase:
        pass


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,;\r\n]+", value) if item.strip()]


class SettingsComputedMixin(_SettingsComputedMixinBase):
    @computed_field
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    def db_settings(self) -> DBSettings:
        return DBSettings(
            user=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @computed_field
    def email_settings(self) -> EmailSettings:
        return EmailSettings(
            smtp_host=self.SMTP_HOST,
            smtp_port=self.SMTP_PORT,
            smtp_fallback_ports=self.SMTP_FALLBACK_PORTS,
            smtp_timeout_seconds=self.SMTP_TIMEOUT_SECONDS,
            smtp_username=self.SMTP_USERNAME,
            smtp_password=self.SMTP_PASSWORD,
            smtp_from_email=self.SMTP_FROM_EMAIL,
            smtp_from_name=self.SMTP_FROM_NAME,
            smtp_starttls=self.SMTP_STARTTLS,
            smtp_use_ssl=self.SMTP_USE_SSL,
            email_code_ttl_seconds=self.EMAIL_CODE_TTL_SECONDS,
            email_code_resend_seconds=self.EMAIL_CODE_RESEND_SECONDS,
            email_code_max_attempts=self.EMAIL_CODE_MAX_ATTEMPTS,
            brute_force_max_failures=self.BRUTE_FORCE_MAX_FAILURES,
            brute_force_window_seconds=self.BRUTE_FORCE_WINDOW_SECONDS,
            brute_force_lock_seconds=self.BRUTE_FORCE_LOCK_SECONDS,
        )

    @computed_field
    def webapp_settings(self) -> WebAppSettings:
        return WebAppSettings(
            title=self.WEBAPP_TITLE,
            primary_color=self.WEBAPP_PRIMARY_COLOR,
            logo_url=self.WEBAPP_LOGO_URL,
            favicon_use_custom=self.WEBAPP_FAVICON_USE_CUSTOM,
            favicon_url=self.WEBAPP_FAVICON_URL,
            logo_favicon_url=self.WEBAPP_LOGO_FAVICON_URL,
            session_ttl_seconds=self.WEBAPP_SESSION_TTL_SECONDS,
            session_secret=self.WEBAPP_SESSION_SECRET,
            webhook_secret_token=self.WEBHOOK_SECRET_TOKEN,
            auth_max_age_seconds=self.WEBAPP_AUTH_MAX_AGE_SECONDS,
            login_token_ttl_seconds=self.WEBAPP_LOGIN_TOKEN_TTL_SECONDS,
            server_host=self.WEBAPP_SERVER_HOST,
            server_port=self.WEBAPP_SERVER_PORT,
            enabled=self.WEBAPP_ENABLED,
            trusted_proxies=self.trusted_proxies,
        )

    @property
    def payment_settings(self) -> PaymentSettings:
        return PaymentSettings(
            default_currency_symbol=self.DEFAULT_CURRENCY_SYMBOL,
            payment_request_timeout_seconds=self.PAYMENT_REQUEST_TIMEOUT_SECONDS,
            payment_methods_order=self.payment_methods_order,
            subscription_options=self.subscription_options,
            stars_subscription_options=self.stars_subscription_options,
            traffic_packages=self.traffic_packages,
            stars_traffic_packages=self.stars_traffic_packages,
            traffic_sale_mode=self.traffic_sale_mode,
        )

    @property
    def referral_settings(self) -> ReferralSettings:
        return ReferralSettings(
            bonus_days_inviter_1_month=self.REFERRAL_BONUS_DAYS_INVITER_1_MONTH,
            bonus_days_inviter_3_months=self.REFERRAL_BONUS_DAYS_INVITER_3_MONTHS,
            bonus_days_inviter_6_months=self.REFERRAL_BONUS_DAYS_INVITER_6_MONTHS,
            bonus_days_inviter_12_months=self.REFERRAL_BONUS_DAYS_INVITER_12_MONTHS,
            bonus_days_referee_1_month=self.REFERRAL_BONUS_DAYS_REFEREE_1_MONTH,
            bonus_days_referee_3_months=self.REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS,
            bonus_days_referee_6_months=self.REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS,
            bonus_days_referee_12_months=self.REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS,
            one_bonus_per_referee=self.REFERRAL_ONE_BONUS_PER_REFEREE,
            welcome_bonus_days=self.REFERRAL_WELCOME_BONUS_DAYS,
            welcome_bonus_without_telegram_enabled=self.REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED,
            legacy_refs_enabled=self.LEGACY_REFS,
        )

    @property
    def support_settings(self) -> SupportSettings:
        return SupportSettings(
            link=self.SUPPORT_LINK,
            tickets_enabled=self.SUPPORT_TICKETS_ENABLED,
            ticket_max_body_length=self.SUPPORT_TICKET_MAX_BODY_LENGTH,
            ticket_max_subject_length=self.SUPPORT_TICKET_MAX_SUBJECT_LENGTH,
            ticket_rate_limit_per_hour=self.SUPPORT_TICKET_RATE_LIMIT_PER_HOUR,
            admin_email_notifications_enabled=self.SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED,
            admin_notification_cooldown_seconds=self.SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS,
            admin_email_cooldown_seconds=self.SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS,
        )

    @property
    def panel_settings(self) -> PanelSettings:
        return PanelSettings(
            api_url=self.PANEL_API_URL,
            api_key=self.PANEL_API_KEY,
            api_cookie=self.PANEL_API_COOKIE,
            webhook_secret=self.PANEL_WEBHOOK_SECRET,
            write_mode=self.PANEL_WRITE_MODE,
            dry_run_enabled=self.panel_dry_run_enabled,
            api_total_timeout_seconds=self.PANEL_API_TOTAL_TIMEOUT_SECONDS,
            api_connect_timeout_seconds=self.PANEL_API_CONNECT_TIMEOUT_SECONDS,
            api_sock_connect_timeout_seconds=self.PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS,
            api_sock_read_timeout_seconds=self.PANEL_API_SOCK_READ_TIMEOUT_SECONDS,
        )

    @property
    def compatibility_settings(self) -> CompatibilitySettings:
        return CompatibilitySettings(
            remnashop_referral_code_compat_enabled=self.MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED,
            remnashop_promo_code_compat_enabled=self.MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED,
            remnashop_imported_at=self.MIGRATION_REMNASHOP_IMPORTED_AT,
            remnashop_notes=self.MIGRATION_REMNASHOP_NOTES,
        )

    @computed_field
    def ADMIN_IDS(self) -> List[int]:
        if self.ADMIN_IDS_STR:
            try:
                return [
                    int(admin_id.strip())
                    for admin_id in self.ADMIN_IDS_STR.split(",")
                    if admin_id.strip().isdigit()
                ]
            except ValueError:
                logging.error(
                    f"Invalid ADMIN_IDS_STR format: '{self.ADMIN_IDS_STR}'. Expected comma-separated integers."  # noqa: E501
                )
                return []
        return []

    @computed_field
    def PRIMARY_ADMIN_ID(self) -> Optional[int]:
        ids = self.ADMIN_IDS
        return ids[0] if ids else None

    @computed_field
    def panel_dry_run_enabled(self) -> bool:
        mode = str(self.PANEL_WRITE_MODE or "auto").strip().lower().replace("-", "_")
        if mode == "dry_run":
            return True
        if mode == "live":
            return False
        runtime = str(self.APP_RUNTIME_MODE or "production").strip().lower()
        return runtime in {"dev", "development", "local", "test", "testing"}

    @computed_field
    def trial_traffic_limit_bytes(self) -> int:
        if self.TRIAL_TRAFFIC_LIMIT_GB is None or self.TRIAL_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.TRIAL_TRAFFIC_LIMIT_GB * (1024**3))

    @computed_field
    def trial_premium_traffic_limit_bytes(self) -> int:
        if self.TRIAL_PREMIUM_TRAFFIC_LIMIT_GB is None or self.TRIAL_PREMIUM_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.TRIAL_PREMIUM_TRAFFIC_LIMIT_GB * (1024**3))

    @computed_field
    def user_traffic_limit_bytes(self) -> int:
        if self.USER_TRAFFIC_LIMIT_GB is None or self.USER_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.USER_TRAFFIC_LIMIT_GB * (1024**3))

    @computed_field
    def parsed_user_squad_uuids(self) -> Optional[List[str]]:
        if self.USER_SQUAD_UUIDS:
            return [uuid.strip() for uuid in self.USER_SQUAD_UUIDS.split(",") if uuid.strip()]
        return None

    @computed_field
    def parsed_trial_squad_uuids(self) -> Optional[List[str]]:
        if self.TRIAL_SQUAD_UUIDS:
            trial_squads = [
                uuid.strip() for uuid in self.TRIAL_SQUAD_UUIDS.split(",") if uuid.strip()
            ]
            if trial_squads:
                return trial_squads
        return self.parsed_user_squad_uuids

    @computed_field
    def parsed_trial_premium_squad_uuids(self) -> Optional[List[str]]:
        if self.TRIAL_PREMIUM_SQUAD_UUIDS:
            premium_squads = [
                uuid.strip() for uuid in self.TRIAL_PREMIUM_SQUAD_UUIDS.split(",") if uuid.strip()
            ]
            if premium_squads:
                return premium_squads
        return None

    @computed_field
    def disposable_email_domains(self) -> List[str]:
        domains: List[str] = []
        for domain in _split_csv(self.DISPOSABLE_EMAIL_DOMAINS):
            normalized = domain.strip().lower().lstrip("@.")
            if normalized and normalized not in domains:
                domains.append(normalized)
        return domains

    @computed_field
    def parsed_user_external_squad_uuid(self) -> Optional[str]:
        if self.USER_EXTERNAL_SQUAD_UUID:
            cleaned = self.USER_EXTERNAL_SQUAD_UUID.strip()
            if cleaned:
                return cleaned
        return None

    @computed_field
    def trusted_proxies(self) -> List[str]:
        return _split_csv(self.TRUSTED_PROXIES)

    @computed_field
    def telegram_webhook_path(self) -> str:
        return "/tg/webhook"

    @computed_field
    def panel_webhook_path(self) -> str:
        return "/webhook/panel"

    @computed_field
    def panel_full_webhook_url(self) -> Optional[str]:
        base = self.WEBHOOK_BASE_URL
        if base:
            return f"{base.rstrip('/')}{self.panel_webhook_path}"
        return None

    @computed_field
    def subscription_options(self) -> Dict[int, float]:
        options: Dict[int, float] = {}

        if self.MONTH_1_ENABLED and self.RUB_PRICE_1_MONTH is not None:
            options[1] = float(self.RUB_PRICE_1_MONTH)
        if self.MONTH_3_ENABLED and self.RUB_PRICE_3_MONTHS is not None:
            options[3] = float(self.RUB_PRICE_3_MONTHS)
        if self.MONTH_6_ENABLED and self.RUB_PRICE_6_MONTHS is not None:
            options[6] = float(self.RUB_PRICE_6_MONTHS)
        if self.MONTH_12_ENABLED and self.RUB_PRICE_12_MONTHS is not None:
            options[12] = float(self.RUB_PRICE_12_MONTHS)
        return options

    @computed_field
    def stars_subscription_options(self) -> Dict[int, int]:
        options: Dict[int, int] = {}
        stars_enabled = self.STARS_ENABLED or self.STARS_ADMIN_ONLY_ENABLED
        if stars_enabled and self.MONTH_1_ENABLED and self.STARS_PRICE_1_MONTH is not None:
            options[1] = self.STARS_PRICE_1_MONTH
        if stars_enabled and self.MONTH_3_ENABLED and self.STARS_PRICE_3_MONTHS is not None:
            options[3] = self.STARS_PRICE_3_MONTHS
        if stars_enabled and self.MONTH_6_ENABLED and self.STARS_PRICE_6_MONTHS is not None:
            options[6] = self.STARS_PRICE_6_MONTHS
        if stars_enabled and self.MONTH_12_ENABLED and self.STARS_PRICE_12_MONTHS is not None:
            options[12] = self.STARS_PRICE_12_MONTHS
        return options

    @computed_field
    def traffic_packages(self) -> Dict[float, float]:
        """
        Mapping of traffic size in GB to price in the default currency.
        """
        packages: Dict[float, float] = {}
        raw = (self.TRAFFIC_PACKAGES or "").strip()
        if not raw:
            return packages
        for part in raw.split(","):
            chunk = part.strip()
            if not chunk or ":" not in chunk:
                continue
            size_str, price_str = chunk.split(":", 1)
            try:
                size_gb = float(size_str.strip())
                price_val = float(price_str.strip())
                if size_gb > 0 and price_val >= 0:
                    packages[size_gb] = price_val
            except ValueError:
                logging.warning("Invalid TRAFFIC_PACKAGES entry skipped: %s", chunk)
                continue
        return packages

    @computed_field
    def stars_traffic_packages(self) -> Dict[float, int]:
        """
        Mapping of traffic size in GB to price in Telegram Stars.
        """
        packages: Dict[float, int] = {}
        raw = (self.STARS_TRAFFIC_PACKAGES or "").strip()
        if not raw:
            return packages
        for part in raw.split(","):
            chunk = part.strip()
            if not chunk or ":" not in chunk:
                continue
            size_str, price_str = chunk.split(":", 1)
            try:
                size_gb = float(size_str.strip())
                price_val = int(float(price_str.strip()))
                if size_gb > 0 and price_val >= 0:
                    packages[size_gb] = price_val
            except ValueError:
                logging.warning("Invalid STARS_TRAFFIC_PACKAGES entry skipped: %s", chunk)
                continue
        return packages

    @computed_field
    def traffic_sale_mode(self) -> bool:
        """When true, the bot sells traffic packages instead of time-based subscriptions."""
        if self.tariffs_config is not None:
            return False
        return bool(self.traffic_packages or self.stars_traffic_packages)

    @computed_field
    def tariff_traffic_warning_levels(self) -> List[int]:
        levels: List[int] = []
        for part in (self.TARIFF_TRAFFIC_WARNING_LEVELS or "").split(","):
            chunk = part.strip()
            if not chunk:
                continue
            try:
                level = int(float(chunk))
            except ValueError:
                logging.warning("Invalid TARIFF_TRAFFIC_WARNING_LEVELS entry skipped: %s", chunk)
                continue
            if 0 < level < 100 and level not in levels:
                levels.append(level)
        return sorted(levels) or [85, 90, 95]

    @computed_field
    def tariffs_config(self) -> Optional[TariffsConfig]:
        return load_tariffs_config(self.TARIFFS_CONFIG_PATH)

    @computed_field
    def webapp_themes_catalog(self) -> WebappThemesConfig:
        return resolved_webapp_themes_catalog(
            primary_accent=self.WEBAPP_PRIMARY_COLOR or "#00fe7a",
            env_default_theme=self.WEBAPP_DEFAULT_THEME,
            theme_dir=self.WEBAPP_THEMES_DIR,
        )

    @field_validator("WEBAPP_PRIMARY_COLOR", mode="before")
    @classmethod
    def ignore_deprecated_webapp_primary_color_env(cls, _value):
        return "#00fe7a"

    @field_validator("WEBAPP_LOGO_URL", mode="before")
    @classmethod
    def ignore_deprecated_webapp_logo_url_env(cls, _value):
        return None

    @field_validator("WEBAPP_FAVICON_USE_CUSTOM", mode="before")
    @classmethod
    def ignore_deprecated_webapp_favicon_use_custom_env(cls, _value):
        return False

    @field_validator("WEBAPP_FAVICON_URL", mode="before")
    @classmethod
    def ignore_deprecated_webapp_favicon_url_env(cls, _value):
        return None

    @field_validator("WEBAPP_LOGO_FAVICON_URL", mode="before")
    @classmethod
    def ignore_deprecated_webapp_logo_favicon_url_env(cls, _value):
        return None

    @computed_field
    def referral_bonus_inviter(self) -> Dict[int, int]:
        bonuses: Dict[int, int] = {}
        if self.REFERRAL_BONUS_DAYS_INVITER_1_MONTH is not None:
            bonuses[1] = self.REFERRAL_BONUS_DAYS_INVITER_1_MONTH
        if self.REFERRAL_BONUS_DAYS_INVITER_3_MONTHS is not None:
            bonuses[3] = self.REFERRAL_BONUS_DAYS_INVITER_3_MONTHS
        if self.REFERRAL_BONUS_DAYS_INVITER_6_MONTHS is not None:
            bonuses[6] = self.REFERRAL_BONUS_DAYS_INVITER_6_MONTHS
        if self.REFERRAL_BONUS_DAYS_INVITER_12_MONTHS is not None:
            bonuses[12] = self.REFERRAL_BONUS_DAYS_INVITER_12_MONTHS
        return bonuses

    @computed_field
    def referral_bonus_referee(self) -> Dict[int, int]:
        bonuses: Dict[int, int] = {}
        if self.REFERRAL_BONUS_DAYS_REFEREE_1_MONTH is not None:
            bonuses[1] = self.REFERRAL_BONUS_DAYS_REFEREE_1_MONTH
        if self.REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS is not None:
            bonuses[3] = self.REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS
        if self.REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS is not None:
            bonuses[6] = self.REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS
        if self.REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS is not None:
            bonuses[12] = self.REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS
        return bonuses

    @property
    def yookassa_autopayments_active(self) -> bool:
        """Autopay features are available only when YooKassa itself is enabled.

        Proxies into the YooKassaConfig BaseSettings model that lives in the
        yookassa provider module вЂ” env-config is owned by the provider now.
        """
        from bot.payment_providers import get_provider_bundle

        bundle = get_provider_bundle("yookassa_service")
        if bundle is None or bundle.config is None:
            return False
        return bool(bundle.config.autopayments_active)

    @computed_field
    def payment_methods_order(self) -> List[str]:
        """
        Ordered list of payment providers to show in the subscription payment keyboard.

        Honors PAYMENT_METHODS_ORDER from the env (user-controlled order), but
        always appends any newly added provider that the user hasn't listed вЂ”
        otherwise upgrading to a release that adds, say, ``heleket`` would
        silently hide the new button until the operator manually updated their
        .env. Toggling the button on/off stays on the per-provider ENABLED
        flag, not on this list.
        """
        from bot.payment_providers import iter_provider_specs

        all_specs = list(iter_provider_specs())
        spec_ids: List[str] = []
        seen_ids: set = set()
        for spec in all_specs:
            if spec.id not in seen_ids:
                spec_ids.append(spec.id)
                seen_ids.add(spec.id)

        default_order = [
            "freekassa",
            "platega_sbp",
            "platega_crypto",
            "severpay",
            "wata",
            "wata_crypto",
            "yookassa",
            "stars",
            "cryptopay",
            "heleket",
            "paykilla",
            "lava",
            "pally",
            "cloudpayments",
            "stripe",
        ]
        # Make sure default_order itself includes every registered spec.
        for sid in spec_ids:
            if sid not in default_order:
                default_order.append(sid)

        if not self.PAYMENT_METHODS_ORDER:
            return default_order

        methods: List[str] = []
        for item in self.PAYMENT_METHODS_ORDER.split(","):
            slug = item.strip().lower()
            if not slug:
                continue
            if slug == "platega":
                # Legacy slug вЂ” expand to the new sub-methods preserving order
                if "platega_sbp" not in methods:
                    methods.append("platega_sbp")
                if "platega_crypto" not in methods:
                    methods.append("platega_crypto")
                continue
            methods.append(slug)
        # Append any registered spec that the operator didn't list вЂ” keeps
        # newly shipped providers visible after an upgrade without forcing a
        # .env edit. Toggling the button is still controlled by ENABLED.
        for sid in spec_ids:
            if sid not in methods:
                methods.append(sid)
        return methods or default_order

    def subscription_purchase_description(self, language: Optional[str] = None) -> str:
        if not self.SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED:
            return ""
        lang = (language or self.DEFAULT_LANGUAGE or "ru").split("-")[0].lower()
        primary = (
            self.SUBSCRIPTION_PURCHASE_DESCRIPTION_EN
            if lang == "en"
            else self.SUBSCRIPTION_PURCHASE_DESCRIPTION_RU
        )
        fallback = (
            self.SUBSCRIPTION_PURCHASE_DESCRIPTION_RU
            if lang == "en"
            else self.SUBSCRIPTION_PURCHASE_DESCRIPTION_EN
        )
        return (primary or fallback or "").strip()

    @computed_field
    def email_auth_configured(self) -> bool:
        return bool(
            self.SMTP_HOST
            and self.SMTP_PORT
            and self.SMTP_USERNAME
            and self.SMTP_PASSWORD
            and self.SMTP_FROM_EMAIL
        )

    @computed_field
    def smtp_ports_to_try(self) -> List[int]:
        ports: List[int] = []

        def add_port(value: Any) -> None:
            try:
                port = int(str(value).strip())
            except (TypeError, ValueError):
                return
            if 0 < port <= 65535 and port not in ports:
                ports.append(port)

        add_port(self.SMTP_PORT)
        for item in (self.SMTP_FALLBACK_PORTS or "").split(","):
            add_port(item)
        return ports


class SettingsValidationMixin:
    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_log_level(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
        if not v:
            return "INFO"
        return v

    @field_validator("POSTGRES_USER", "POSTGRES_PASSWORD", mode="before")
    @classmethod
    def validate_required_db_credentials(cls, v):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("WEBAPP_SESSION_SECRET", "WEBHOOK_SECRET_TOKEN", mode="before")
    @classmethod
    def normalize_webapp_secrets(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v:
                return v
        if v:
            return v
        return secrets.token_urlsafe(32)

    @field_validator(
        "LOG_CHAT_ID",
        "LOG_THREAD_ID",
        "LOG_SUPPORT_THREAD_ID",
        "BACKUP_CHAT_ID",
        "BACKUP_THREAD_ID",
        "REQUIRED_CHANNEL_ID",
        mode="before",
    )
    @classmethod
    def validate_optional_int_fields(cls, v):
        """Convert empty strings to None for optional integer fields"""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator(
        "REQUIRED_CHANNEL_LINK",
        "CRYPT4_REDIRECT_URL",
        "PRIVACY_POLICY_URL",
        "USER_AGREEMENT_URL",
        "SUBSCRIPTION_MINI_APP_URL",
        "WEBAPP_LOGO_URL",
        "TELEGRAM_OAUTH_CLIENT_SECRET",
        "TELEGRAM_OAUTH_REQUEST_ACCESS",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
        "SMTP_FROM_NAME",
        "SMTP_FALLBACK_PORTS",
        "BACKUP_COMPOSE_SOURCE_DIR",
        "BACKUP_COMPOSE_RESTORE_DIR",
        "PANEL_API_COOKIE",
        mode="before",
    )
    @classmethod
    def sanitize_optional_link(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("USER_HWID_DEVICE_LIMIT", mode="before")
    @classmethod
    def validate_optional_int(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator("APP_RUNTIME_MODE", mode="before")
    @classmethod
    def normalize_app_runtime_mode(cls, v):
        value = str(v or "production").strip().lower().replace("-", "_")
        if not value:
            return "production"
        aliases = {
            "prod": "production",
            "dev": "development",
            "local_dev": "development",
            "testing": "test",
        }
        return aliases.get(value, value)

    @field_validator("PANEL_WRITE_MODE", mode="before")
    @classmethod
    def validate_panel_write_mode(cls, v):
        value = str(v or "auto").strip().lower().replace("-", "_")
        if value not in {"auto", "live", "dry_run"}:
            raise ValueError("PANEL_WRITE_MODE must be one of: auto, live, dry_run")
        return value

    @field_validator("USER_TRAFFIC_STRATEGY", "TRIAL_TRAFFIC_STRATEGY", mode="before")
    @classmethod
    def normalize_panel_traffic_strategy(cls, v):
        return normalize_traffic_limit_strategy(v)
