from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from bot.middlewares.i18n import JsonI18n
from bot.services.notification_service import NotificationService
from bot.utils.telegram_markup import remove_profile_link_buttons
from tests.support.settings_stub import settings_stub

PUBLIC_ID = "ms_" + "a" * 32


def _service(language: str = "en") -> NotificationService:
    service = NotificationService(
        bot=SimpleNamespace(send_message=AsyncMock()),
        settings=settings_stub(
            DEFAULT_LANGUAGE=language,
            SUBSCRIPTION_MINI_APP_URL="https://app.example.test/app",
            LOG_NEW_USERS=True,
            LOG_PAYMENTS=True,
            LOG_PROMO_ACTIVATIONS=True,
            LOG_TRIAL_ACTIVATIONS=True,
            LOG_SUSPICIOUS_ACTIVITY=True,
        ),
        i18n=JsonI18n(str(Path(__file__).resolve().parents[2] / "locales")),
        bot_username="shop_bot",
    )
    service._send_to_log_channel = AsyncMock()
    return service


class LogUserContextTests(IsolatedAsyncioTestCase):
    async def test_optional_localizer_keeps_available_identity_fields(self):
        service = _service()
        service.i18n = None
        display = service._format_user_display(
            PUBLIC_ID, username="alice", email="user<&@example.test", telegram_id=123456
        )
        self.assertEqual(
            display.splitlines(),
            [
                f"ID: <code>{PUBLIC_ID}</code>",
                "Telegram username: <code>@alice</code>",
                "Telegram ID: <code>123456</code>",
                "Email: <code>user&lt;&amp;@example.test</code>",
            ],
        )

    async def test_all_account_log_flows_share_identity_lines_and_navigation(self):
        cases = [
            ("notify_new_user_registration", {}),
            ("notify_new_email_user_registration", {"email": "user<&@example.test"}),
            (
                "notify_new_external_user_registration",
                {"provider": "google", "email": "user<&@example.test"},
            ),
            ("notify_account_email_linked", {"email": "user<&@example.test"}),
            (
                "notify_account_telegram_linked",
                {"email": "user<&@example.test", "telegram_id": 123456},
            ),
            (
                "notify_account_external_identity_linked",
                {
                    "provider": "google",
                    "link_source": "login",
                    "email": "user<&@example.test",
                    "telegram_id": 123456,
                },
            ),
            (
                "notify_payment_received",
                {"amount": 45, "currency": "RUB", "months": 1, "payment_provider": "wata"},
            ),
            ("notify_promo_activation", {"promo_code": "CODE", "bonus_days": 3}),
            ("notify_trial_activation", {"end_date": datetime(2026, 10, 1, tzinfo=UTC)}),
            ("notify_suspicious_promo_attempt", {"suspicious_input": "bad<&"}),
        ]
        user = SimpleNamespace(
            user_id=42,
            minishop_id=PUBLIC_ID,
            telegram_id=123456,
            username="alice",
            email="user<&@example.test",
            first_name=None,
        )
        for language in ("ru", "en"):
            service = _service(language)
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=SimpleNamespace())
            context.__aexit__ = AsyncMock(return_value=False)
            with (
                patch.object(service, "session_factory", MagicMock(return_value=context)),
                patch.object(service, "_public_user_id", AsyncMock(return_value=PUBLIC_ID)),
                patch(
                    "bot.services.notification_user_context.user_dal.get_user_by_id",
                    AsyncMock(return_value=user),
                ),
            ):
                for method, kwargs in cases:
                    with self.subTest(language=language, method=method):
                        service._send_to_log_channel.reset_mock()
                        await getattr(service, method)(user_id=42, **kwargs)
                        service._send_to_log_channel.assert_awaited_once()
                        call = service._send_to_log_channel.await_args
                        lines = call.args[0].splitlines()
                        for field in (PUBLIC_ID, "@alice", "123456", "user&lt;&amp;@example.test"):
                            matching = [line for line in lines if field in line]
                            self.assertEqual(len(matching), 1, (method, field, lines))
                        keyboard = call.kwargs["reply_markup"]
                        urls = [button.url for row in keyboard.inline_keyboard for button in row]
                        self.assertIn(
                            f"https://t.me/shop_bot?startapp=admin_user_{PUBLIC_ID}", urls
                        )
                        self.assertIn("tg://user?id=123456", urls)

    async def test_email_only_user_has_card_without_fabricated_telegram_fields(self):
        service = _service()
        await service.notify_new_email_user_registration(
            user_id=42, minishop_id=PUBLIC_ID, email="user@example.test"
        )
        call = service._send_to_log_channel.await_args
        self.assertIn(PUBLIC_ID, call.args[0])
        self.assertIn("Email:", call.args[0])
        self.assertNotIn("Telegram", call.args[0])
        keyboard = call.kwargs["reply_markup"]
        self.assertEqual(len(keyboard.inline_keyboard), 1)
        self.assertEqual(
            keyboard.inline_keyboard[0][0].url,
            f"https://t.me/shop_bot?startapp=admin_user_{PUBLIC_ID}",
        )

    async def test_rejected_profile_link_fallback_preserves_user_card(self):
        service = _service()
        keyboard = service._build_profile_keyboard(
            lambda key: key, 123456, user_id=42, minishop_id=PUBLIC_ID
        )
        fallback = remove_profile_link_buttons(keyboard)
        self.assertIsNotNone(fallback)
        assert fallback is not None
        self.assertEqual(len(fallback.inline_keyboard), 1)
        self.assertEqual(
            fallback.inline_keyboard[0][0].url,
            f"https://t.me/shop_bot?startapp=admin_user_{PUBLIC_ID}",
        )

    async def test_unresolved_bot_username_uses_card_callback(self):
        service = _service()
        service.bot_username = "YOUR_BOT_USERNAME"
        keyboard = service._build_profile_keyboard(
            lambda key: key, None, user_id=42, minishop_id=PUBLIC_ID
        )
        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data,
            "admin_user_card_from_list:42:0",
        )
