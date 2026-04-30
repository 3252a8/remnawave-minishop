import unittest

from pydantic import ValidationError

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

    def test_trial_traffic_strategy_is_available(self):
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            TRIAL_TRAFFIC_STRATEGY="WEEK",
        )

        self.assertEqual(settings.TRIAL_TRAFFIC_STRATEGY, "WEEK")
