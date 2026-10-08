"""Static field contract for computed settings and their runtime decorators."""

from __future__ import annotations

from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeVar,
    overload,
)

if TYPE_CHECKING:
    _Owner = TypeVar("_Owner")

    class _ComputedField[T]:
        @overload
        def __get__(self, obj: None, owner: type[_Owner]) -> property: ...

        @overload
        def __get__(self, obj: _Owner, owner: type[_Owner] | None = None) -> T: ...

        def __get__(
            self,
            obj: object | None,
            owner: type[object] | None = None,
        ) -> object: ...

    def computed_field[T](func: Callable[[Any], T]) -> _ComputedField[T]: ...

    class _SettingsFieldsProtocol(Protocol):
        POSTGRES_USER: str
        POSTGRES_PASSWORD: str
        POSTGRES_HOST: str
        POSTGRES_PORT: int
        POSTGRES_DB: str
        SMTP_HOST: str
        SMTP_PORT: int
        SMTP_FALLBACK_PORTS: str | None
        SMTP_TIMEOUT_SECONDS: int
        SMTP_USERNAME: str | None
        SMTP_PASSWORD: str | None
        SMTP_FROM_EMAIL: str | None
        SMTP_FROM_NAME: str | None
        SMTP_STARTTLS: bool
        SMTP_USE_SSL: bool
        EMAIL_CODE_TTL_SECONDS: int
        EMAIL_CODE_RESEND_SECONDS: int
        EMAIL_CODE_MAX_ATTEMPTS: int
        EMAIL_AUTH_SECRET: str | None
        WEBAPP_SESSION_SECRET: str
        PUBLIC_APP_URL: str | None
        SUBSCRIPTION_MINI_APP_URL: str | None
        TELEGRAM_ENABLED: bool
        BRUTE_FORCE_MAX_FAILURES: int
        BRUTE_FORCE_WINDOW_SECONDS: int
        BRUTE_FORCE_LOCK_SECONDS: int
        WEBAPP_TITLE: str
        WEBAPP_PRIMARY_COLOR: str
        WEBAPP_USER_THEME_MODE_ENABLED: bool
        WEBAPP_ADMIN_THEME_EFFECTS_ENABLED: bool
        WEBAPP_COMPACT_HOME_ENABLED: bool
        WEBAPP_COMPACT_LOGIN_ENABLED: bool
        WEBAPP_CHECKOUT_ADDON_VALUE_ANIMATION_ENABLED: bool
        WEBAPP_CHECKOUT_ADDON_EDITOR_EXPANDED_BY_DEFAULT: bool
        WEBAPP_LOGO_URL: str | None
        WEBAPP_FAVICON_USE_CUSTOM: bool
        WEBAPP_FAVICON_URL: str | None
        WEBAPP_LOGO_FAVICON_URL: str | None
        WEBAPP_SESSION_TTL_SECONDS: int
        WEBHOOK_SECRET_TOKEN: str
        WEBAPP_AUTH_MAX_AGE_SECONDS: int
        WEBAPP_LOGIN_TOKEN_TTL_SECONDS: int
        TELEGRAM_LOGIN_ENABLED: bool
        TELEGRAM_LOGIN_RECOMMENDED: bool
        TELEGRAM_LOGIN_WIDE_BUTTON: bool
        EMAIL_LOGIN_ENABLED: bool
        EMAIL_LOGIN_RECOMMENDED: bool
        EMAIL_LOGIN_WIDE_BUTTON: bool
        EMAIL_ADDRESS_CHANGE_ENABLED: bool
        GOOGLE_OIDC_ENABLED: bool
        GOOGLE_LOGIN_RECOMMENDED: bool
        GOOGLE_LOGIN_WIDE_BUTTON: bool
        GOOGLE_OIDC_CLIENT_ID: str | None
        GOOGLE_OIDC_CLIENT_SECRET: str | None
        YANDEX_OIDC_ENABLED: bool
        YANDEX_LOGIN_RECOMMENDED: bool
        YANDEX_LOGIN_WIDE_BUTTON: bool
        YANDEX_OIDC_CLIENT_ID: str | None
        YANDEX_OIDC_CLIENT_SECRET: str | None
        DISCORD_OIDC_ENABLED: bool
        DISCORD_LOGIN_RECOMMENDED: bool
        DISCORD_LOGIN_WIDE_BUTTON: bool
        DISCORD_OIDC_CLIENT_ID: str | None
        DISCORD_OIDC_CLIENT_SECRET: str | None
        PASSKEY_LOGIN_ENABLED: bool
        PASSKEY_LOGIN_RECOMMENDED: bool
        PASSKEY_LOGIN_WIDE_BUTTON: bool
        QR_LOGIN_ENABLED: bool
        QR_LOGIN_WIDE_BUTTON: bool
        PASSKEY_RP_ID: str | None
        PASSKEY_RP_NAME: str | None
        PASSKEY_ORIGINS: str | None
        PASSKEY_CHALLENGE_TTL_SECONDS: int
        WEBAPP_SERVER_HOST: str
        WEBAPP_SERVER_PORT: int
        WEBAPP_ENABLED: bool
        DEFAULT_CURRENCY_SYMBOL: str
        USER_BALANCE_ENABLED: bool
        USER_BALANCE_RECURRING_ENABLED: bool
        USER_BALANCE_CURRENCY: str
        USER_BALANCE_TOPUP_MIN_AMOUNT: float
        USER_BALANCE_TOPUP_MAX_AMOUNT: float
        USER_BALANCE_TOPUP_PRESETS: str
        PAYMENT_REQUEST_TIMEOUT_SECONDS: float
        ADMIN_IDS_STR: str
        PANEL_WRITE_MODE: str
        PANEL_API_URL: str | None
        PANEL_API_KEY: str | None
        PANEL_API_COOKIE: str | None
        PANEL_WEBHOOK_SECRET: str | None
        PANEL_API_TOTAL_TIMEOUT_SECONDS: float
        PANEL_API_CONNECT_TIMEOUT_SECONDS: float
        PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS: float
        PANEL_API_SOCK_READ_TIMEOUT_SECONDS: float
        APP_RUNTIME_MODE: str
        QA_AUTH_ENABLED: bool
        QA_PAYMENT_ENABLED: bool
        QA_PAYMENT_ADMIN_ONLY_ENABLED: bool
        QA_PAYMENT_SECRET: str
        TRIAL_TRAFFIC_LIMIT_GB: float | None
        TRIAL_PREMIUM_TRAFFIC_LIMIT_GB: float | None
        TRIAL_HWID_DEVICE_LIMIT: int | None
        USER_TRAFFIC_LIMIT_GB: float | None
        USER_SQUAD_UUIDS: str | None
        TRIAL_SQUAD_UUIDS: str | None
        TRIAL_PREMIUM_SQUAD_UUIDS: str | None
        DISPOSABLE_EMAIL_DOMAINS: str
        USER_EXTERNAL_SQUAD_UUID: str | None
        TRUSTED_PROXIES: str | None
        WEBHOOK_BASE_URL: str | None
        MONTH_1_ENABLED: bool
        RUB_PRICE_1_MONTH: int | None
        MONTH_3_ENABLED: bool
        RUB_PRICE_3_MONTHS: int | None
        MONTH_6_ENABLED: bool
        RUB_PRICE_6_MONTHS: int | None
        MONTH_12_ENABLED: bool
        RUB_PRICE_12_MONTHS: int | None
        STARS_ENABLED: bool
        STARS_ADMIN_ONLY_ENABLED: bool
        STARS_PRICE_1_MONTH: int | None
        STARS_PRICE_3_MONTHS: int | None
        STARS_PRICE_6_MONTHS: int | None
        STARS_PRICE_12_MONTHS: int | None
        TRAFFIC_PACKAGES: str | None
        STARS_TRAFFIC_PACKAGES: str | None
        TARIFF_TRAFFIC_WARNING_LEVELS: str
        TARIFFS_CONFIG_PATH: str
        WEBAPP_DEFAULT_THEME: str | None
        WEBAPP_THEMES_DIR: str
        REFERRAL_PROGRAM_ENABLED: bool
        REFERRAL_BONUS_DAYS_INVITER_1_MONTH: int | None
        REFERRAL_BONUS_DAYS_INVITER_3_MONTHS: int | None
        REFERRAL_BONUS_DAYS_INVITER_6_MONTHS: int | None
        REFERRAL_BONUS_DAYS_INVITER_12_MONTHS: int | None
        REFERRAL_BONUS_DAYS_REFEREE_1_MONTH: int | None
        REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS: int | None
        REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS: int | None
        REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS: int | None
        REFERRAL_ONE_BONUS_PER_REFEREE: bool
        REFERRAL_GIFT_ACTIVATION_ENABLED: bool
        REFERRAL_WELCOME_BONUS_DAYS: int
        REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED: bool
        REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL: bool
        REFERRAL_WEBAPP_LINK_ENABLED: bool
        REFERRAL_TELEGRAM_LINK_ENABLED: bool
        PARTNER_PROGRAM_ENABLED: bool
        PARTNER_AUTO_ENROLLMENT_ENABLED: bool
        PARTNER_REFERRAL_PROGRAM_DISABLED: bool
        PARTNER_WITHDRAWALS_ENABLED: bool
        PARTNER_BALANCE_PAYMENT_ENABLED: bool
        PARTNER_CLIENT_WELCOME_BONUS_ENABLED: bool
        PARTNER_CLIENT_PAYMENT_BONUS_ENABLED: bool
        PARTNER_ONE_BONUS_PER_CLIENT: bool
        PARTNER_DEFAULT_COMMISSION_BPS: int
        PARTNER_COMMISSION_HOLD_DAYS: int
        PARTNER_ELIGIBLE_CURRENCIES: str
        PARTNER_EXCLUDED_SALE_MODES: str
        PARTNER_WITHDRAWAL_METHODS_JSON: str
        PARTNER_TELEGRAM_LINK_ENABLED: bool
        PARTNER_WEBAPP_LINK_ENABLED: bool
        PARTNER_APPLICATION_MESSAGE_MAX_LENGTH: int
        PARTNER_MAX_ACTIVE_WITHDRAWALS: int
        PARTNER_REAPPLICATION_ENABLED: bool
        PARTNER_REAPPLICATION_COOLDOWN_DAYS: int
        PARTNER_LIST_PAGE_LIMIT: int
        PARTNER_APPLICATION_RATE_LIMIT_HOURS: int
        PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS: int
        PARTNER_AUDIT_RETENTION_DAYS: int
        PARTNER_REQUISITES_RETENTION_DAYS: int
        REGISTRATION_INVITE_ONLY_ENABLED: bool
        LEGACY_REFS: bool
        MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED: bool
        MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED: bool
        MIGRATION_REMNASHOP_IMPORTED_AT: str | None
        MIGRATION_REMNASHOP_NOTES: str | None
        SUPPORT_LINK: str | None
        SERVER_STATUS_ENABLED: bool
        SERVER_STATUS_PROVIDER: str
        SERVER_STATUS_URL: str | None
        SUPPORT_TICKETS_ENABLED: bool
        SUPPORT_TICKET_MAX_BODY_LENGTH: int
        SUPPORT_TICKET_MAX_SUBJECT_LENGTH: int
        SUPPORT_TICKET_RATE_LIMIT_PER_HOUR: int
        SUPPORT_MESSAGE_RATE_LIMIT_PER_MINUTE: int
        SUPPORT_IMAGE_RATE_LIMIT_PER_DAY: int
        SUPPORT_ADMIN_TELEGRAM_NOTIFICATIONS_ENABLED: bool
        SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED: bool
        SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS: int
        SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS: int
        PAYMENT_METHODS_ORDER: str | None
        SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED: bool
        DEFAULT_LANGUAGE: str
        MENU_BUTTONS_JSON: str
        TELEGRAM_MENU_APPEARANCE_JSON: str
        TELEGRAM_CUSTOM_EMOJI_LIBRARY_JSON: str
        SUBSCRIPTION_PURCHASE_DESCRIPTION_EN: str
        SUBSCRIPTION_PURCHASE_DESCRIPTION_RU: str

    class _SettingsComputedMixinBase(_SettingsFieldsProtocol):
        pass

else:
    from pydantic import computed_field as computed_field

    class _SettingsComputedMixinBase:
        pass
