from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from config.settings_mixins import _split_csv
from config.settings_models import SupportSettings
from config.webapp_themes_config import WebappThemesConfig

DEFAULT_SETTINGS_VALUES: dict[str, Any] = {
    "ADMIN_BROADCAST_AUDIENCE_COUNTS_CACHE_TTL_SECONDS": 30,
    "ADMIN_DB_STATS_CACHE_TTL_SECONDS": 5,
    "ADMIN_PANEL_STATS_CACHE_TTL_SECONDS": 15,
    "ADMIN_USERS_LIST_CACHE_TTL_SECONDS": 3,
    "BACKUP_DIR": "data/backups",
    "BACKUP_LOCK_TTL_SECONDS": 7200,
    "BACKUP_PG_DUMP_TIMEOUT_SECONDS": 1800,
    "BACKUP_PG_RESTORE_TIMEOUT_SECONDS": 1800,
    "CRYPT4_ENABLED": False,
    "CRYPT4_LINK_CACHE_TTL_SECONDS": 3600,
    "CRYPT4_REDIRECT_URL": None,
    "DEFAULT_CURRENCY_SYMBOL": "RUB",
    "DEFAULT_LANGUAGE": "ru",
    "DISPOSABLE_EMAIL_DOMAINS": "",
    "EMAIL_CODE_MAX_ATTEMPTS": 5,
    "EMAIL_CODE_RESEND_SECONDS": 60,
    "EMAIL_CODE_TTL_SECONDS": 600,
    "LOG_TRIAL_ACTIVATIONS": False,
    "PANEL_ALL_USERS_CACHE_TTL_SECONDS": 5,
    "PANEL_ALL_USERS_PAGE_SIZE": 1000,
    "PANEL_API_CONNECT_TIMEOUT_SECONDS": 8,
    "PANEL_API_COOKIE": None,
    "PANEL_API_KEY": "panel-key",
    "PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS": 8,
    "PANEL_API_SOCK_READ_TIMEOUT_SECONDS": 15,
    "PANEL_API_TOTAL_TIMEOUT_SECONDS": 25,
    "PANEL_API_URL": "https://panel.example.test/api",
    "PANEL_DEVICES_CACHE_TTL_SECONDS": 5,
    "PANEL_DRY_RUN_SYNTHETIC_CREATE": True,
    "PANEL_DRY_RUN_VALIDATE_REMOTE": False,
    "PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES": 104857600,
    "PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS": 3600,
    "PANEL_USER_CACHE_TTL_SECONDS": 5,
    "PROFILE_SYNC_CACHE_TTL_SECONDS": 900,
    "REDIS_KEY_PREFIX": "tests",
    "REDIS_URL": None,
    "REFERRAL_ONE_BONUS_PER_REFEREE": False,
    "REFERRAL_WELCOME_BONUS_DAYS": 0,
    "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED": True,
    "SUBSCRIPTION_GUIDES_CONFIG_CACHE_TTL_SECONDS": 300,
    "SUBSCRIPTION_GUIDES_ENABLED": True,
    "SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS": 300,
    "SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS": 300,
    "SUBSCRIPTION_MINI_APP_URL": "",
    "SUBSCRIPTION_NOTIFY_DAYS_BEFORE": 3,
    "SUBSCRIPTION_PAGE_CONFIG_JSON": "",
    "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED": False,
    "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED": True,
    "SUBSCRIPTION_PAGE_CONFIG_PATH": "data/subpage-config/multiapp.json",
    "SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS": 1800,
    "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED": False,
    "SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS": 300,
    "TELEGRAM_ACTION_COOLDOWN_ENABLED": True,
    "TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW": 240,
    "TELEGRAM_ANTIFLOOD_ENABLED": True,
    "TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW": 60,
    "TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW": 60,
    "TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW": 180,
    "TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW": 120,
    "TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW": 30,
    "TELEGRAM_ANTIFLOOD_WINDOW_SECONDS": 60,
    "TELEGRAM_BOT_MENU_DISABLED": False,
    "TELEGRAM_OAUTH_CLIENT_ID": None,
    "TELEGRAM_OAUTH_CLIENT_SECRET": None,
    "TELEGRAM_OAUTH_REQUEST_ACCESS": None,
    "TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS": 20,
    "TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS": 30,
    "TRIAL_DURATION_DAYS": 3,
    "TRIAL_ENABLED": True,
    "TRIAL_TRAFFIC_LIMIT_GB": 5.0,
    "TRIAL_TRAFFIC_STRATEGY": "NO_RESET",
    "TRIAL_WITHOUT_TELEGRAM_ENABLED": True,
    "USER_HWID_DEVICE_LIMIT": None,
    "WEBAPP_DEVICES_CACHE_TTL_SECONDS": 5,
    "WEBAPP_ENABLED": True,
    "WEBAPP_FAVICON_URL": None,
    "WEBAPP_FAVICON_USE_CUSTOM": False,
    "WEBAPP_LOGO_FAVICON_URL": None,
    "WEBAPP_LOGO_URL": None,
    "WEBAPP_ME_CACHE_TTL_SECONDS": 15,
    "WEBAPP_PRIMARY_COLOR": "#00fe7a",
    "WEBAPP_TITLE": "/minishop",
}


class SettingsStub(SimpleNamespace):
    @property
    def disposable_email_domains(self) -> list[str]:
        return _split_csv(self.DISPOSABLE_EMAIL_DOMAINS)

    @property
    def email_auth_configured(self) -> bool:
        if hasattr(self, "_email_auth_configured"):
            return bool(self._email_auth_configured)
        return bool(
            getattr(self, "SMTP_HOST", None)
            and getattr(self, "SMTP_PORT", None)
            and getattr(self, "SMTP_USERNAME", None)
            and getattr(self, "SMTP_PASSWORD", None)
            and getattr(self, "SMTP_FROM_EMAIL", None)
        )

    @email_auth_configured.setter
    def email_auth_configured(self, value: bool) -> None:
        self._email_auth_configured = value

    @property
    def tariffs_config(self) -> Any:
        return getattr(self, "_tariffs_config", None)

    @tariffs_config.setter
    def tariffs_config(self, value: Any) -> None:
        self._tariffs_config = value

    @property
    def traffic_packages(self) -> dict[float, float]:
        return getattr(self, "_traffic_packages", {})

    @property
    def stars_traffic_packages(self) -> dict[float, int]:
        return getattr(self, "_stars_traffic_packages", {})

    @property
    def traffic_sale_mode(self) -> bool:
        if hasattr(self, "_traffic_sale_mode"):
            return bool(self._traffic_sale_mode)
        return bool(self.traffic_packages or self.stars_traffic_packages)

    @property
    def trusted_proxies(self) -> list[str]:
        return _split_csv(getattr(self, "TRUSTED_PROXIES", None))

    @property
    def support_settings(self) -> SupportSettings:
        return SupportSettings(
            link=getattr(self, "SUPPORT_LINK", None),
            tickets_enabled=bool(getattr(self, "SUPPORT_TICKETS_ENABLED", True)),
            ticket_max_body_length=int(getattr(self, "SUPPORT_TICKET_MAX_BODY_LENGTH", 4000)),
            ticket_max_subject_length=int(getattr(self, "SUPPORT_TICKET_MAX_SUBJECT_LENGTH", 160)),
            ticket_rate_limit_per_hour=int(getattr(self, "SUPPORT_TICKET_RATE_LIMIT_PER_HOUR", 5)),
            admin_email_notifications_enabled=bool(
                getattr(self, "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED", False)
            ),
            admin_notification_cooldown_seconds=int(
                getattr(self, "SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS", 300)
            ),
            admin_email_cooldown_seconds=int(
                getattr(self, "SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS", 1800)
            ),
        )

    @property
    def user_traffic_limit_bytes(self) -> int:
        return int(float(getattr(self, "USER_TRAFFIC_LIMIT_GB", 0) or 0) * 1024**3)

    @property
    def webapp_themes_catalog(self) -> WebappThemesConfig:
        return getattr(
            self,
            "_webapp_themes_catalog",
            WebappThemesConfig(default_theme="dark", themes=[]),
        )

    def subscription_purchase_description(self, language: str | None = None) -> str:
        if not getattr(self, "SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED", True):
            return ""
        normalized = (language or self.DEFAULT_LANGUAGE or "ru").lower()
        if normalized.startswith("en"):
            return getattr(self, "SUBSCRIPTION_PURCHASE_DESCRIPTION_EN", "")
        return getattr(self, "SUBSCRIPTION_PURCHASE_DESCRIPTION_RU", "")


def settings_stub(**overrides: Any) -> SettingsStub:
    values = dict(DEFAULT_SETTINGS_VALUES)
    for key in (
        "email_auth_configured",
        "stars_traffic_packages",
        "tariffs_config",
        "traffic_packages",
        "traffic_sale_mode",
        "webapp_themes_catalog",
    ):
        if key in overrides:
            overrides[f"_{key}"] = overrides.pop(key)
    values.update(overrides)
    return SettingsStub(**values)
