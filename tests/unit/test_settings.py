import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from bot.services import settings_override_service
from config.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_blank_postgres_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="",
            )

    def test_webapp_secrets_are_generated_when_missing(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertTrue(settings.WEBAPP_SESSION_SECRET)
        self.assertTrue(settings.WEBHOOK_SECRET_TOKEN)
        self.assertEqual(settings.WEBAPP_SESSION_TTL_SECONDS, 86400)

    def test_webapp_title_defaults_to_minishop(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertEqual(settings.WEBAPP_TITLE, "/minishop")

    def test_webapp_api_base_url_defaults_to_same_origin_api(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertEqual(settings.WEBAPP_API_BASE_URL, "/api")

    def test_internal_webhook_port_is_independent_from_host_port(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            WEB_SERVER_PORT=9090,
            WEB_SERVER_INTERNAL_PORT=8080,
        )

        self.assertEqual(settings.WEB_SERVER_PORT, 9090)
        self.assertEqual(settings.web_server_listen_port, 8080)

    def test_direct_run_falls_back_to_legacy_webhook_port(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            WEB_SERVER_PORT=9090,
        )

        self.assertEqual(settings.web_server_listen_port, 9090)

    def test_webapp_api_base_url_strips_same_origin_trailing_slashes(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            WEBAPP_API_BASE_URL="/api/",
        )

        self.assertEqual(settings.WEBAPP_API_BASE_URL, "/api")

    def test_minishop_edge_token_settings_are_optional_and_stripped(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            MINISHOP_EDGE_TOKEN="  edge-secret  ",
            MINISHOP_EDGE_TOKEN_HEADER="",
        )

        self.assertEqual(settings.MINISHOP_EDGE_TOKEN, "edge-secret")
        self.assertEqual(settings.MINISHOP_EDGE_TOKEN_HEADER, "X-Minishop-Edge-Token")

    def test_trusted_proxies_default_includes_private_proxy_ranges(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertEqual(
            settings.trusted_proxies,
            [
                "127.0.0.1",
                "::1",
                "10.0.0.0/8",
                "172.16.0.0/12",
                "192.168.0.0/16",
                "fc00::/7",
            ],
        )

    def test_panel_write_mode_defaults_to_live_in_production(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertEqual(settings.APP_RUNTIME_MODE, "production")
        self.assertEqual(settings.PANEL_WRITE_MODE, "auto")
        self.assertFalse(settings.panel_dry_run_enabled)

    def test_development_runtime_enables_panel_dry_run_in_auto_mode(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            APP_RUNTIME_MODE="development",
        )

        self.assertTrue(settings.panel_dry_run_enabled)

    def test_panel_write_mode_live_overrides_development_runtime(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            APP_RUNTIME_MODE="development",
            PANEL_WRITE_MODE="live",
        )

        self.assertFalse(settings.panel_dry_run_enabled)

    def test_panel_write_mode_rejects_unknown_value(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                PANEL_WRITE_MODE="danger",
            )

    def test_legacy_subscription_prices_have_defaults(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
        )

        self.assertEqual(
            settings.subscription_options,
            {1: 200.0, 3: 600.0, 6: 1200.0, 12: 2400.0},
        )

    def test_payment_settings_view_reflects_payment_fields(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            DEFAULT_CURRENCY_SYMBOL="EUR",
            PAYMENT_REQUEST_TIMEOUT_SECONDS=7,
            PAYMENT_METHODS_ORDER="stars,severpay",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            TRAFFIC_PACKAGES="10:199,50:799",
            STARS_TRAFFIC_PACKAGES="10:1000",
        )

        payment_settings = settings.payment_settings

        self.assertEqual(payment_settings.default_currency_symbol, "EUR")
        self.assertEqual(payment_settings.payment_request_timeout_seconds, 7)
        self.assertEqual(payment_settings.payment_methods_order[:2], ["stars", "severpay"])
        self.assertIn("stripe", payment_settings.payment_methods_order)
        self.assertEqual(
            payment_settings.subscription_options,
            settings.subscription_options,
        )
        self.assertEqual(
            payment_settings.stars_subscription_options,
            settings.stars_subscription_options,
        )
        self.assertEqual(payment_settings.traffic_packages, {10.0: 199.0, 50.0: 799.0})
        self.assertEqual(payment_settings.stars_traffic_packages, {10.0: 1000})
        self.assertTrue(payment_settings.traffic_sale_mode)

    def test_referral_settings_view_reflects_referral_fields(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            REFERRAL_BONUS_DAYS_1_MONTH=5,
            REFEREE_BONUS_DAYS_12_MONTHS=11,
            REFERRAL_ONE_BONUS_PER_REFEREE=False,
            REFERRAL_WELCOME_BONUS_DAYS=9,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=False,
            LEGACY_REFS=False,
        )

        referral_settings = settings.referral_settings

        self.assertEqual(referral_settings.bonus_days_inviter_1_month, 5)
        self.assertEqual(referral_settings.bonus_days_inviter_3_months, 7)
        self.assertEqual(referral_settings.bonus_days_referee_12_months, 11)
        self.assertEqual(referral_settings.bonus_days_referee_1_month, 1)
        self.assertFalse(referral_settings.one_bonus_per_referee)
        self.assertEqual(referral_settings.welcome_bonus_days, 9)
        self.assertFalse(referral_settings.welcome_bonus_without_telegram_enabled)
        self.assertFalse(referral_settings.legacy_refs_enabled)

    def test_registration_settings_view_reflects_invite_only_flag(self):
        default_settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )
        enabled_settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            REGISTRATION_INVITE_ONLY_ENABLED=True,
        )

        self.assertFalse(default_settings.registration_settings.invite_only_enabled)
        self.assertTrue(enabled_settings.registration_settings.invite_only_enabled)

    def test_support_settings_view_reflects_support_fields(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            SUPPORT_LINK="https://t.me/support",
            SUPPORT_TICKETS_ENABLED=False,
            SUPPORT_TICKET_MAX_BODY_LENGTH=1000,
            SUPPORT_TICKET_RATE_LIMIT_PER_HOUR=2,
            SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=True,
        )

        support_settings = settings.support_settings

        self.assertEqual(support_settings.link, "https://t.me/support")
        self.assertFalse(support_settings.tickets_enabled)
        self.assertEqual(support_settings.ticket_max_body_length, 1000)
        self.assertEqual(support_settings.ticket_max_subject_length, 160)
        self.assertEqual(support_settings.ticket_rate_limit_per_hour, 2)
        self.assertTrue(support_settings.admin_email_notifications_enabled)
        self.assertEqual(support_settings.admin_notification_cooldown_seconds, 300)
        self.assertEqual(support_settings.admin_email_cooldown_seconds, 1800)

    def test_support_link_normalizes_telegram_shortcuts(self):
        for raw in ("@help_center_bot", "t.me/help_center_bot"):
            with self.subTest(raw=raw):
                settings = Settings(
                    _env_file=None,
                    BOT_TOKEN="token",
                    POSTGRES_USER="app_user",
                    POSTGRES_PASSWORD="app_password",
                    SUPPORT_LINK=raw,
                )

                self.assertEqual(settings.SUPPORT_LINK, "https://t.me/help_center_bot")
                self.assertEqual(
                    settings.support_settings.link,
                    "https://t.me/help_center_bot",
                )

    def test_support_link_rejects_values_that_cannot_form_a_button_url(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                SUPPORT_LINK="not a link",
            )

    def test_support_link_preserves_external_https_url(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            SUPPORT_LINK="https://support.example.test/help",
        )

        self.assertEqual(
            settings.support_settings.link,
            "https://support.example.test/help",
        )

    def test_panel_settings_view_reflects_panel_fields(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            PANEL_API_URL="https://panel.example.com",
            PANEL_API_KEY="secret-key",
            PANEL_WEBHOOK_SECRET="hook",
            APP_RUNTIME_MODE="development",
        )

        panel_settings = settings.panel_settings

        self.assertEqual(panel_settings.api_url, "https://panel.example.com")
        self.assertEqual(panel_settings.api_key, "secret-key")
        self.assertIsNone(panel_settings.api_cookie)
        self.assertEqual(panel_settings.webhook_secret, "hook")
        self.assertEqual(panel_settings.write_mode, "auto")
        self.assertTrue(panel_settings.dry_run_enabled)
        self.assertEqual(panel_settings.api_total_timeout_seconds, 25)
        self.assertEqual(panel_settings.api_connect_timeout_seconds, 8)
        self.assertEqual(panel_settings.api_sock_read_timeout_seconds, 15)

    def test_compatibility_settings_view_reflects_migration_fields(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED=True,
            MIGRATION_REMNASHOP_IMPORTED_AT="2026-01-02T03:04:05Z",
            MIGRATION_REMNASHOP_NOTES="migrated batch 1",
        )

        compatibility_settings = settings.compatibility_settings

        self.assertTrue(compatibility_settings.remnashop_referral_code_compat_enabled)
        self.assertFalse(compatibility_settings.remnashop_promo_code_compat_enabled)
        self.assertEqual(compatibility_settings.remnashop_imported_at, "2026-01-02T03:04:05Z")
        self.assertEqual(compatibility_settings.remnashop_notes, "migrated batch 1")

    def test_subscription_guides_defaults_are_enabled(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertTrue(settings.SUBSCRIPTION_GUIDES_ENABLED)
        self.assertTrue(settings.SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED)
        self.assertTrue(settings.SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED)
        self.assertFalse(settings.SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED)
        self.assertEqual(
            settings.SUBSCRIPTION_PAGE_CONFIG_PATH,
            "data/subpage-config/multiapp.json",
        )
        self.assertEqual(settings.SUBSCRIPTION_PAGE_CONFIG_JSON, "")
        self.assertEqual(settings.SUBSCRIPTION_GUIDES_CONFIG_CACHE_TTL_SECONDS, 300)
        self.assertEqual(settings.SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS, 300)
        self.assertEqual(settings.SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS, 300)

    def test_deprecated_webapp_appearance_env_values_are_ignored(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            WEBAPP_PRIMARY_COLOR="#ff0000",
            WEBAPP_LOGO_URL="https://cdn.example.com/logo.png",
            WEBAPP_FAVICON_USE_CUSTOM=True,
            WEBAPP_FAVICON_URL="https://cdn.example.com/favicon.png",
            WEBAPP_LOGO_FAVICON_URL="/webapp-favicon/abcdef1234567890/icon-180.png",
        )

        self.assertEqual(settings.WEBAPP_PRIMARY_COLOR, "#00fe7a")
        self.assertIsNone(settings.WEBAPP_LOGO_URL)
        self.assertFalse(settings.WEBAPP_FAVICON_USE_CUSTOM)
        self.assertIsNone(settings.WEBAPP_FAVICON_URL)
        self.assertIsNone(settings.WEBAPP_LOGO_FAVICON_URL)

    def test_tariffs_config_missing_uses_legacy_fallback(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFFS_CONFIG_PATH="missing-tariffs.json",
            TRAFFIC_PACKAGES="10:199",
        )

        self.assertIsNone(settings.tariffs_config)
        self.assertTrue(settings.traffic_sale_mode)

    def test_existing_tariffs_config_disables_legacy_traffic_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tariffs.json"
            path.write_text(
                json.dumps(
                    {
                        "default_tariff": "standard",
                        "tariffs": [
                            {
                                "key": "standard",
                                "names": {"ru": "Стандарт"},
                                "descriptions": {},
                                "squad_uuids": ["uuid"],
                                "billing_model": "period",
                                "monthly_gb": 100,
                                "prices_rub": {"1": 150},
                                "prices_stars": {"1": 0},
                                "enabled_periods": [1],
                                "enabled": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                _env_file=None,
                BOT_TOKEN="token",
                POSTGRES_USER="app_user",
                POSTGRES_PASSWORD="app_password",
                TARIFFS_CONFIG_PATH=str(path),
                TRAFFIC_PACKAGES="10:199",
            )

            self.assertIsNotNone(settings.tariffs_config)
            self.assertFalse(settings.traffic_sale_mode)

    def test_appearance_backup_roundtrip_preserves_logo_theme_and_favicon_settings(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )
        settings.WEBAPP_LOGO_URL = "/webapp-uploaded-logo/logo-1111111111111111.png"
        settings.WEBAPP_LOGO_FAVICON_URL = "/webapp-favicon/aaaaaaaaaaaaaaaa/icon-180.png"
        settings.WEBAPP_FAVICON_USE_CUSTOM = True
        settings.WEBAPP_FAVICON_URL = "/webapp-favicon/bbbbbbbbbbbbbbbb/icon-180.png"
        settings.WEBAPP_PRIMARY_COLOR = "#123456"

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "appearance-settings.json"
            with patch.object(
                settings_override_service,
                "APPEARANCE_OVERRIDES_BACKUP_PATH",
                backup_path,
            ):
                settings_override_service.write_appearance_backup(settings)
                restored = settings_override_service._read_appearance_backup()

        self.assertEqual(
            restored["WEBAPP_LOGO_URL"],
            "/webapp-uploaded-logo/logo-1111111111111111.png",
        )
        self.assertEqual(restored["WEBAPP_PRIMARY_COLOR"], "#123456")
        self.assertEqual(
            restored["WEBAPP_FAVICON_URL"],
            "/webapp-favicon/bbbbbbbbbbbbbbbb/icon-180.png",
        )

    def test_trial_traffic_strategy_is_available(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TRIAL_TRAFFIC_STRATEGY="WEEK",
        )

        self.assertEqual(settings.TRIAL_TRAFFIC_STRATEGY, "WEEK")

    def test_traffic_strategy_legacy_aliases_are_canonicalized(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            USER_TRAFFIC_STRATEGY="monthly",
            TRIAL_TRAFFIC_STRATEGY="MONTHLY_ROLLING",
        )

        self.assertEqual(settings.USER_TRAFFIC_STRATEGY, "MONTH")
        self.assertEqual(settings.TRIAL_TRAFFIC_STRATEGY, "MONTH_ROLLING")

    def test_support_admin_email_notifications_default_to_disabled(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertFalse(settings.SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED)

    def test_backup_defaults_are_safe_and_blank_targets_use_log_fallback(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            BACKUP_CHAT_ID="",
            BACKUP_THREAD_ID="",
        )

        self.assertFalse(settings.BACKUP_ENABLED)
        self.assertEqual(settings.BACKUP_INTERVAL_SECONDS, 3600)
        self.assertEqual(settings.BACKUP_DIR, "data/backups")
        self.assertEqual(settings.BACKUP_LOCAL_RETENTION, 100)
        self.assertIsNone(settings.BACKUP_CHAT_ID)
        self.assertIsNone(settings.BACKUP_THREAD_ID)
        self.assertEqual(settings.BACKUP_COMPOSE_SOURCE_DIR, "/app/compose-source")
        self.assertIsNone(settings.BACKUP_COMPOSE_RESTORE_DIR)
        self.assertEqual(settings.BACKUP_PG_RESTORE_PATH, "pg_restore")

    def test_subscription_purchase_description_is_localized_and_toggleable(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            SUBSCRIPTION_PURCHASE_DESCRIPTION_RU="Русский текст",
            SUBSCRIPTION_PURCHASE_DESCRIPTION_EN="English text",
        )

        self.assertEqual(settings.subscription_purchase_description("ru"), "Русский текст")
        self.assertEqual(settings.subscription_purchase_description("en"), "English text")

        settings.SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED = False
        self.assertEqual(settings.subscription_purchase_description("ru"), "")

    def test_payment_button_presentation_env_values_are_available(self):
        """Presentation overrides now live on each provider's BaseSettings
        model instead of the central Settings — verify they're loaded from
        env and exposed via the provider bundle."""
        import os

        from bot.payment_providers import build_provider_configs, get_spec_presentation

        os.environ["PAYMENT_YOOKASSA_WEBAPP_LABEL_RU"] = "Карта"
        os.environ["PAYMENT_YOOKASSA_WEBAPP_LABEL_EN"] = "Card"
        os.environ["PAYMENT_YOOKASSA_WEBAPP_ICON"] = "CreditCard"
        os.environ["PAYMENT_YOOKASSA_TELEGRAM_LABEL_RU"] = "Банковская карта"
        os.environ["PAYMENT_YOOKASSA_TELEGRAM_LABEL_EN"] = "Bank card"
        os.environ["PAYMENT_YOOKASSA_TELEGRAM_EMOJI"] = "💳"
        try:
            build_provider_configs(force=True)
            presentation = get_spec_presentation("yookassa")
            self.assertIsNotNone(presentation)
            self.assertEqual(presentation.WEBAPP_LABEL_RU, "Карта")
            self.assertEqual(presentation.WEBAPP_LABEL_EN, "Card")
            self.assertEqual(presentation.WEBAPP_ICON, "CreditCard")
            self.assertEqual(presentation.TELEGRAM_LABEL_RU, "Банковская карта")
            self.assertEqual(presentation.TELEGRAM_LABEL_EN, "Bank card")
            self.assertEqual(presentation.TELEGRAM_EMOJI, "💳")
        finally:
            for key in (
                "PAYMENT_YOOKASSA_WEBAPP_LABEL_RU",
                "PAYMENT_YOOKASSA_WEBAPP_LABEL_EN",
                "PAYMENT_YOOKASSA_WEBAPP_ICON",
                "PAYMENT_YOOKASSA_TELEGRAM_LABEL_RU",
                "PAYMENT_YOOKASSA_TELEGRAM_LABEL_EN",
                "PAYMENT_YOOKASSA_TELEGRAM_EMOJI",
            ):
                os.environ.pop(key, None)

    def test_tariff_warning_levels_are_parsed(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TARIFF_TRAFFIC_WARNING_LEVELS="90,85,bad,95,90,100,0",
        )

        self.assertEqual(settings.tariff_traffic_warning_levels, [85, 90, 95])

    def test_subscription_hour_notification_default_is_available(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertEqual(settings.SUBSCRIPTION_NOTIFY_HOURS_BEFORE, 3)
        self.assertEqual(settings.SUBSCRIPTION_NOTIFICATION_WORKER_TICK_SECONDS, 300)
        self.assertTrue(settings.SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED)
