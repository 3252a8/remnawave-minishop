"""Behavioural tests for ``ReferralService.apply_referral_bonuses_for_payment``.

This is the entry point that every payment provider calls after a successful
``subscription`` purchase. The contract has several non-obvious branches that
have been wrong before in this project:

* skip when the referee has no inviter recorded;
* skip when ``REFERRAL_ONE_BONUS_PER_REFEREE`` is set and the referee already
  has prior succeeded payments;
* skip when the referee was already active at payment time and the caller
  asked to skip that case;
* award both the inviter bonus (extend existing or create new bonus sub)
  and the referee bonus (extend their freshly activated subscription).

The bot/i18n/panel collaborators are stubbed because we are testing branching
and DB intent, not network I/O.
"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

from bot.services.referral_service import ReferralService
from config.tariffs_config import TariffsConfig


def _make_settings(**overrides: Any) -> SimpleNamespace:
    base = dict(
        DEFAULT_LANGUAGE="en",
        REFERRAL_ONE_BONUS_PER_REFEREE=True,
        user_traffic_limit_bytes=0,
        referral_bonus_inviter={1: 7, 3: 21, 6: 45, 12: 90},
        referral_bonus_referee={1: 3, 3: 10, 6: 21, 12: 45},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_user(user_id: int, *, referred_by_id: Optional[int] = None, **fields):
    base = dict(
        user_id=user_id,
        first_name=f"User{user_id}",
        language_code="en",
        referred_by_id=referred_by_id,
        email=None,
        panel_user_uuid=f"panel-{user_id}",
    )
    base.update(fields)
    return SimpleNamespace(**base)


def _make_service(*, settings, subscription_service):
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    i18n = SimpleNamespace(gettext=lambda lang, key, **kw: f"{key}({lang})")
    return ReferralService(settings, subscription_service, bot, i18n), bot


class SkipPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_inviter_returns_empty_payload(self):
        settings = _make_settings()
        subscription_service = AsyncMock()
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)
        # Referred_by_id is None → bail out immediately.
        with patch(
            "bot.services.referral_service.user_dal.get_user_by_id",
            AsyncMock(return_value=_make_user(42, referred_by_id=None)),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=1,
            )
        self.assertEqual(
            result,
            {"referee_bonus_applied_days": None, "referee_new_end_date": None},
        )
        subscription_service.extend_active_subscription_days.assert_not_called()

    async def test_referee_with_prior_successful_payment_is_skipped(self):
        # REFERRAL_ONE_BONUS_PER_REFEREE protects against duplicate awarding
        # when the same referee buys multiple subscriptions.
        settings = _make_settings(REFERRAL_ONE_BONUS_PER_REFEREE=True)
        subscription_service = AsyncMock()
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)
        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
            patch(
                "bot.services.referral_service.payment_dal.count_user_succeeded_payments",
                AsyncMock(return_value=2),
            ),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=1,
                current_payment_db_id=99,
            )
        self.assertEqual(
            result,
            {"referee_bonus_applied_days": None, "referee_new_end_date": None},
        )
        subscription_service.extend_active_subscription_days.assert_not_called()

    async def test_referee_already_active_is_skipped_when_caller_asks(self):
        settings = _make_settings(REFERRAL_ONE_BONUS_PER_REFEREE=False)
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=True)
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)
        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=1,
                skip_if_active_before_payment=True,
            )
        self.assertEqual(
            result,
            {"referee_bonus_applied_days": None, "referee_new_end_date": None},
        )
        subscription_service.extend_active_subscription_days.assert_not_called()


class InviterBonusTests(unittest.IsolatedAsyncioTestCase):
    """The inviter bonus has two sub-paths: extend their active sub or create
    a fresh bonus sub when they had none. Pin both."""

    async def test_extends_inviter_active_subscription(self):
        settings = _make_settings(REFERRAL_ONE_BONUS_PER_REFEREE=False)
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=False)
        # _get_or_create_panel_user_link_details returns (uuid, sub_link_id, short, created)
        subscription_service._get_or_create_panel_user_link_details = AsyncMock(
            return_value=("inviter-panel", "inviter-sub", "short", False)
        )
        new_end = datetime(2026, 1, 1, tzinfo=timezone.utc)
        subscription_service.extend_active_subscription_days = AsyncMock(return_value=new_end)
        service, bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
            patch(
                "bot.services.referral_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=10)),
            ),
            patch("bot.services.referral_service.events.emit", AsyncMock()) as emit_event,
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=1,
                skip_if_active_before_payment=False,
            )

        self.assertTrue(result["inviter_bonus_applied_flag"])
        # Inviter extension call must use the configured 1-month inviter bonus (7 days here).
        subscription_service.extend_active_subscription_days.assert_any_await(
            session=unittest.mock.ANY,
            user_id=1,
            bonus_days=7,
            reason=unittest.mock.ANY,
        )
        bot.send_message.assert_not_awaited()
        emit_event.assert_not_awaited()
        payload = result["event_payload"]
        self.assertEqual(payload["inviter_user_id"], 1)
        self.assertEqual(payload["inviter_bonus_days"], 7)
        self.assertEqual(payload["inviter_bonus_end_date"], new_end.isoformat())
        self.assertEqual(payload["inviter_bonus_kind"], "extended")
        self.assertEqual(payload["purchased_subscription_months"], 1)
        self.assertIsNone(payload["tariff_key"])
        self.assertFalse(payload["one_bonus_per_referee"])

    async def test_creates_new_bonus_sub_when_inviter_has_no_active_sub(self):
        settings = _make_settings(REFERRAL_ONE_BONUS_PER_REFEREE=False)
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=False)
        subscription_service._get_or_create_panel_user_link_details = AsyncMock(
            return_value=("inviter-panel", "inviter-sub", "short", False)
        )
        # Inviter has no active sub → extend returns None for inviter.
        # extend_active_subscription_days is called twice (inviter + referee). Use a side_effect:
        # First call (inviter) → None, second call (referee) → new datetime.
        inviter_new_end = datetime(2026, 1, 10, tzinfo=timezone.utc)
        referee_new_end = datetime(2026, 2, 1, tzinfo=timezone.utc)
        subscription_service.extend_active_subscription_days = AsyncMock(
            side_effect=[inviter_new_end, referee_new_end]
        )

        service, bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
            patch(
                "bot.services.referral_service.subscription_dal.deactivate_other_active_subscriptions",
                AsyncMock(),
            ) as deactivate_other,
            patch(
                "bot.services.referral_service.subscription_dal.upsert_subscription",
                AsyncMock(return_value=SimpleNamespace(subscription_id=999)),
            ) as upsert,
            patch(
                "bot.services.referral_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=None),
            ),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=1,
                skip_if_active_before_payment=False,
            )

        self.assertTrue(result["inviter_bonus_applied_flag"])
        upsert.assert_not_awaited()
        deactivate_other.assert_not_awaited()
        event_payload = result["event_payload"]
        self.assertEqual(event_payload["inviter_bonus_kind"], "new_sub")
        self.assertEqual(event_payload["inviter_bonus_end_date"], inviter_new_end.isoformat())

    async def test_inviter_extension_failure_does_not_fallback_to_manual_upsert(self):
        settings = _make_settings(REFERRAL_ONE_BONUS_PER_REFEREE=False)
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=False)
        subscription_service._get_or_create_panel_user_link_details = AsyncMock(
            return_value=("inviter-panel", "inviter-sub", "short", False)
        )
        referee_new_end = datetime(2026, 2, 1, tzinfo=timezone.utc)
        subscription_service.extend_active_subscription_days = AsyncMock(
            side_effect=[None, referee_new_end]
        )
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
            patch(
                "bot.services.referral_service.subscription_dal.upsert_subscription",
                AsyncMock(),
            ) as upsert,
            patch(
                "bot.services.referral_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=10)),
            ),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=1,
                skip_if_active_before_payment=False,
            )

        self.assertFalse(result["inviter_bonus_applied_flag"])
        self.assertEqual(result["referee_bonus_applied_days"], 3)
        upsert.assert_not_awaited()


class RefereeBonusTests(unittest.IsolatedAsyncioTestCase):
    async def test_applies_referee_bonus_via_extend_active_subscription(self):
        settings = _make_settings(REFERRAL_ONE_BONUS_PER_REFEREE=False)
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=False)
        # Inviter bonus is 0 for this test (skip inviter branch), referee gets 10 days.
        subscription_service._get_or_create_panel_user_link_details = AsyncMock(
            return_value=("inviter-panel", "inviter-sub", "short", False)
        )
        referee_new_end = datetime(2026, 3, 1, tzinfo=timezone.utc)
        subscription_service.extend_active_subscription_days = AsyncMock(
            return_value=referee_new_end
        )
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
            patch(
                "bot.services.referral_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=10)),
            ),
        ):
            # 3-month plan → 10-day referee bonus, 21-day inviter bonus.
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=3,
                skip_if_active_before_payment=False,
            )

        self.assertEqual(result["referee_bonus_applied_days"], 10)
        self.assertEqual(result["referee_new_end_date"], referee_new_end)
        # Referee extension call:
        referee_call = [
            call
            for call in subscription_service.extend_active_subscription_days.await_args_list
            if call.kwargs.get("user_id") == 42
        ]
        self.assertTrue(referee_call, "referee bonus extension must be invoked")
        self.assertEqual(referee_call[0].kwargs["bonus_days"], 10)

    async def test_no_referee_bonus_when_extend_returns_none(self):
        settings = _make_settings(
            REFERRAL_ONE_BONUS_PER_REFEREE=False,
            # Skip the inviter branch entirely.
            referral_bonus_inviter={},
            referral_bonus_referee={1: 3},
        )
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=False)
        subscription_service.extend_active_subscription_days = AsyncMock(return_value=None)
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
            patch(
                "bot.services.referral_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=10)),
            ),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=1,
                skip_if_active_before_payment=False,
            )

        self.assertIsNone(result["referee_bonus_applied_days"])
        self.assertIsNone(result["referee_new_end_date"])

    async def test_no_bonus_for_months_without_configured_value(self):
        # 24-month plan has no entries in either bonus dict → nothing applies.
        settings = _make_settings(REFERRAL_ONE_BONUS_PER_REFEREE=False)
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=False)
        subscription_service.extend_active_subscription_days = AsyncMock()
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with patch(
            "bot.services.referral_service.user_dal.get_user_by_id",
            AsyncMock(
                side_effect=lambda session, uid: (
                    _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                )
            ),
        ), patch(
            "bot.services.referral_service.subscription_dal.get_active_subscription_by_user_id",
            AsyncMock(return_value=None),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=24,
                skip_if_active_before_payment=False,
            )

        self.assertIsNone(result["referee_bonus_applied_days"])
        self.assertFalse(result["inviter_bonus_applied_flag"])
        subscription_service.extend_active_subscription_days.assert_not_called()

    async def test_tariff_bonus_uses_referee_purchase_tariff(self):
        data = {
            "default_tariff": "standard",
            "tariffs": [
                {
                    "key": "standard",
                    "names": {"en": "Standard"},
                    "descriptions": {},
                    "squad_uuids": ["standard-squad"],
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "prices_rub": {"2": 400},
                    "prices_stars": {},
                    "enabled_periods": [2],
                    "referral_bonus_days_inviter": {"2": 5},
                    "referral_bonus_days_referee": {"2": 1},
                    "enabled": True,
                },
                {
                    "key": "premium",
                    "names": {"en": "Premium"},
                    "descriptions": {},
                    "squad_uuids": ["premium-squad"],
                    "billing_model": "period",
                    "monthly_gb": 500,
                    "prices_rub": {"2": 700},
                    "prices_stars": {},
                    "enabled_periods": [2],
                    "referral_bonus_days_inviter": {"2": 20},
                    "referral_bonus_days_referee": {"2": 7},
                    "enabled": True,
                },
            ],
        }
        settings = _make_settings(
            REFERRAL_ONE_BONUS_PER_REFEREE=False,
            tariffs_config=TariffsConfig.model_validate(data),
        )
        subscription_service = AsyncMock()
        subscription_service.has_active_subscription = AsyncMock(return_value=False)
        subscription_service._get_or_create_panel_user_link_details = AsyncMock(
            return_value=("inviter-panel", "inviter-sub", "short", False)
        )
        inviter_new_end = datetime(2026, 4, 1, tzinfo=timezone.utc)
        referee_new_end = datetime(2026, 5, 1, tzinfo=timezone.utc)
        subscription_service.extend_active_subscription_days = AsyncMock(
            side_effect=[inviter_new_end, referee_new_end]
        )
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(
                    side_effect=lambda session, uid: (
                        _make_user(uid, referred_by_id=1) if uid == 42 else _make_user(uid)
                    )
                ),
            ),
            patch(
                "bot.services.referral_service.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=None),
            ),
        ):
            result = await service.apply_referral_bonuses_for_payment(
                session=AsyncMock(),
                referee_user_id=42,
                purchased_subscription_months=2,
                skip_if_active_before_payment=False,
                tariff_key="premium",
            )

        self.assertEqual(result["referee_bonus_applied_days"], 7)
        self.assertTrue(result["inviter_bonus_applied_flag"])
        inviter_call = [
            call
            for call in subscription_service.extend_active_subscription_days.await_args_list
            if call.kwargs.get("user_id") == 1
        ][0]
        referee_call = [
            call
            for call in subscription_service.extend_active_subscription_days.await_args_list
            if call.kwargs.get("user_id") == 42
        ][0]
        self.assertEqual(inviter_call.kwargs["bonus_days"], 20)
        self.assertEqual(referee_call.kwargs["bonus_days"], 7)


class GenerateReferralLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_includes_bot_username_and_referral_code(self):
        settings = _make_settings()
        subscription_service = AsyncMock()
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(return_value=_make_user(1)),
            ),
            patch(
                "bot.services.referral_service.user_dal.ensure_referral_code",
                AsyncMock(return_value="abc123"),
            ),
        ):
            link = await service.generate_referral_link(
                session=AsyncMock(),
                bot_username="my_bot",
                inviter_user_id=1,
            )
        self.assertEqual(link, "https://t.me/my_bot?start=ref_uabc123")

    async def test_returns_none_when_user_missing(self):
        settings = _make_settings()
        subscription_service = AsyncMock()
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with patch(
            "bot.services.referral_service.user_dal.get_user_by_id",
            AsyncMock(return_value=None),
        ):
            link = await service.generate_referral_link(
                session=AsyncMock(),
                bot_username="my_bot",
                inviter_user_id=999,
            )
        self.assertIsNone(link)

    async def test_returns_none_when_referral_code_unavailable(self):
        settings = _make_settings()
        subscription_service = AsyncMock()
        service, _bot = _make_service(settings=settings, subscription_service=subscription_service)

        with (
            patch(
                "bot.services.referral_service.user_dal.get_user_by_id",
                AsyncMock(return_value=_make_user(1)),
            ),
            patch(
                "bot.services.referral_service.user_dal.ensure_referral_code",
                AsyncMock(return_value=None),
            ),
        ):
            link = await service.generate_referral_link(
                session=AsyncMock(),
                bot_username="my_bot",
                inviter_user_id=1,
            )
        self.assertIsNone(link)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
