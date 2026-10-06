import unittest

from config.settings import Settings


class QrLoginProviderSettingsTests(unittest.TestCase):
    def test_qr_is_offered_only_when_enabled(self):
        self.assertNotIn("qr", Settings.model_construct().webapp_auth_providers)
        enabled = Settings.model_construct(QR_LOGIN_ENABLED=True)
        self.assertIn("qr", enabled.webapp_auth_providers)
        self.assertNotIn("qr", enabled.webapp_wide_auth_providers)
        self.assertNotIn("qr", enabled.webapp_recommended_auth_providers)

    def test_wide_button_follows_its_own_toggle(self):
        settings = Settings.model_construct(QR_LOGIN_ENABLED=True, QR_LOGIN_WIDE_BUTTON=True)
        self.assertIn("qr", settings.webapp_wide_auth_providers)
