from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import auth as auth_module


class WebAppReferralWelcomeBonusTests(IsolatedAsyncioTestCase):
    async def test_disposable_email_referral_welcome_bonus_requires_telegram(self):
        settings = SimpleNamespace(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="mailinator.com",
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=None,
            email="person@mailinator.com",
        )
        subscription_service = SimpleNamespace(
            has_active_subscription=AsyncMock(return_value=False),
            extend_active_subscription_days=AsyncMock(),
        )
        request = SimpleNamespace(
            app={"settings": settings, "subscription_service": subscription_service}
        )

        result = await auth_module._apply_referral_welcome_bonus_if_needed(
            request,
            SimpleNamespace(),
            user,
            "ABC123",
        )

        self.assertIsNone(result)
        subscription_service.has_active_subscription.assert_not_awaited()
        subscription_service.extend_active_subscription_days.assert_not_awaited()

    async def test_linked_telegram_allows_disposable_email_referral_welcome_bonus(self):
        end_date = datetime(2026, 1, 9, 3, 4, tzinfo=timezone.utc)
        settings = SimpleNamespace(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="mailinator.com",
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=123456,
            email="person@mailinator.com",
        )
        session = SimpleNamespace()
        subscription_service = SimpleNamespace(
            has_active_subscription=AsyncMock(return_value=False),
            extend_active_subscription_days=AsyncMock(return_value=end_date),
        )
        request = SimpleNamespace(
            app={"settings": settings, "subscription_service": subscription_service}
        )

        result = await auth_module._apply_referral_welcome_bonus_if_needed(
            request,
            session,
            user,
            "ABC123",
        )

        self.assertEqual(result, end_date)
        subscription_service.has_active_subscription.assert_awaited_once_with(session, 42)
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            3,
            reason="referral_welcome_bonus",
        )
