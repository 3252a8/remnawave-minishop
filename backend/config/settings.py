import logging
import os
import secrets

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings_mixins import SettingsComputedMixin, SettingsValidationMixin
from config.settings_models import (
    CompatibilitySettings,
    DBSettings,
    EmailSettings,
    PanelSettings,
    PaymentSettings,
    ReferralSettings,
    RegistrationSettings,
    SupportSettings,
    WebAppSettings,
)

logger = logging.getLogger(__name__)

DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_RU = (
    "By buying or renewing a subscription, you get access to a VPN/proxy service "
    "that helps protect your connection and keep your access stable."
)
DEFAULT_SUBSCRIPTION_PURCHASE_DESCRIPTION_EN = (
    "By buying or renewing a subscription, you get access to a VPN/proxy service "
    "that helps protect your connection and keep your access stable."
)


DEFAULT_DISPOSABLE_EMAIL_DOMAINS = "\n".join(
    [
        "10minutemail.com",
        "10minutemail.net",
        "10minutemail.org",
        "20minutemail.com",
        "33mail.com",
        "anonbox.net",
        "anonymbox.com",
        "armyspy.com",
        "byom.de",
        "crazymailing.com",
        "cuvox.de",
        "dayrep.com",
        "deadaddress.com",
        "dispostable.com",
        "dodgeit.com",
        "dodgit.com",
        "dropmail.me",
        "easytrashmail.com",
        "emailfake.com",
        "emailondeck.com",
        "emailtemporanea.com",
        "emailtemporanea.net",
        "einrot.com",
        "fakeinbox.com",
        "filzmail.com",
        "fleckens.hu",
        "generator.email",
        "getairmail.com",
        "getnada.com",
        "grr.la",
        "guerrillamail.biz",
        "guerrillamail.com",
        "guerrillamail.de",
        "guerrillamail.info",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamailblock.com",
        "gustr.com",
        "hmamail.com",
        "incognitomail.org",
        "inboxbear.com",
        "jetable.org",
        "jourrapide.com",
        "kasmail.com",
        "mail-temp.com",
        "mailcatch.com",
        "maildrop.cc",
        "mailexpire.com",
        "mailinator.com",
        "mailinator.net",
        "mailinator.org",
        "mailmetrash.com",
        "mailnesia.com",
        "mailnull.com",
        "mailpoof.com",
        "mailtothis.com",
        "mail.tm",
        "mintemail.com",
        "mohmal.com",
        "moakt.com",
        "mytemp.email",
        "mytrashmail.com",
        "nada.email",
        "no-spam.ws",
        "pookmail.com",
        "rhyta.com",
        "sharklasers.com",
        "sofort-mail.de",
        "spam4.me",
        "spambog.com",
        "spamdecoy.net",
        "spamfree24.org",
        "spamgourmet.com",
        "spamhole.com",
        "spam.la",
        "spammotel.com",
        "superrito.com",
        "teleworm.us",
        "tempail.com",
        "temp-mail.io",
        "temp-mail.org",
        "tempmail.com",
        "tempmail.dev",
        "tempmail.net",
        "tempmailo.com",
        "temporaryemail.net",
        "temporary-mail.net",
        "tempr.email",
        "throwawaymail.com",
        "trash-mail.com",
        "trash-mail.de",
        "trashmail.com",
        "trashmail.me",
        "trashmail.net",
        "trashmailer.com",
        "trashymail.com",
        "weg-werf-email.de",
        "wegwerfmail.de",
        "wegwerfmail.net",
        "wegwerfmail.org",
        "yomail.info",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
    ]
)

DEFAULT_TRUSTED_PROXIES = ",".join(
    [
        "127.0.0.1",
        "::1",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    ]
)


class Settings(SettingsComputedMixin, SettingsValidationMixin, BaseSettings):
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

    REDIS_URL: str | None = Field(default=None)
    REDIS_KEY_PREFIX: str = Field(default="remnawave-tg-shop")
    WEBAPP_ME_CACHE_TTL_SECONDS: int = Field(default=15)
    WEBAPP_DEVICES_CACHE_TTL_SECONDS: int = Field(default=5)
    PANEL_USER_CACHE_TTL_SECONDS: int = Field(default=5)
    PANEL_DEVICES_CACHE_TTL_SECONDS: int = Field(default=5)
    SUBSCRIPTION_GUIDES_CONFIG_CACHE_TTL_SECONDS: int = Field(default=300)
    SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS: int = Field(default=300)
    SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS: int = Field(default=300)
    PANEL_ALL_USERS_CACHE_TTL_SECONDS: int = Field(default=5)
    PANEL_ALL_USERS_PAGE_SIZE: int = Field(default=1000)
    # Courtesy delay between consecutive /users pages when fetching the full
    # panel user list. The panel caps page size at 1000, so large deployments
    # page many times (100k users -> 100 pages); at the default 0.1s that is
    # ~10s of pure waiting per full sync. Operators with a panel that tolerates
    # faster polling can lower this (0 disables the delay entirely).
    PANEL_ALL_USERS_PAGE_DELAY_SECONDS: float = Field(default=0.1)
    PANEL_API_TOTAL_TIMEOUT_SECONDS: float = Field(default=25)
    PANEL_API_CONNECT_TIMEOUT_SECONDS: float = Field(default=8)
    PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS: float = Field(default=8)
    PANEL_API_SOCK_READ_TIMEOUT_SECONDS: float = Field(default=15)
    ADMIN_PANEL_STATS_CACHE_TTL_SECONDS: int = Field(default=15)
    ADMIN_DB_STATS_CACHE_TTL_SECONDS: int = Field(default=5)
    ADMIN_USERS_LIST_CACHE_TTL_SECONDS: int = Field(default=3)
    ADMIN_BROADCAST_AUDIENCE_COUNTS_CACHE_TTL_SECONDS: int = Field(default=30)
    PROFILE_SYNC_CACHE_TTL_SECONDS: int = Field(default=900)
    PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS: int = Field(default=3600)
    PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES: int = Field(default=104857600)
    WEBAPP_RATE_LIMIT_TTL_SECONDS: int = Field(default=60)
    WEBAPP_RATE_LIMIT_MAX_REQUESTS: int = Field(default=30)
    TELEGRAM_DROP_NON_PRIVATE_UPDATES: bool = Field(default=True)
    TELEGRAM_ANTIFLOOD_ENABLED: bool = Field(default=True)
    TELEGRAM_ANTIFLOOD_WINDOW_SECONDS: int = Field(default=60)
    TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW: int = Field(default=180)
    TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW: int = Field(default=120)
    TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW: int = Field(default=240)
    TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW: int = Field(default=60)
    TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW: int = Field(default=30)
    TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW: int = Field(default=60)
    TELEGRAM_ACTION_COOLDOWN_ENABLED: bool = Field(default=True)
    TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS: int = Field(default=20)
    TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS: int = Field(default=30)
    WEBHOOK_QUEUE_NAME: str = Field(default="webhook-events")
    WEBHOOK_QUEUE_CONCURRENCY: int = Field(default=4)
    WORKER_PANEL_SYNC_INTERVAL_SECONDS: int = Field(default=900)
    TARIFF_WORKER_LOCK_TTL_SECONDS: int = Field(default=240)
    TARIFF_WORKER_TICK_SECONDS: int = Field(default=300)
    TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD: int = Field(default=50)
    BACKUP_ENABLED: bool = Field(
        default=False,
        description="Run periodic backup jobs from the worker container.",
    )
    BACKUP_INTERVAL_SECONDS: int = Field(default=60 * 60)
    BACKUP_LOCK_TTL_SECONDS: int = Field(default=2 * 60 * 60)
    BACKUP_DIR: str = Field(default="data/backups")
    BACKUP_LOCAL_RETENTION: int = Field(default=100)
    BACKUP_CHAT_ID: int | None = Field(
        default=None,
        description="Telegram chat ID for backup archives. Falls back to LOG_CHAT_ID.",
    )
    BACKUP_THREAD_ID: int | None = Field(
        default=None,
        description="Telegram topic/thread ID for backup archives. Falls back to LOG_THREAD_ID.",
    )
    BACKUP_POSTGRES_DUMP_ENABLED: bool = Field(default=True)
    BACKUP_PG_DUMP_PATH: str = Field(default="pg_dump")
    BACKUP_PG_DUMP_TIMEOUT_SECONDS: int = Field(default=30 * 60)
    BACKUP_PG_RESTORE_PATH: str = Field(default="pg_restore")
    BACKUP_PG_RESTORE_TIMEOUT_SECONDS: int = Field(default=30 * 60)
    BACKUP_COMPOSE_ENABLED: bool = Field(default=True)
    BACKUP_COMPOSE_SOURCE_DIR: str | None = Field(default="/app/compose-source")
    BACKUP_COMPOSE_RESTORE_DIR: str | None = Field(default=None)
    BACKUP_COMPOSE_EXCLUDE_DIRS: str = Field(
        default=".git,node_modules,__pycache__,.pytest_cache,.ruff_cache,postgres-data,redis-data,shop-data,backups"
    )

    DEFAULT_LANGUAGE: str = Field(default="ru")
    DEFAULT_CURRENCY_SYMBOL: str = Field(default="RUB")

    SUPPORT_LINK: str | None = Field(default=None)
    SERVER_STATUS_URL: str | None = Field(default=None)
    PRIVACY_POLICY_URL: str | None = Field(default=None)
    USER_AGREEMENT_URL: str | None = Field(default=None)
    REQUIRED_CHANNEL_ID: int | None = Field(
        default=None, description="Telegram channel ID the user must join to access the bot"
    )
    REQUIRED_CHANNEL_LINK: str | None = Field(
        default=None,
        description="Public username or invite link to the required channel for join button",
    )

    LKNPD_INN: str | None = Field(
        default=None,
        alias="NALOGO_INN",
        description="INN for lknpd.nalog.ru (self-employed) authentication",
    )
    LKNPD_PASSWORD: str | None = Field(
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

    WEBHOOK_BASE_URL: str | None = None
    TRUSTED_PROXIES: str | None = Field(
        default=DEFAULT_TRUSTED_PROXIES,
        description="Comma-separated list of reverse proxy IPs or CIDRs trusted to forward X-Forwarded-For.",  # noqa: E501
    )

    STARS_ENABLED: bool = Field(default=True)
    STARS_ADMIN_ONLY_ENABLED: bool = Field(default=False)
    PAYMENT_METHODS_ORDER: str | None = Field(
        default=None,
        description="Comma-separated list of payment methods to show (e.g., severpay,wata,freekassa,yookassa,platega,stars,cryptopay,heleket,paykilla,lava,pally,cloudpayments,stripe)",  # noqa: E501
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
    PAYMENT_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=20,
        ge=1,
        description="Maximum total time for one payment provider API request, in seconds.",
    )

    MONTH_1_ENABLED: bool = Field(default=True, alias="1_MONTH_ENABLED")
    MONTH_3_ENABLED: bool = Field(default=True, alias="3_MONTHS_ENABLED")
    MONTH_6_ENABLED: bool = Field(default=True, alias="6_MONTHS_ENABLED")
    MONTH_12_ENABLED: bool = Field(default=True, alias="12_MONTHS_ENABLED")

    RUB_PRICE_1_MONTH: int | None = Field(default=200)
    RUB_PRICE_3_MONTHS: int | None = Field(default=600)
    RUB_PRICE_6_MONTHS: int | None = Field(default=1200)
    RUB_PRICE_12_MONTHS: int | None = Field(default=2400)
    PROMO_DURATION_MULTIPLIER_MAX: float = Field(default=12.0)
    PROMO_TRAFFIC_MULTIPLIER_MAX: float = Field(default=12.0)

    STARS_PRICE_1_MONTH: int | None = Field(default=None)
    STARS_PRICE_3_MONTHS: int | None = Field(default=None)
    STARS_PRICE_6_MONTHS: int | None = Field(default=None)
    STARS_PRICE_12_MONTHS: int | None = Field(default=None)
    PANEL_WEBHOOK_SECRET: str | None = Field(default=None)

    TRAFFIC_PACKAGES: str | None = Field(
        default=None,
        description="Comma-separated list of traffic packages in the format '<GB>:<price>', e.g. '10:199,50:799'",  # noqa: E501
    )
    STARS_TRAFFIC_PACKAGES: str | None = Field(
        default=None,
        description="Comma-separated list of traffic packages priced in Stars, e.g. '5:500,20:1500'",  # noqa: E501
    )
    TARIFFS_CONFIG_PATH: str = Field(default="data/tariffs.json")
    TARIFF_TRAFFIC_WARNING_LEVELS: str = Field(
        default="85,90,95",
        description="Comma-separated traffic usage warning levels for tariff traffic limits, e.g. '85,90,95'",  # noqa: E501
    )

    SUBSCRIPTION_NOTIFICATIONS_ENABLED: bool = Field(default=True)
    SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_ON_EXPIRE: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_AFTER_EXPIRE: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_DAYS_BEFORE: int = Field(default=3)
    SUBSCRIPTION_NOTIFY_HOURS_BEFORE: int = Field(default=3)
    SUBSCRIPTION_NOTIFICATION_WORKER_TICK_SECONDS: int = Field(default=300)

    REFERRAL_BONUS_DAYS_INVITER_1_MONTH: int | None = Field(
        default=3, alias="REFERRAL_BONUS_DAYS_1_MONTH"
    )
    REFERRAL_BONUS_DAYS_INVITER_3_MONTHS: int | None = Field(
        default=7, alias="REFERRAL_BONUS_DAYS_3_MONTHS"
    )
    REFERRAL_BONUS_DAYS_INVITER_6_MONTHS: int | None = Field(
        default=15, alias="REFERRAL_BONUS_DAYS_6_MONTHS"
    )
    REFERRAL_BONUS_DAYS_INVITER_12_MONTHS: int | None = Field(
        default=30, alias="REFERRAL_BONUS_DAYS_12_MONTHS"
    )

    REFERRAL_BONUS_DAYS_REFEREE_1_MONTH: int | None = Field(
        default=1, alias="REFEREE_BONUS_DAYS_1_MONTH"
    )
    REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS: int | None = Field(
        default=3, alias="REFEREE_BONUS_DAYS_3_MONTHS"
    )
    REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS: int | None = Field(
        default=7, alias="REFEREE_BONUS_DAYS_6_MONTHS"
    )
    REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS: int | None = Field(
        default=15, alias="REFEREE_BONUS_DAYS_12_MONTHS"
    )

    # Referral program configuration
    REFERRAL_ONE_BONUS_PER_REFEREE: bool = Field(
        default=True,
        description="When true, referral payment bonuses are applied only on the invited user's first successful payment.",  # noqa: E501
    )
    REFERRAL_WELCOME_BONUS_DAYS: int = Field(
        default=3,
        description="Welcome bonus days granted to a newly registered user who joined via referral link.",  # noqa: E501
    )
    REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED: bool = Field(
        default=True,
        description=(
            "Allow referral welcome bonus grants for users who have not linked Telegram. "
            "Disposable email domains are still blocked until Telegram is linked."
        ),
    )
    LEGACY_REFS: bool = Field(
        default=True,
        description="Allow legacy referral links like /start ref_<telegram_id>, where the payload contains the inviter's Telegram/user ID.",  # noqa: E501
    )
    MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED: bool = Field(
        default=False,
        description=(
            "Accept referral links imported from snoups/remnashop via legacy_referral_codes."
        ),
    )
    MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED: bool = Field(
        default=False,
        description="Try exact legacy Remnashop promo codes before uppercase normalization.",
    )
    MIGRATION_REMNASHOP_IMPORTED_AT: str | None = Field(
        default=None,
        description="Timestamp of the latest Remnashop import run, managed by the import script.",
    )
    MIGRATION_REMNASHOP_NOTES: str | None = Field(
        default=None,
        description="Operator notes for instances migrated from Remnashop.",
    )

    APP_RUNTIME_MODE: str = Field(
        default="production",
        description="Runtime profile: production, development, staging or test.",
    )
    QA_AUTH_ENABLED: bool = Field(
        default=False,
        description=(
            "Expose email verification codes through the public auth API in "
            "development/test runtimes for full-stack QA."
        ),
    )
    QA_PAYMENT_ENABLED: bool = Field(
        default=False,
        description="Enable the signed local QA payment provider in development/test runtimes.",
    )
    QA_PAYMENT_ADMIN_ONLY_ENABLED: bool = Field(
        default=False,
        description="Expose the local QA payment provider to admin users only.",
    )
    QA_PAYMENT_SECRET: str = Field(
        default="",
        description="HMAC secret used by the local QA payment webhook.",
    )
    PANEL_WRITE_MODE: str = Field(
        default="auto",
        description=(
            "Panel write behavior: auto uses dry-run in development/test runtimes, "
            "live always writes to Remnawave, dry_run validates and logs mutations only."
        ),
    )
    PANEL_DRY_RUN_VALIDATE_REMOTE: bool = Field(
        default=True,
        description=(
            "When panel dry-run is enabled, validate referenced users and squads "
            "via live GET requests."
        ),
    )
    PANEL_DRY_RUN_SYNTHETIC_CREATE: bool = Field(
        default=True,
        description=(
            "When panel dry-run is enabled, return synthetic users for create-user attempts."
        ),
    )
    PANEL_API_URL: str | None = None
    PANEL_API_KEY: str | None = None
    PANEL_API_COOKIE: str | None = None
    USER_TRAFFIC_LIMIT_GB: float | None = Field(default=0.0)
    USER_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")
    USER_SQUAD_UUIDS: str | None = Field(
        default=None,
        description="Comma-separated UUIDs of internal squads to assign to new panel users",
    )
    USER_EXTERNAL_SQUAD_UUID: str | None = Field(
        default=None,
        description="UUID of the external squad to assign to new panel users (optional)",
    )

    TRIAL_ENABLED: bool = Field(default=True)
    TRIAL_DURATION_DAYS: int = Field(default=3)
    TRIAL_TRAFFIC_LIMIT_GB: float | None = Field(default=5.0)
    TRIAL_PREMIUM_TRAFFIC_LIMIT_GB: float | None = Field(
        default=0.0,
        description=(
            "Separate premium traffic limit for trial subscriptions. "
            "0 disables premium traffic enforcement for trials."
        ),
    )
    TRIAL_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")
    TRIAL_WITHOUT_TELEGRAM_ENABLED: bool = Field(
        default=True,
        description=(
            "Allow trial activation for users who have not linked Telegram. "
            "Disposable email domains are still blocked until Telegram is linked."
        ),
    )
    TRIAL_SQUAD_UUIDS: str | None = Field(
        default=None,
        description=(
            "Comma-separated UUIDs of internal squads to assign during trial activation. "
            "Falls back to USER_SQUAD_UUIDS when empty."
        ),
    )
    TRIAL_PREMIUM_SQUAD_UUIDS: str | None = Field(
        default=None,
        description=(
            "Comma-separated premium internal squad UUIDs to assign during trial activation. "
            "Empty value disables premium squads for trials."
        ),
    )

    CRYPT4_ENABLED: bool = Field(
        default=False, description="Enable happ crypt4 encryption for subscription URLs"
    )
    CRYPT4_REDIRECT_URL: str | None = Field(
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
    WEBAPP_TITLE: str = Field(default="/minishop")
    WEBAPP_PRIMARY_COLOR: str = Field(default="#00fe7a")
    WEBAPP_THEMES_DIR: str = Field(
        default="data/themes",
        description=(
            "Directory with per-theme folders. Each theme lives in "
            "<key>/theme.json with optional CSS/assets next to it."
        ),
    )
    WEBAPP_DEFAULT_THEME: str | None = Field(
        default=None,
        description=(
            "Override the descriptor-marked default theme when set to an existing theme key."
        ),
    )
    WEBAPP_LOGO_URL: str | None = Field(default=None)
    WEBAPP_FAVICON_USE_CUSTOM: bool = Field(default=False)
    WEBAPP_FAVICON_URL: str | None = Field(default=None)
    WEBAPP_LOGO_FAVICON_URL: str | None = Field(default=None)
    SUBSCRIPTION_GUIDES_ENABLED: bool = Field(
        default=True,
        description="Show embedded install instructions inside the subscription Mini App.",
    )
    SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED: bool = Field(
        default=True,
        description=(
            "Open Mini App install guides from Telegram bot connect buttons and show public "
            "install guide share links."
        ),
    )
    SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED: bool = Field(
        default=True,
        description=(
            "Use Remnawave Panel Subscription Page config for embedded guides when available."
        ),
    )
    SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED: bool = Field(
        default=False,
        description="Enable admin JSON override for embedded guides config.",
    )
    SUBSCRIPTION_PAGE_CONFIG_PATH: str = Field(
        default="data/subpage-config/multiapp.json",
        description="Path to Remnawave Subscription Page v1 JSON config for embedded guides.",
    )
    SUBSCRIPTION_PAGE_CONFIG_JSON: str = Field(
        default="",
        description="Admin-provided Remnawave Subscription Page v1 JSON config override.",
    )
    WEBAPP_SESSION_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    WEBHOOK_SECRET_TOKEN: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    WEBAPP_SESSION_TTL_SECONDS: int = Field(default=24 * 60 * 60)
    WEBAPP_AUTH_MAX_AGE_SECONDS: int = Field(default=24 * 60 * 60)
    WEBAPP_LOGIN_TOKEN_TTL_SECONDS: int = Field(default=10 * 60)
    TELEGRAM_OAUTH_CLIENT_ID: int | None = Field(
        default=None,
        description="Telegram Web Login Client ID from BotFather. Defaults to the numeric bot ID from BOT_TOKEN.",  # noqa: E501
    )
    TELEGRAM_OAUTH_CLIENT_SECRET: str | None = Field(
        default=None,
        description="Telegram Web Login Client Secret from BotFather. Reserved for full OIDC authorization code integrations.",  # noqa: E501
    )
    TELEGRAM_OAUTH_REQUEST_ACCESS: str | None = Field(
        default="write",
        description="Comma-separated Telegram Login permissions to request: write,phone. Leave empty to request only OpenID profile.",  # noqa: E501
    )

    SMTP_HOST: str = Field(default="smtp-relay.brevo.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_FALLBACK_PORTS: str | None = Field(default="2525,465")
    SMTP_TIMEOUT_SECONDS: int = Field(default=30)
    SMTP_USERNAME: str | None = Field(default=None)
    SMTP_PASSWORD: str | None = Field(default=None)
    SMTP_FROM_EMAIL: str | None = Field(default=None)
    SMTP_FROM_NAME: str | None = Field(default=None)
    DISPOSABLE_EMAIL_DOMAINS: str = Field(
        default=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
        description=(
            "Disposable email domains treated as requiring Telegram for trial and "
            "referral welcome bonus abuse protection. Accepts commas or one domain per line."
        ),
    )
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
    SUBSCRIPTION_MINI_APP_URL: str | None = Field(default=None)
    WEBAPP_API_BASE_URL: str = Field(
        default="/api",
        description=(
            "Base URL used by the Mini App frontend for backend API requests. "
            "Keep /api; split deployments configure the frontend nginx upstream instead."
        ),
    )
    MINISHOP_EDGE_TOKEN: str = Field(
        default="",
        description=(
            "Optional server-side token required on protected Web App API upstream routes. "
            "It must be injected by a trusted reverse proxy, never by browser JavaScript."
        ),
    )
    MINISHOP_EDGE_TOKEN_HEADER: str = Field(
        default="X-Minishop-Edge-Token",
        description=(
            "HTTP header name used by frontend nginx or an API edge to pass MINISHOP_EDGE_TOKEN."
        ),
    )
    TELEGRAM_BOT_MENU_DISABLED: bool = Field(
        default=False,
        description=(
            "Hide the in-bot user interface and /tg command. "
            "User renewal prompts should open the Mini App."
        ),
    )

    START_COMMAND_DESCRIPTION: str | None = Field(default=None)
    DISABLE_WELCOME_MESSAGE: bool = Field(
        default=False, description="Disable welcome message on /start command"
    )
    REGISTRATION_INVITE_ONLY_ENABLED: bool = Field(
        default=False,
        description=(
            "When true, new public registrations require a valid referral invitation. "
            "Existing users can still sign in normally."
        ),
    )

    MY_DEVICES_SECTION_ENABLED: bool = Field(
        default=False, description="Enable the My Devices section in the subscription menu"
    )
    USER_HWID_DEVICE_LIMIT: int | None = Field(
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

    # Logging Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Global log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    LOG_CHAT_ID: int | None = Field(
        default=None, description="Telegram chat/group ID for sending notifications"
    )
    LOG_THREAD_ID: int | None = Field(
        default=None, description="Thread ID for supergroup messages (optional)"
    )
    LOG_SUPPORT_THREAD_ID: int | None = Field(
        default=None, description="Thread ID for support ticket log messages"
    )

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

    # Anonymous install telemetry (self-hosted friendly, opt-out).
    TELEMETRY_ENABLED: bool = Field(
        default=True,
        description=(
            "Send an anonymous daily install heartbeat (version, official/custom "
            "image provenance, OS, locale, user-count range). No personal data. "
            "Opt out here, via the web admin, or by clearing "
            "TELEMETRY_ENDPOINT/TELEMETRY_API_KEY."
        ),
    )
    TELEMETRY_ENDPOINT: str = Field(
        default="https://eu.i.posthog.com",
        description="PostHog ingestion host. Empty disables telemetry.",
    )
    TELEMETRY_API_KEY: str = Field(
        default="phc_sRiAbbrjhyYPfsgBwSZyLvujDXBLaDpmWKt6paGmCCMm",
        description=(
            "PostHog project API key (phc_...). Safe to ship in the image: it is "
            "a write-only ingest key. Empty disables telemetry."
        ),
    )
    TELEMETRY_INTERVAL_HOURS: int = Field(default=24)

    @property
    def telemetry_configured(self) -> bool:
        """True when telemetry is enabled and has a delivery target."""
        return bool(
            self.TELEMETRY_ENABLED
            and str(self.TELEMETRY_ENDPOINT or "").strip()
            and str(self.TELEMETRY_API_KEY or "").strip()
        )

    PLUGINS_ENABLED: bool = Field(
        default=True,
        description="Discover and load extension plugins from the minishop.plugins entry points.",
    )
    PLUGINS_STRICT: bool = Field(
        default=False,
        description=(
            "Treat plugin load/setup errors as fatal instead of logging and skipping the plugin."
        ),
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )


_settings_instance: Settings | None = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        try:
            # Third-party boundary: pydantic-settings fills required fields
            # (BOT_TOKEN, POSTGRES_*) from the environment inside __init__, but
            # dataclass_transform makes mypy demand them as named arguments.
            # model_validate({}) would satisfy mypy yet skip the env sources.
            _settings_instance = Settings()  # type: ignore[call-arg]
            if not _settings_instance.ADMIN_IDS:
                logger.warning(
                    "CRITICAL: ADMIN_IDS not set or contains no valid integer IDs in .env. "
                    "Admin functionality will be restricted."
                )

            if not _settings_instance.PANEL_API_URL:
                logger.warning(
                    "CRITICAL: PANEL_API_URL is not set. Panel integration will not work."
                )
            if _settings_instance.panel_dry_run_enabled:
                logger.warning(
                    "PANEL_WRITE_MODE dry-run is enabled: Remnawave write requests will be "
                    "validated and logged without changing panel users."
                )
            if not os.getenv("WEBAPP_SESSION_SECRET"):
                logger.warning(
                    "WEBAPP_SESSION_SECRET is not set. A generated secret will be used for this process only."  # noqa: E501
                )
            if not os.getenv("WEBHOOK_SECRET_TOKEN"):
                logger.warning(
                    "WEBHOOK_SECRET_TOKEN is not set. A generated secret will be used for this process only."  # noqa: E501
                )
            if (_settings_instance.LKNPD_INN or _settings_instance.LKNPD_PASSWORD) and not (
                _settings_instance.LKNPD_INN and _settings_instance.LKNPD_PASSWORD
            ):
                logger.warning(
                    "WARNING: LKNPD credentials are incomplete. Receipt sending will be disabled."
                )

        except ValidationError as e:
            logger.critical("Pydantic validation error while loading settings: %s", e)

            raise SystemExit(
                f"CRITICAL SETTINGS ERROR: {e}. Please check your .env file and Settings model."
            ) from e
    return _settings_instance


__all__ = [
    "CompatibilitySettings",
    "DBSettings",
    "EmailSettings",
    "PanelSettings",
    "PaymentSettings",
    "ReferralSettings",
    "RegistrationSettings",
    "Settings",
    "SupportSettings",
    "WebAppSettings",
    "get_settings",
]
