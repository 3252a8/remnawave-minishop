import unittest
from types import SimpleNamespace
from typing import List
from unittest.mock import patch

from bot.services import user_email_notifications as module


class _FakeI18n:
    def gettext(self, language, key, **kwargs):
        values = {
            "email_payment_failed_subject": "Payment failed",
            "email_user_notification_intro": "Account notification.",
            "email_user_notification_cta": "Open dashboard",
            "email_user_notification_text_dashboard": "Dashboard: {url}",
            "email_footer_auto": "Sent automatically by {brand}.",
        }
        return values.get(key, key).format(**kwargs)


class _FakeEmailService:
    instances: List["_FakeEmailService"] = []

    def __init__(self, settings, i18n=None):
        self.settings = settings
        self.i18n = i18n
        self.sent: List[dict] = []
        _FakeEmailService.instances.append(self)

    async def send_rendered_email(self, *, email, content):
        self.sent.append({"email": email, "content": content})


def _settings(**overrides):
    values = {
        "email_auth_configured": True,
        "DEFAULT_LANGUAGE": "en",
        "WEBAPP_PRIMARY_COLOR": "#00fe7a",
        "WEBAPP_TITLE": "Mini Shop",
        "WEBAPP_LOGO_URL": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SendUserNotificationEmailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _FakeEmailService.instances = []

    async def test_sends_rendered_notification_to_linked_email(self):
        user = SimpleNamespace(email="user@example.com", language_code="en")

        with patch.object(module, "EmailAuthService", _FakeEmailService):
            sent = await module.send_user_notification_email(
                settings=_settings(),
                i18n=_FakeI18n(),
                user=user,
                subject_key="email_payment_failed_subject",
                message_text="<b>Important</b>\n<script>alert(1)</script>",
                dashboard_url="https://app.example.com/account",
            )

        self.assertTrue(sent)
        self.assertEqual(len(_FakeEmailService.instances), 1)
        payload = _FakeEmailService.instances[0].sent[0]
        self.assertEqual(payload["email"], "user@example.com")
        content = payload["content"]
        self.assertEqual(content.subject, "Payment failed")
        self.assertIn("Important", content.text)
        self.assertIn("Dashboard: https://app.example.com/account", content.text)
        self.assertIn("<strong>Important</strong>", content.html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content.html)

    async def test_skips_when_smtp_is_not_configured(self):
        user = SimpleNamespace(email="user@example.com", language_code="en")

        with patch.object(module, "EmailAuthService", _FakeEmailService):
            sent = await module.send_user_notification_email(
                settings=_settings(email_auth_configured=False),
                i18n=_FakeI18n(),
                user=user,
                subject_key="email_payment_failed_subject",
                message_text="Payment failed",
            )

        self.assertFalse(sent)
        self.assertEqual(_FakeEmailService.instances, [])

    async def test_skips_when_user_has_no_email(self):
        user = SimpleNamespace(email=" ", language_code="en")

        with patch.object(module, "EmailAuthService", _FakeEmailService):
            sent = await module.send_user_notification_email(
                settings=_settings(),
                i18n=_FakeI18n(),
                user=user,
                subject_key="email_payment_failed_subject",
                message_text="Payment failed",
            )

        self.assertFalse(sent)
        self.assertEqual(_FakeEmailService.instances, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
