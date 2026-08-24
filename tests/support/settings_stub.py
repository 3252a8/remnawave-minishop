from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from config.settings_mixins import _split_csv
from config.settings_models import (
    PanelSettings,
    PartnerSettings,
    PartnerWithdrawalMethod,
    ReferralSettings,
    RegistrationSettings,
    SupportSettings,
    WebAppSettings,
)
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
    "PANEL_WRITE_MODE": "auto",
    "PARTNER_PROGRAM_ENABLED": False,
    "PARTNER_AUTO_ENROLLMENT_ENABLED": False,
    "PARTNER_REFERRAL_PROGRAM_DISABLED": False,
    "PARTNER_WITHDRAWALS_ENABLED": True,
    "PARTNER_BALANCE_PAYMENT_ENABLED": True,
    "PARTNER_CLIENT_WELCOME_BONUS_ENABLED": False,
    "PARTNER_CLIENT_PAYMENT_BONUS_ENABLED": False,
    "PARTNER_ONE_BONUS_PER_CLIENT": True,
    "PARTNER_DEFAULT_COMMISSION_BPS": 3000,
    "PARTNER_COMMISSION_HOLD_DAYS": 0,
    "PARTNER_ELIGIBLE_CURRENCIES": '["RUB"]',
    "PARTNER_EXCLUDED_SALE_MODES": "[]",
    "PARTNER_WITHDRAWAL_METHODS_JSON": "[]",
    "PARTNER_TELEGRAM_LINK_ENABLED": True,
    "PARTNER_WEBAPP_LINK_ENABLED": True,
    "PARTNER_APPLICATION_MESSAGE_MAX_LENGTH": 2000,
    "PARTNER_MAX_ACTIVE_WITHDRAWALS": 3,
    "PARTNER_REAPPLICATION_ENABLED": False,
    "PARTNER_REAPPLICATION_COOLDOWN_DAYS": 0,
    "PARTNER_LIST_PAGE_LIMIT": 50,
    "PARTNER_APPLICATION_RATE_LIMIT_HOURS": 24,
    "PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS": 10,
    "PARTNER_AUDIT_RETENTION_DAYS": 1095,
    "PARTNER_REQUISITES_RETENTION_DAYS": 90,
    "PARTNER_REQUISITES_ENCRYPTION_KEY": None,
    "PARTNER_REQUISITES_KEY_ID": "v1",
    "PROFILE_SYNC_CACHE_TTL_SECONDS": 900,
    "REDIS_KEY_PREFIX": "tests",
    "REDIS_URL": None,
    "REFERRAL_PROGRAM_ENABLED": True,
    "REFERRAL_ONE_BONUS_PER_REFEREE": False,
    "REFERRAL_WELCOME_BONUS_DAYS": 0,
    "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED": True,
    "REFERRAL_WEBAPP_LINK_ENABLED": True,
    "REFERRAL_TELEGRAM_LINK_ENABLED": True,
    "REGISTRATION_INVITE_ONLY_ENABLED": False,
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
    "TELEGRAM_BOT_PROXY_URL": None,
    "TELEGRAM_OAUTH_CLIENT_ID": None,
    "TELEGRAM_OAUTH_CLIENT_SECRET": None,
    "TELEGRAM_OAUTH_REQUEST_ACCESS": None,
    "TELEGRAM_OAUTH_USE_BOT_PROXY": True,
    "TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS": 20,
    "TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS": 30,
    "TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED": False,
    "TORRENT_BLOCKER_NOTIFICATIONS_ENABLED": False,
    "TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS": 3600,
    "TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP": False,
    "TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED": True,
    "TRIAL_DURATION_DAYS": 3,
    "TRIAL_ENABLED": True,
    "TRIAL_HWID_DEVICE_LIMIT": None,
    "TRIAL_TRAFFIC_LIMIT_GB": 5.0,
    "TRIAL_TRAFFIC_STRATEGY": "NO_RESET",
    "TRIAL_WITHOUT_TELEGRAM_ENABLED": True,
    "USER_HWID_DEVICE_LIMIT": None,
    "USER_TRAFFIC_STRATEGY": "NO_RESET",
    "WEBAPP_DEVICES_CACHE_TTL_SECONDS": 5,
    "WEBAPP_ENABLED": True,
    "WEBAPP_FAVICON_URL": None,
    "WEBAPP_FAVICON_USE_CUSTOM": False,
    "WEBAPP_LOGO_FAVICON_URL": None,
    "WEBAPP_LOGO_URL": None,
    "WEBAPP_ME_CACHE_TTL_SECONDS": 15,
    "WEBAPP_API_BASE_URL": "/api",
    "MINISHOP_EDGE_TOKEN": "",
    "MINISHOP_EDGE_TOKEN_HEADER": "X-Minishop-Edge-Token",
    "WEBAPP_PRIMARY_COLOR": "#00fe7a",
    "WEBAPP_SERVER_HOST": "0.0.0.0",
    "WEBAPP_SERVER_PORT": 8080,
    "WEBAPP_SESSION_SECRET": "test-session-secret",
    "WEBAPP_SESSION_TTL_SECONDS": 86400,
    "WEBAPP_TITLE": "/minishop",
    "WEBAPP_AUTH_MAX_AGE_SECONDS": 86400,
    "WEBAPP_LOGIN_TOKEN_TTL_SECONDS": 600,
    "WEBHOOK_SECRET_TOKEN": "test-webhook-secret",
}


class SettingsStub(SimpleNamespace):
    @property
    def disposable_email_domains(self) -> list[str]:
        domains: list[str] = _split_csv(self.DISPOSABLE_EMAIL_DOMAINS)
        return domains

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
        proxies: list[str] = _split_csv(getattr(self, "TRUSTED_PROXIES", None))
        return proxies

    @property
    def webapp_settings(self) -> WebAppSettings:
        return WebAppSettings(
            title=getattr(self, "WEBAPP_TITLE", "/minishop"),
            primary_color=getattr(self, "WEBAPP_PRIMARY_COLOR", "#00fe7a"),
            logo_url=getattr(self, "WEBAPP_LOGO_URL", None),
            favicon_use_custom=bool(getattr(self, "WEBAPP_FAVICON_USE_CUSTOM", False)),
            favicon_url=getattr(self, "WEBAPP_FAVICON_URL", None),
            logo_favicon_url=getattr(self, "WEBAPP_LOGO_FAVICON_URL", None),
            session_ttl_seconds=int(getattr(self, "WEBAPP_SESSION_TTL_SECONDS", 86400)),
            session_secret=getattr(self, "WEBAPP_SESSION_SECRET", "test-session-secret"),
            webhook_secret_token=getattr(self, "WEBHOOK_SECRET_TOKEN", "test-webhook-secret"),
            auth_max_age_seconds=int(getattr(self, "WEBAPP_AUTH_MAX_AGE_SECONDS", 86400)),
            login_token_ttl_seconds=int(getattr(self, "WEBAPP_LOGIN_TOKEN_TTL_SECONDS", 600)),
            server_host=getattr(self, "WEBAPP_SERVER_HOST", "0.0.0.0"),
            server_port=int(getattr(self, "WEBAPP_SERVER_PORT", 8080)),
            enabled=bool(getattr(self, "WEBAPP_ENABLED", True)),
            trusted_proxies=self.trusted_proxies,
        )

    @property
    def panel_settings(self) -> PanelSettings:
        return PanelSettings(
            api_url=getattr(self, "PANEL_API_URL", None),
            api_key=getattr(self, "PANEL_API_KEY", None),
            api_cookie=getattr(self, "PANEL_API_COOKIE", None),
            webhook_secret=getattr(self, "PANEL_WEBHOOK_SECRET", None),
            write_mode=getattr(self, "PANEL_WRITE_MODE", "auto"),
            dry_run_enabled=self.panel_dry_run_enabled,
            api_total_timeout_seconds=float(getattr(self, "PANEL_API_TOTAL_TIMEOUT_SECONDS", 25)),
            api_connect_timeout_seconds=float(
                getattr(self, "PANEL_API_CONNECT_TIMEOUT_SECONDS", 8)
            ),
            api_sock_connect_timeout_seconds=float(
                getattr(self, "PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS", 8)
            ),
            api_sock_read_timeout_seconds=float(
                getattr(self, "PANEL_API_SOCK_READ_TIMEOUT_SECONDS", 15)
            ),
        )

    @property
    def panel_dry_run_enabled(self) -> bool:
        mode = (
            str(getattr(self, "PANEL_WRITE_MODE", "auto") or "auto")
            .strip()
            .lower()
            .replace(
                "-",
                "_",
            )
        )
        if mode == "dry_run":
            return True
        if mode == "live":
            return False
        runtime = str(getattr(self, "APP_RUNTIME_MODE", "production") or "production").lower()
        return runtime in {"dev", "development", "local", "test", "testing"}

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
    def referral_settings(self) -> ReferralSettings:
        return ReferralSettings(
            enabled=bool(getattr(self, "REFERRAL_PROGRAM_ENABLED", True)),
            bonus_days_inviter_1_month=getattr(self, "REFERRAL_BONUS_DAYS_1_MONTH", 7),
            bonus_days_inviter_3_months=getattr(self, "REFERRAL_BONUS_DAYS_3_MONTHS", 7),
            bonus_days_inviter_6_months=getattr(self, "REFERRAL_BONUS_DAYS_6_MONTHS", 7),
            bonus_days_inviter_12_months=getattr(self, "REFERRAL_BONUS_DAYS_12_MONTHS", 7),
            bonus_days_referee_1_month=getattr(self, "REFEREE_BONUS_DAYS_1_MONTH", 3),
            bonus_days_referee_3_months=getattr(self, "REFEREE_BONUS_DAYS_3_MONTHS", 3),
            bonus_days_referee_6_months=getattr(self, "REFEREE_BONUS_DAYS_6_MONTHS", 3),
            bonus_days_referee_12_months=getattr(self, "REFEREE_BONUS_DAYS_12_MONTHS", 3),
            one_bonus_per_referee=bool(getattr(self, "REFERRAL_ONE_BONUS_PER_REFEREE", False)),
            welcome_bonus_days=int(getattr(self, "REFERRAL_WELCOME_BONUS_DAYS", 0)),
            welcome_bonus_without_telegram_enabled=bool(
                getattr(self, "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", True)
            ),
            webapp_link_enabled=bool(getattr(self, "REFERRAL_WEBAPP_LINK_ENABLED", True)),
            telegram_link_enabled=bool(getattr(self, "REFERRAL_TELEGRAM_LINK_ENABLED", True)),
            legacy_refs_enabled=bool(getattr(self, "LEGACY_REFS", True)),
        )

    @property
    def registration_settings(self) -> RegistrationSettings:
        return RegistrationSettings(
            invite_only_enabled=bool(getattr(self, "REGISTRATION_INVITE_ONLY_ENABLED", False)),
        )

    @property
    def partner_settings(self) -> PartnerSettings:
        import json

        return PartnerSettings(
            enabled=bool(self.PARTNER_PROGRAM_ENABLED),
            auto_enrollment_enabled=bool(self.PARTNER_AUTO_ENROLLMENT_ENABLED),
            referral_program_disabled=bool(self.PARTNER_REFERRAL_PROGRAM_DISABLED),
            withdrawals_enabled=bool(self.PARTNER_WITHDRAWALS_ENABLED),
            balance_payment_enabled=bool(self.PARTNER_BALANCE_PAYMENT_ENABLED),
            client_welcome_bonus_enabled=bool(self.PARTNER_CLIENT_WELCOME_BONUS_ENABLED),
            client_payment_bonus_enabled=bool(self.PARTNER_CLIENT_PAYMENT_BONUS_ENABLED),
            one_bonus_per_client=bool(self.PARTNER_ONE_BONUS_PER_CLIENT),
            default_commission_bps=int(self.PARTNER_DEFAULT_COMMISSION_BPS),
            commission_hold_days=int(self.PARTNER_COMMISSION_HOLD_DAYS),
            eligible_currencies=json.loads(self.PARTNER_ELIGIBLE_CURRENCIES),
            excluded_sale_modes=json.loads(self.PARTNER_EXCLUDED_SALE_MODES),
            withdrawal_methods=[
                PartnerWithdrawalMethod.model_validate(item)
                for item in json.loads(self.PARTNER_WITHDRAWAL_METHODS_JSON)
            ],
            telegram_link_enabled=bool(self.PARTNER_TELEGRAM_LINK_ENABLED),
            webapp_link_enabled=bool(self.PARTNER_WEBAPP_LINK_ENABLED),
            application_message_max_length=int(self.PARTNER_APPLICATION_MESSAGE_MAX_LENGTH),
            max_active_withdrawals=int(self.PARTNER_MAX_ACTIVE_WITHDRAWALS),
            reapplication_enabled=bool(self.PARTNER_REAPPLICATION_ENABLED),
            reapplication_cooldown_days=int(self.PARTNER_REAPPLICATION_COOLDOWN_DAYS),
            list_page_limit=int(self.PARTNER_LIST_PAGE_LIMIT),
            application_rate_limit_hours=int(self.PARTNER_APPLICATION_RATE_LIMIT_HOURS),
            withdrawal_rate_limit_seconds=int(self.PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS),
            audit_retention_days=int(self.PARTNER_AUDIT_RETENTION_DAYS),
            requisites_retention_days=int(self.PARTNER_REQUISITES_RETENTION_DAYS),
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
