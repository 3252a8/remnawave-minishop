import logging
import os
import secrets
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.tariffs_config import TariffsConfig, load_tariffs_config
from config.webapp_themes_config import (
    WebappThemesConfig,
    resolved_webapp_themes_catalog,
)

DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_RU = (
    "Покупая или продлевая подписку, вы получаете доступ к VPN/прокси-сервису, "
    "который помогает защищать ваше соединение и поддерживать стабильный доступ к сети."
)
DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN = (
    "By buying or renewing a subscription, you get access to a VPN/proxy service "
    "that helps protect your connection and keep your access stable."
)


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class DBSettings(BaseModel):
    user: str
    password: str
    host: str
    port: int
    database: str


class EmailSettings(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_fallback_ports: Optional[str]
    smtp_timeout_seconds: int
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_from_email: Optional[str]
    smtp_from_name: Optional[str]
    smtp_starttls: bool
    smtp_use_ssl: bool
    email_code_ttl_seconds: int
    email_code_resend_seconds: int
    email_code_max_attempts: int
    brute_force_max_failures: int
    brute_force_window_seconds: int
    brute_force_lock_seconds: int


class WebAppSettings(BaseModel):
    title: str
    primary_color: str
    logo_url: Optional[str]
    logo_use_emoji: bool
    logo_emoji: str
    logo_emoji_font: str
    favicon_use_custom: bool
    favicon_url: Optional[str]
    logo_favicon_url: Optional[str]
    session_ttl_seconds: int
    session_secret: str
    webhook_secret_token: str
    auth_max_age_seconds: int
    login_token_ttl_seconds: int
    server_host: str
    server_port: int
    enabled: bool
    trusted_proxies: List[str]


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS_STR: str = Field(
        default="", alias="ADMIN_IDS", description="Comma-separated list of admin Telegram User IDs"
    )

    POSTGRES_USER: str = Field(...)
    POSTGRES_PASSWORD: str = Field(...)
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="vpn_shop_db")
    DB_POOL_SIZE: int = Field(default=20)
    DB_MAX_OVERFLOW: int = Field(default=10)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800)

    REDIS_URL: Optional[str] = Field(default=None)
    REDIS_KEY_PREFIX: str = Field(default="remnawave-tg-shop")
    WEBAPP_ME_CACHE_TTL_SECONDS: int = Field(default=15)
    WEBAPP_DEVICES_CACHE_TTL_SECONDS: int = Field(default=5)
    PANEL_USER_CACHE_TTL_SECONDS: int = Field(default=5)
    PANEL_DEVICES_CACHE_TTL_SECONDS: int = Field(default=5)
    PANEL_ALL_USERS_CACHE_TTL_SECONDS: int = Field(default=5)
    PANEL_ALL_USERS_PAGE_SIZE: int = Field(default=1000)
    ADMIN_PANEL_STATS_CACHE_TTL_SECONDS: int = Field(default=15)
    ADMIN_DB_STATS_CACHE_TTL_SECONDS: int = Field(default=5)
    ADMIN_USERS_LIST_CACHE_TTL_SECONDS: int = Field(default=3)
    PROFILE_SYNC_CACHE_TTL_SECONDS: int = Field(default=900)
    PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS: int = Field(default=3600)
    PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES: int = Field(default=104857600)
    WEBAPP_RATE_LIMIT_TTL_SECONDS: int = Field(default=60)
    WEBAPP_RATE_LIMIT_MAX_REQUESTS: int = Field(default=30)
    WEBHOOK_QUEUE_NAME: str = Field(default="webhook-events")
    WEBHOOK_QUEUE_CONCURRENCY: int = Field(default=4)
    WORKER_PANEL_SYNC_INTERVAL_SECONDS: int = Field(default=900)
    TARIFF_WORKER_LOCK_TTL_SECONDS: int = Field(default=240)
    TARIFF_WORKER_TICK_SECONDS: int = Field(default=300)
    TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD: int = Field(default=50)

    DEFAULT_LANGUAGE: str = Field(default="ru")
    DEFAULT_CURRENCY_SYMBOL: str = Field(default="RUB")

    SUPPORT_LINK: Optional[str] = Field(default=None)
    SERVER_STATUS_URL: Optional[str] = Field(default=None)
    TERMS_OF_SERVICE_URL: Optional[str] = Field(default=None)
    PRIVACY_POLICY_URL: Optional[str] = Field(default=None)
    USER_AGREEMENT_URL: Optional[str] = Field(default=None)
    REQUIRED_CHANNEL_ID: Optional[int] = Field(
        default=None, description="Telegram channel ID the user must join to access the bot"
    )
    REQUIRED_CHANNEL_LINK: Optional[str] = Field(
        default=None,
        description="Public username or invite link to the required channel for join button",
    )

    LKNPD_INN: Optional[str] = Field(
        default=None,
        alias="NALOGO_INN",
        description="INN for lknpd.nalog.ru (self-employed) authentication",
    )
    LKNPD_PASSWORD: Optional[str] = Field(
        default=None,
        alias="NALOGO_PASSWORD",
        description="Password for lknpd.nalog.ru (self-employed) authentication",
    )
    LKNPD_API_URL: str = Field(
        default="https://lknpd.nalog.ru/api",
        alias="NALOGO_API_URL",
        description="Base URL for LKNPD API (can be overridden for proxies)",
    )
    LKNPD_RECEIPT_NAME_SUBSCRIPTION: str = Field(
        default="subscription {months} months",
        alias="NALOGO_RECEIPT_NAME_SUBSCRIPTION",
        description="Receipt item name for time-based subscriptions. Use {months} placeholder for duration.",  # noqa: E501
    )
    LKNPD_RECEIPT_NAME_TRAFFIC: str = Field(
        default="traffic package {gb} GB",
        alias="NALOGO_RECEIPT_NAME_TRAFFIC",
        description="Receipt item name for traffic packages. Use {gb} placeholder for traffic amount.",  # noqa: E501
    )

    WEBHOOK_BASE_URL: Optional[str] = None
    TRUSTED_PROXIES: Optional[str] = Field(
        default="127.0.0.1,::1",
        description="Comma-separated list of reverse proxy IPs or CIDRs trusted to forward X-Forwarded-For.",  # noqa: E501
    )

    STARS_ENABLED: bool = Field(default=True)
    PAYMENT_METHODS_ORDER: Optional[str] = Field(
        default=None,
        description="Comma-separated list of payment methods to show (e.g., severpay,wata,freekassa,yookassa,platega,stars,cryptopay)",  # noqa: E501
    )
    SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED: bool = Field(
        default=True,
        description="Show a localized description of the subscription before users choose a purchase/renewal period.",  # noqa: E501
    )
    SUBSCRIPTION_PURCHASE_DESCRIPTION_RU: str = Field(
        default=DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_RU,
        description="Russian subscription description shown before purchase/renewal options.",
    )
    SUBSCRIPTION_PURCHASE_DESCRIPTION_EN: str = Field(
        default=DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN,
        description="English subscription description shown before purchase/renewal options.",
    )

    MONTH_1_ENABLED: bool = Field(default=True, alias="1_MONTH_ENABLED")
    MONTH_3_ENABLED: bool = Field(default=True, alias="3_MONTHS_ENABLED")
    MONTH_6_ENABLED: bool = Field(default=True, alias="6_MONTHS_ENABLED")
    MONTH_12_ENABLED: bool = Field(default=True, alias="12_MONTHS_ENABLED")

    RUB_PRICE_1_MONTH: Optional[int] = Field(default=None)
    RUB_PRICE_3_MONTHS: Optional[int] = Field(default=None)
    RUB_PRICE_6_MONTHS: Optional[int] = Field(default=None)
    RUB_PRICE_12_MONTHS: Optional[int] = Field(default=None)

    STARS_PRICE_1_MONTH: Optional[int] = Field(default=None)
    STARS_PRICE_3_MONTHS: Optional[int] = Field(default=None)
    STARS_PRICE_6_MONTHS: Optional[int] = Field(default=None)
    STARS_PRICE_12_MONTHS: Optional[int] = Field(default=None)
    PANEL_WEBHOOK_SECRET: Optional[str] = Field(default=None)

    TRAFFIC_PACKAGES: Optional[str] = Field(
        default=None,
        description="Comma-separated list of traffic packages in the format '<GB>:<price>', e.g. '10:199,50:799'",  # noqa: E501
    )
    STARS_TRAFFIC_PACKAGES: Optional[str] = Field(
        default=None,
        description="Comma-separated list of traffic packages priced in Stars, e.g. '5:500,20:1500'",  # noqa: E501
    )
    TARIFFS_CONFIG_PATH: str = Field(default="data/tariffs.json")
    TARIFF_TRAFFIC_WARNING_LEVELS: str = Field(
        default="85,90,95",
        description="Comma-separated traffic usage warning levels for tariff traffic limits, e.g. '85,90,95'",  # noqa: E501
    )

    SUBSCRIPTION_NOTIFICATIONS_ENABLED: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_ON_EXPIRE: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_AFTER_EXPIRE: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_DAYS_BEFORE: int = Field(default=3)

    REFERRAL_BONUS_DAYS_INVITER_1_MONTH: Optional[int] = Field(
        default=3, alias="REFERRAL_BONUS_DAYS_1_MONTH"
    )
    REFERRAL_BONUS_DAYS_INVITER_3_MONTHS: Optional[int] = Field(
        default=7, alias="REFERRAL_BONUS_DAYS_3_MONTHS"
    )
    REFERRAL_BONUS_DAYS_INVITER_6_MONTHS: Optional[int] = Field(
        default=15, alias="REFERRAL_BONUS_DAYS_6_MONTHS"
    )
    REFERRAL_BONUS_DAYS_INVITER_12_MONTHS: Optional[int] = Field(
        default=30, alias="REFERRAL_BONUS_DAYS_12_MONTHS"
    )

    REFERRAL_BONUS_DAYS_REFEREE_1_MONTH: Optional[int] = Field(
        default=1, alias="REFEREE_BONUS_DAYS_1_MONTH"
    )
    REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS: Optional[int] = Field(
        default=3, alias="REFEREE_BONUS_DAYS_3_MONTHS"
    )
    REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS: Optional[int] = Field(
        default=7, alias="REFEREE_BONUS_DAYS_6_MONTHS"
    )
    REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS: Optional[int] = Field(
        default=15, alias="REFEREE_BONUS_DAYS_12_MONTHS"
    )

    # Referral program configuration
    REFERRAL_ONE_BONUS_PER_REFEREE: bool = Field(
        default=True,
        description="When true, referral bonuses (for inviter and referee) are applied only once per invited user - on their first successful payment.",  # noqa: E501
    )
    REFERRAL_WELCOME_BONUS_DAYS: int = Field(
        default=3,
        description="Welcome bonus days granted to a newly registered user who joined via referral link.",  # noqa: E501
    )
    LEGACY_REFS: bool = Field(
        default=True,
        description="Allow legacy referral links like ref_<telegram_id> to continue working. Defaults to True when unset.",  # noqa: E501
    )

    PANEL_API_URL: Optional[str] = None
    PANEL_API_KEY: Optional[str] = None
    USER_TRAFFIC_LIMIT_GB: Optional[float] = Field(default=0.0)
    USER_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")
    USER_SQUAD_UUIDS: Optional[str] = Field(
        default=None,
        description="Comma-separated UUIDs of internal squads to assign to new panel users",
    )
    USER_EXTERNAL_SQUAD_UUID: Optional[str] = Field(
        default=None,
        description="UUID of the external squad to assign to new panel users (optional)",
    )

    TRIAL_ENABLED: bool = Field(default=True)
    TRIAL_DURATION_DAYS: int = Field(default=3)
    TRIAL_TRAFFIC_LIMIT_GB: Optional[float] = Field(default=5.0)
    TRIAL_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")

    CRYPT4_ENABLED: bool = Field(
        default=False, description="Enable happ crypt4 encryption for subscription URLs"
    )
    CRYPT4_REDIRECT_URL: Optional[str] = Field(
        default=None,
        description="Base redirect URL used for the connect button when crypt4 is enabled",
    )
    CRYPT4_LINK_CACHE_TTL_SECONDS: int = Field(
        default=3600,
        description="TTL for cached happ crypt4 encryption results keyed by raw subscription URL",
    )

    WEB_SERVER_HOST: str = Field(default="0.0.0.0")
    WEB_SERVER_PORT: int = Field(default=8080)

    WEBAPP_ENABLED: bool = Field(
        default=True,
        description="Run the subscription Mini App in the same container on a separate port.",
    )
    WEBAPP_SERVER_HOST: str = Field(default="0.0.0.0")
    WEBAPP_SERVER_PORT: int = Field(default=8081)
    WEBAPP_TITLE: str = Field(default="Моя подписка")
    WEBAPP_PRIMARY_COLOR: str = Field(default="#00fe7a")
    WEBAPP_THEMES_DIR: str = Field(
        default="data/themes",
        description=(
            "Directory with per-theme folders. Each theme lives in "
            "<key>/theme.json with optional CSS/assets next to it."
        ),
    )
    WEBAPP_DEFAULT_THEME: Optional[str] = Field(
        default=None,
        description=(
            "Override the descriptor-marked default theme when set to an existing theme key."
        ),
    )
    WEBAPP_LOGO_URL: Optional[str] = Field(default=None)
    WEBAPP_LOGO_USE_EMOJI: bool = Field(default=False)
    WEBAPP_LOGO_EMOJI: str = Field(default="🫥")
    WEBAPP_LOGO_EMOJI_FONT: str = Field(
        default="system",
        description=(
            "Emoji font for logo fallback: system, noto-color, noto-color-animated, "
            "noto-emoji, twemoji, openmoji, apple, segoe, noto-local"
        ),
    )
    WEBAPP_FAVICON_USE_CUSTOM: bool = Field(default=False)
    WEBAPP_FAVICON_URL: Optional[str] = Field(default=None)
    WEBAPP_LOGO_FAVICON_URL: Optional[str] = Field(default=None)
    WEBAPP_SESSION_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    WEBHOOK_SECRET_TOKEN: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    WEBAPP_SESSION_TTL_SECONDS: int = Field(default=24 * 60 * 60)
    WEBAPP_AUTH_MAX_AGE_SECONDS: int = Field(default=24 * 60 * 60)
    WEBAPP_LOGIN_TOKEN_TTL_SECONDS: int = Field(default=10 * 60)
    TELEGRAM_OAUTH_CLIENT_ID: Optional[int] = Field(
        default=None,
        description="Telegram Web Login Client ID from BotFather. Defaults to the numeric bot ID from BOT_TOKEN.",  # noqa: E501
    )
    TELEGRAM_OAUTH_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Telegram Web Login Client Secret from BotFather. Reserved for full OIDC authorization code integrations.",  # noqa: E501
    )
    TELEGRAM_OAUTH_REQUEST_ACCESS: Optional[str] = Field(
        default="write",
        description="Comma-separated Telegram Login permissions to request: write,phone. Leave empty to request only OpenID profile.",  # noqa: E501
    )

    SMTP_HOST: str = Field(default="smtp-relay.brevo.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_FALLBACK_PORTS: Optional[str] = Field(default="2525,465")
    SMTP_TIMEOUT_SECONDS: int = Field(default=30)
    SMTP_USERNAME: Optional[str] = Field(default=None)
    SMTP_PASSWORD: Optional[str] = Field(default=None)
    SMTP_FROM_EMAIL: Optional[str] = Field(default=None)
    SMTP_FROM_NAME: Optional[str] = Field(default=None)
    SMTP_STARTTLS: bool = Field(default=True)
    SMTP_USE_SSL: bool = Field(default=False)
    EMAIL_CODE_TTL_SECONDS: int = Field(default=10 * 60)
    EMAIL_CODE_RESEND_SECONDS: int = Field(default=60)
    EMAIL_CODE_MAX_ATTEMPTS: int = Field(default=5)
    BRUTE_FORCE_MAX_FAILURES: int = Field(
        default=5,
        description="Maximum failed code attempts allowed within the throttle window before a temporary lockout is applied.",  # noqa: E501
    )
    BRUTE_FORCE_WINDOW_SECONDS: int = Field(
        default=15 * 60,
        description="Rolling window used to count failed email and promo code attempts.",
    )
    BRUTE_FORCE_LOCK_SECONDS: int = Field(
        default=30 * 60,
        description="Temporary lockout duration applied after too many failed code attempts.",
    )

    LOGS_PAGE_SIZE: int = Field(default=10)
    LOG_ADMIN_ACTIONS: bool = Field(
        default=True,
        description="Log updates/events triggered by users from ADMIN_IDS.",
    )

    SUPPORT_TICKETS_ENABLED: bool = Field(default=True)
    SUPPORT_TICKET_MAX_BODY_LENGTH: int = Field(default=4000)
    SUPPORT_TICKET_MAX_SUBJECT_LENGTH: int = Field(default=160)
    SUPPORT_TICKET_RATE_LIMIT_PER_HOUR: int = Field(default=5)
    SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED: bool = Field(default=False)
    SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS: int = Field(default=5 * 60)
    SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS: int = Field(default=30 * 60)
    SUBSCRIPTION_MINI_APP_URL: Optional[str] = Field(default=None)

    START_COMMAND_DESCRIPTION: Optional[str] = Field(default=None)
    DISABLE_WELCOME_MESSAGE: bool = Field(
        default=False, description="Disable welcome message on /start command"
    )

    MY_DEVICES_SECTION_ENABLED: bool = Field(
        default=False, description="Enable the My Devices section in the subscription menu"
    )
    USER_HWID_DEVICE_LIMIT: Optional[int] = Field(
        default=None, description="Default hardware device limit for panel users (0 = unlimited)"
    )

    # Inline mode thumbnail URLs
    INLINE_REFERRAL_THUMBNAIL_URL: str = Field(
        default="https://cdn-icons-png.flaticon.com/512/1077/1077114.png"
    )
    INLINE_USER_STATS_THUMBNAIL_URL: str = Field(
        default="https://cdn-icons-png.flaticon.com/512/681/681494.png"
    )
    INLINE_FINANCIAL_STATS_THUMBNAIL_URL: str = Field(
        default="https://cdn-icons-png.flaticon.com/512/2769/2769339.png"
    )
    INLINE_SYSTEM_STATS_THUMBNAIL_URL: str = Field(
        default="https://cdn-icons-png.flaticon.com/512/2920/2920277.png"
    )

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def db_settings(self) -> DBSettings:
        return DBSettings(
            user=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @computed_field
    @property
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
    @property
    def webapp_settings(self) -> WebAppSettings:
        return WebAppSettings(
            title=self.WEBAPP_TITLE,
            primary_color=self.WEBAPP_PRIMARY_COLOR,
            logo_url=self.WEBAPP_LOGO_URL,
            logo_use_emoji=self.WEBAPP_LOGO_USE_EMOJI,
            logo_emoji=self.WEBAPP_LOGO_EMOJI,
            logo_emoji_font=self.WEBAPP_LOGO_EMOJI_FONT,
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

    @computed_field
    @property
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
    @property
    def PRIMARY_ADMIN_ID(self) -> Optional[int]:
        ids = self.ADMIN_IDS
        return ids[0] if ids else None

    @computed_field
    @property
    def trial_traffic_limit_bytes(self) -> int:
        if self.TRIAL_TRAFFIC_LIMIT_GB is None or self.TRIAL_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.TRIAL_TRAFFIC_LIMIT_GB * (1024**3))

    @computed_field
    @property
    def user_traffic_limit_bytes(self) -> int:
        if self.USER_TRAFFIC_LIMIT_GB is None or self.USER_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.USER_TRAFFIC_LIMIT_GB * (1024**3))

    @computed_field
    @property
    def parsed_user_squad_uuids(self) -> Optional[List[str]]:
        if self.USER_SQUAD_UUIDS:
            return [uuid.strip() for uuid in self.USER_SQUAD_UUIDS.split(",") if uuid.strip()]
        return None

    @computed_field
    @property
    def parsed_user_external_squad_uuid(self) -> Optional[str]:
        if self.USER_EXTERNAL_SQUAD_UUID:
            cleaned = self.USER_EXTERNAL_SQUAD_UUID.strip()
            if cleaned:
                return cleaned
        return None

    @computed_field
    @property
    def trusted_proxies(self) -> List[str]:
        return _split_csv(self.TRUSTED_PROXIES)

    @computed_field
    @property
    def telegram_webhook_path(self) -> str:
        return "/tg/webhook"

    @computed_field
    @property
    def panel_webhook_path(self) -> str:
        return "/webhook/panel"

    @computed_field
    @property
    def panel_full_webhook_url(self) -> Optional[str]:
        base = self.WEBHOOK_BASE_URL
        if base:
            return f"{base.rstrip('/')}{self.panel_webhook_path}"
        return None

    @computed_field
    @property
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
    @property
    def stars_subscription_options(self) -> Dict[int, int]:
        options: Dict[int, int] = {}
        if self.STARS_ENABLED and self.MONTH_1_ENABLED and self.STARS_PRICE_1_MONTH is not None:
            options[1] = self.STARS_PRICE_1_MONTH
        if self.STARS_ENABLED and self.MONTH_3_ENABLED and self.STARS_PRICE_3_MONTHS is not None:
            options[3] = self.STARS_PRICE_3_MONTHS
        if self.STARS_ENABLED and self.MONTH_6_ENABLED and self.STARS_PRICE_6_MONTHS is not None:
            options[6] = self.STARS_PRICE_6_MONTHS
        if self.STARS_ENABLED and self.MONTH_12_ENABLED and self.STARS_PRICE_12_MONTHS is not None:
            options[12] = self.STARS_PRICE_12_MONTHS
        return options

    @computed_field
    @property
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
    @property
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
    @property
    def traffic_sale_mode(self) -> bool:
        """When true, the bot sells traffic packages instead of time-based subscriptions."""
        if self.tariffs_config is not None:
            return False
        return bool(self.traffic_packages or self.stars_traffic_packages)

    @computed_field
    @property
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
    @property
    def tariffs_config(self) -> Optional[TariffsConfig]:
        return load_tariffs_config(self.TARIFFS_CONFIG_PATH)

    @computed_field
    @property
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

    @field_validator("WEBAPP_LOGO_USE_EMOJI", mode="before")
    @classmethod
    def ignore_deprecated_webapp_logo_use_emoji_env(cls, _value):
        return False

    @field_validator("WEBAPP_LOGO_EMOJI", mode="before")
    @classmethod
    def ignore_deprecated_webapp_logo_emoji_env(cls, _value):
        return "🫥"

    @field_validator("WEBAPP_LOGO_EMOJI_FONT", mode="before")
    @classmethod
    def ignore_deprecated_webapp_logo_emoji_font_env(cls, _value):
        return "system"

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
    @property
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
    @property
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
        yookassa provider module — env-config is owned by the provider now.
        """
        from bot.payment_providers import get_provider_bundle

        bundle = get_provider_bundle("yookassa_service")
        if bundle is None or bundle.config is None:
            return False
        return bool(bundle.config.autopayments_active)

    @computed_field
    @property
    def payment_methods_order(self) -> List[str]:
        """
        Ordered list of payment providers to show in the subscription payment keyboard.

        Honors PAYMENT_METHODS_ORDER from the env (user-controlled order), but
        always appends any newly added provider that the user hasn't listed —
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
            "yookassa",
            "stars",
            "cryptopay",
            "heleket",
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
                # Legacy slug — expand to the new sub-methods preserving order
                if "platega_sbp" not in methods:
                    methods.append("platega_sbp")
                if "platega_crypto" not in methods:
                    methods.append("platega_crypto")
                continue
            methods.append(slug)
        # Append any registered spec that the operator didn't list — keeps
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
    @property
    def email_auth_configured(self) -> bool:
        return bool(
            self.SMTP_HOST
            and self.SMTP_PORT
            and self.SMTP_USERNAME
            and self.SMTP_PASSWORD
            and self.SMTP_FROM_EMAIL
        )

    @computed_field
    @property
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

    # Logging Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Global log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    LOG_CHAT_ID: Optional[int] = Field(
        default=None, description="Telegram chat/group ID for sending notifications"
    )
    LOG_THREAD_ID: Optional[int] = Field(
        default=None, description="Thread ID for supergroup messages (optional)"
    )
    LOG_SUPPORT_THREAD_ID: Optional[int] = Field(
        default=None, description="Thread ID for support ticket log messages"
    )

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

    @field_validator("LOG_CHAT_ID", "LOG_THREAD_ID", "LOG_SUPPORT_THREAD_ID", mode="before")
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

    # Notification types
    LOG_NEW_USERS: bool = Field(
        default=True, description="Send notifications for new user registrations"
    )
    LOG_PAYMENTS: bool = Field(
        default=True, description="Send notifications for successful payments"
    )
    LOG_PROMO_ACTIVATIONS: bool = Field(
        default=True, description="Send notifications for promo code activations"
    )
    LOG_TRIAL_ACTIVATIONS: bool = Field(
        default=True, description="Send notifications for trial activations"
    )
    LOG_SUSPICIOUS_ACTIVITY: bool = Field(
        default=True, description="Send notifications for suspicious promo attempts"
    )
    LOG_SUPPORT: bool = Field(default=True, description="Send support ticket notifications")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        try:
            _settings_instance = Settings()
            if not _settings_instance.ADMIN_IDS:
                logging.warning(
                    "CRITICAL: ADMIN_IDS not set or contains no valid integer IDs in .env. "
                    "Admin functionality will be restricted."
                )

            if not _settings_instance.PANEL_API_URL:
                logging.warning(
                    "CRITICAL: PANEL_API_URL is not set. Panel integration will not work."
                )
            if not os.getenv("WEBAPP_SESSION_SECRET"):
                logging.warning(
                    "WEBAPP_SESSION_SECRET is not set. A generated secret will be used for this process only."  # noqa: E501
                )
            if not os.getenv("WEBHOOK_SECRET_TOKEN"):
                logging.warning(
                    "WEBHOOK_SECRET_TOKEN is not set. A generated secret will be used for this process only."  # noqa: E501
                )
            if (_settings_instance.LKNPD_INN or _settings_instance.LKNPD_PASSWORD) and not (
                _settings_instance.LKNPD_INN and _settings_instance.LKNPD_PASSWORD
            ):
                logging.warning(
                    "WARNING: LKNPD credentials are incomplete. Receipt sending will be disabled."
                )

        except ValidationError as e:
            logging.critical(f"Pydantic validation error while loading settings: {e}")

            raise SystemExit(
                f"CRITICAL SETTINGS ERROR: {e}. Please check your .env file and Settings model."
            )
    return _settings_instance
