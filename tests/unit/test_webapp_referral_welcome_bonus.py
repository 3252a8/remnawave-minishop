from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import auth as auth_module
from bot.app.web.webapp import auth_referral
from config.settings_defaults import DEFAULT_DISPOSABLE_EMAIL_DOMAINS
from tests.support.settings_stub import settings_stub


class _Session:
    def __init__(self):
        self.commit_count = 0
        self.rollback_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


class WebAppReferralWelcomeBonusTests(IsolatedAsyncioTestCase):
    async def test_partner_link_registration_can_receive_shared_welcome_bonus_once(self):
        end_date = datetime(2026, 1, 9, 3, 4, tzinfo=UTC)
        settings = settings_stub(
            REFERRAL_PROGRAM_ENABLED=False,
            PARTNER_PROGRAM_ENABLED=True,
            PARTNER_CLIENT_WELCOME_BONUS_ENABLED=True,
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="",
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=None,
            telegram_id=123456,
            email="person@example.com",
            referral_welcome_bonus_claimed_at=None,
        )
        session = SimpleNamespace()
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=end_date),
        )
        request = SimpleNamespace(
            app={"settings": settings, "subscription_service": subscription_service}
        )

        with (
            patch(
                "bot.app.web.webapp.auth_referral.user_dal.lock_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.app.web.webapp.auth_referral.subscription_dal.has_any_subscription_for_user",
                AsyncMock(return_value=False),
            ),
            patch(
                "bot.app.web.webapp.auth_referral.PartnerProgramService.client_welcome_bonus_eligible",
                AsyncMock(return_value=True),
            ) as eligible,
        ):
            result = await auth_module._apply_referral_welcome_bonus_if_needed(
                request,
                session,
                user,
                "p_partner-code",
            )

        self.assertEqual(result, end_date)
        self.assertIsNotNone(user.referral_welcome_bonus_claimed_at)
        eligible.assert_awaited_once_with(session, user_id=42)
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            3,
            reason="referral_welcome_bonus",
            tariff_key="standard",
        )

    async def test_email_only_referral_welcome_bonus_uses_configured_tariff_when_enabled(self):
        end_date = datetime(2026, 1, 9, 3, 4, tzinfo=UTC)
        settings = settings_stub(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="",
            tariffs_config=SimpleNamespace(
                default_tariff="standard",
                referral_welcome_bonus_tariff="starter",
            ),
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=None,
            email="person@example.com",
            referral_welcome_bonus_claimed_at=None,
        )
        session = SimpleNamespace()
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=end_date),
        )
        request = SimpleNamespace(
            app={"settings": settings, "subscription_service": subscription_service}
        )

        with (
            patch(
                "bot.app.web.webapp.auth_referral.user_dal.lock_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.app.web.webapp.auth_referral.subscription_dal.has_any_subscription_for_user",
                AsyncMock(return_value=False),
            ),
        ):
            result = await auth_module._apply_referral_welcome_bonus_if_needed(
                request,
                session,
                user,
                "ABC123",
            )

        self.assertEqual(result, end_date)
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            3,
            reason="referral_welcome_bonus",
            tariff_key="starter",
        )

    async def test_email_only_referral_welcome_bonus_waits_for_telegram_when_disabled(self):
        settings = settings_stub(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=False,
            DISPOSABLE_EMAIL_DOMAINS="",
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=None,
            email="person@example.com",
        )
        subscription_service = SimpleNamespace(extend_active_subscription_days=AsyncMock())
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
        subscription_service.extend_active_subscription_days.assert_not_awaited()

    async def test_disposable_email_referral_welcome_bonus_requires_telegram(self):
        settings = settings_stub(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=None,
            email="person@ogzmail.com",
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
        end_date = datetime(2026, 1, 9, 3, 4, tzinfo=UTC)
        settings = settings_stub(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=123456,
            email="person@ogzmail.com",
            is_banned=False,
            referral_welcome_bonus_claimed_at=None,
        )
        session = _Session()
        subscription_service = SimpleNamespace(
            has_active_subscription=AsyncMock(return_value=False),
            extend_active_subscription_days=AsyncMock(return_value=end_date),
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "subscription_service": subscription_service,
                "async_session_factory": lambda: session,
            }
        )

        with (
            patch(
                "bot.app.web.webapp.auth_referral.user_dal.get_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.app.web.webapp.auth_referral.user_dal.lock_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.app.web.webapp.auth_referral.subscription_dal.has_any_subscription_for_user",
                AsyncMock(return_value=False),
            ) as has_history,
        ):
            result = await auth_referral._grant_deferred_referral_welcome_bonus_after_telegram_link(
                request, 42
            )

        self.assertEqual(result, end_date)
        self.assertEqual(session.commit_count, 1)
        self.assertEqual(session.rollback_count, 0)
        has_history.assert_awaited_once_with(session, 42)
        subscription_service.has_active_subscription.assert_not_awaited()
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            3,
            reason="referral_welcome_bonus",
            tariff_key="standard",
        )
        # A successful grant must mark the bonus as claimed so it cannot be
        # granted again after this one expires.
        self.assertIsNotNone(user.referral_welcome_bonus_claimed_at)

    async def test_already_claimed_referral_welcome_bonus_is_not_granted_again(self):
        settings = settings_stub(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="",
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=123456,
            email="person@example.com",
            referral_welcome_bonus_claimed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session = SimpleNamespace()
        subscription_service = SimpleNamespace(
            has_active_subscription=AsyncMock(return_value=False),
            extend_active_subscription_days=AsyncMock(),
        )
        request = SimpleNamespace(
            app={"settings": settings, "subscription_service": subscription_service}
        )

        with patch(
            "bot.app.web.webapp.auth_referral.user_dal.lock_user_by_id",
            AsyncMock(return_value=user),
        ):
            result = await auth_module._apply_referral_welcome_bonus_if_needed(
                request,
                session,
                user,
                "ABC123",
            )

        self.assertIsNone(result)
        subscription_service.has_active_subscription.assert_not_awaited()
        subscription_service.extend_active_subscription_days.assert_not_awaited()

    async def test_historical_subscription_blocks_referral_welcome_bonus(self):
        settings = settings_stub(
            REFERRAL_WELCOME_BONUS_DAYS=3,
            REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True,
            DISPOSABLE_EMAIL_DOMAINS="",
            tariffs_config=SimpleNamespace(default_tariff="standard"),
        )
        user = SimpleNamespace(
            user_id=42,
            referred_by_id=7,
            telegram_id=123456,
            email="person@example.com",
            referral_welcome_bonus_claimed_at=None,
        )
        session = SimpleNamespace()
        subscription_service = SimpleNamespace(
            has_active_subscription=AsyncMock(return_value=False),
            extend_active_subscription_days=AsyncMock(),
        )
        request = SimpleNamespace(
            app={"settings": settings, "subscription_service": subscription_service}
        )

        with (
            patch(
                "bot.app.web.webapp.auth_referral.user_dal.lock_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.app.web.webapp.auth_referral.subscription_dal.has_any_subscription_for_user",
                AsyncMock(return_value=True),
            ) as has_history,
        ):
            result = await auth_module._apply_referral_welcome_bonus_if_needed(
                request,
                session,
                user,
                "ABC123",
            )

        self.assertIsNone(result)
        has_history.assert_awaited_once_with(session, 42)
        subscription_service.extend_active_subscription_days.assert_not_awaited()
