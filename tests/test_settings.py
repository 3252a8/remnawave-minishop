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

    def test_deprecated_webapp_appearance_env_values_are_ignored(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            WEBAPP_PRIMARY_COLOR="#ff0000",
            WEBAPP_LOGO_URL="https://cdn.example.com/logo.png",
            WEBAPP_LOGO_USE_EMOJI=True,
            WEBAPP_LOGO_EMOJI="🔥",
            WEBAPP_LOGO_EMOJI_FONT="twemoji",
            WEBAPP_FAVICON_USE_CUSTOM=True,
            WEBAPP_FAVICON_URL="https://cdn.example.com/favicon.png",
            WEBAPP_LOGO_FAVICON_URL="/webapp-favicon/abcdef1234567890/icon-180.png",
        )

        self.assertEqual(settings.WEBAPP_PRIMARY_COLOR, "#00fe7a")
        self.assertIsNone(settings.WEBAPP_LOGO_URL)
        self.assertFalse(settings.WEBAPP_LOGO_USE_EMOJI)
        self.assertEqual(settings.WEBAPP_LOGO_EMOJI, "🫥")
        self.assertEqual(settings.WEBAPP_LOGO_EMOJI_FONT, "system")
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
        settings.WEBAPP_LOGO_USE_EMOJI = False
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

    def test_support_admin_email_notifications_default_to_disabled(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
        )

        self.assertFalse(settings.SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED)

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
