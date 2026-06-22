import unittest

from bot.utils.mini_app_url import (
    append_query_params,
    subscription_mini_app_install_url,
    subscription_mini_app_path_url,
    subscription_mini_app_renew_url,
    subscription_mini_app_topup_url,
    subscription_mini_app_trial_url,
    subscription_public_install_url,
)
from config.settings import Settings


class MiniAppUrlTests(unittest.TestCase):
    def test_append_query_params_adds_topup(self):
        self.assertEqual(
            append_query_params("https://app.example.com/home", {"topup": "regular"}),
            "https://app.example.com/home?topup=regular",
        )

    def test_append_query_params_merges_existing(self):
        self.assertEqual(
            append_query_params("https://app.example.com/?lang=ru", {"topup": "premium"}),
            "https://app.example.com/?lang=ru&topup=premium",
        )

    def test_subscription_mini_app_topup_url_none_when_unset(self):
        s = Settings(
            _env_file=None,
            BOT_TOKEN="x",
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            SUBSCRIPTION_MINI_APP_URL=None,
        )
        self.assertIsNone(subscription_mini_app_topup_url(s, "regular"))

    def test_subscription_mini_app_topup_url(self):
        s = Settings(
            _env_file=None,
            BOT_TOKEN="x",
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/webapp",
        )
        self.assertEqual(
            subscription_mini_app_topup_url(s, "regular"),
            "https://app.example.com/webapp?topup=regular",
        )
        self.assertEqual(
            subscription_mini_app_topup_url(s, "premium"),
            "https://app.example.com/webapp?topup=premium",
        )

    def test_subscription_mini_app_topup_url_preserves_existing_query(self):
        s = Settings(
            _env_file=None,
            BOT_TOKEN="x",
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/webapp?lang=ru",
        )
        self.assertEqual(
            subscription_mini_app_topup_url(s, "premium"),
            "https://app.example.com/webapp?lang=ru&topup=premium",
        )

    def test_subscription_mini_app_renew_url(self):
        s = Settings(
            _env_file=None,
            BOT_TOKEN="x",
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/webapp?lang=ru",
        )
        self.assertEqual(
            subscription_mini_app_renew_url(s, "premium"),
            "https://app.example.com/webapp?lang=ru&renew=1&renew_tariff=premium",
        )

    def test_subscription_mini_app_path_url(self):
        s = Settings(
            _env_file=None,
            BOT_TOKEN="x",
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/webapp/",
        )
        self.assertEqual(
            subscription_mini_app_path_url(s, "/install"),
            "https://app.example.com/webapp/install",
        )
        self.assertEqual(
            subscription_mini_app_install_url(s),
            "https://app.example.com/webapp/install",
        )
        self.assertEqual(
            subscription_mini_app_trial_url(s),
            "https://app.example.com/webapp/trial",
        )

    def test_subscription_public_install_url_uses_origin(self):
        s = Settings(
            _env_file=None,
            BOT_TOKEN="x",
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/webapp",
        )
        self.assertEqual(
            subscription_public_install_url(s, "8f559061460e8fede78ef18dce887236"),
            "https://app.example.com/s/8f559061460e8fede78ef18dce887236",
        )
