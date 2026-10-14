"""Referral welcome bonus added to the free trial."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.referral_welcome_trial import (
    referral_welcome_bonus_joins_trial,
    referral_welcome_trial_bonus_days,
)
from tests.support.settings_stub import settings_stub


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "REFERRAL_WELCOME_BONUS_DAYS": 3,
        "REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL": True,
        "TRIAL_DURATION_DAYS": 7,
    }
    values.update(overrides)
    return settings_stub(**values)


def _user(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "user_id": 42,
        "referred_by_id": 7,
        "telegram_id": 42,
        "email": None,
        "referral_welcome_bonus_claimed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ReferralWelcomeBonusJoinsTrialTests(IsolatedAsyncioTestCase):
    def test_bonus_joins_only_an_enabled_free_trial(self) -> None:
        self.assertTrue(referral_welcome_bonus_joins_trial(_settings()))
        self.assertFalse(
            referral_welcome_bonus_joins_trial(
                _settings(REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL=False)
            )
        )
        self.assertFalse(referral_welcome_bonus_joins_trial(_settings(TRIAL_ENABLED=False)))
        self.assertFalse(referral_welcome_bonus_joins_trial(_settings(TRIAL_DURATION_DAYS=0)))
        self.assertFalse(referral_welcome_bonus_joins_trial(_settings(TRIAL_PAYMENT_ENABLED=True)))
        self.assertFalse(
            referral_welcome_bonus_joins_trial(_settings(REFERRAL_WELCOME_BONUS_DAYS=0))
        )

    async def test_invited_user_gets_bonus_days_once(self) -> None:
        session = SimpleNamespace()

        self.assertEqual(await referral_welcome_trial_bonus_days(session, _settings(), _user()), 3)
        claimed = _user(referral_welcome_bonus_claimed_at=datetime(2026, 10, 1, tzinfo=UTC))
        self.assertEqual(await referral_welcome_trial_bonus_days(session, _settings(), claimed), 0)

    async def test_disabled_setting_adds_nothing(self) -> None:
        settings = _settings(REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL=False)

        self.assertEqual(
            await referral_welcome_trial_bonus_days(SimpleNamespace(), settings, _user()), 0
        )

    async def test_partner_client_eligibility_decides_without_a_referrer(self) -> None:
        session = SimpleNamespace()
        user = _user(referred_by_id=None)
        target = (
            "bot.services.referral_welcome_trial.PartnerProgramService."
            "client_welcome_bonus_eligible"
        )

        with patch(target, AsyncMock(return_value=True)) as eligible:
            self.assertEqual(await referral_welcome_trial_bonus_days(session, _settings(), user), 3)
        eligible.assert_awaited_once_with(session, user_id=42)
        with patch(target, AsyncMock(return_value=False)):
            self.assertEqual(await referral_welcome_trial_bonus_days(session, _settings(), user), 0)

    async def test_email_only_user_follows_the_welcome_bonus_telegram_rule(self) -> None:
        user = _user(telegram_id=None, email="person@example.com")

        required = _settings(REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=False)
        allowed = _settings(REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED=True)
        self.assertEqual(
            await referral_welcome_trial_bonus_days(SimpleNamespace(), required, user), 0
        )
        self.assertEqual(
            await referral_welcome_trial_bonus_days(SimpleNamespace(), allowed, user), 3
        )
