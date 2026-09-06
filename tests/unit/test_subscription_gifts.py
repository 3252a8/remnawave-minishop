import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp.billing_checkout_bundle import CheckoutBundle
from bot.app.web.webapp.gift_checkout import attach_gift_delivery
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from bot.services import subscription_gifts
from bot.services.payment_fulfillment import PaymentFulfillmentError, reverse_payment_fulfillment
from bot.services.subscription_order_terms import freeze_subscription_terms, paid_period_end
from config.tariffs_config import TariffsConfig
from db.gift_models import SubscriptionGift
from db.models import Payment, Subscription, User


class SubscriptionGiftTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        catalog = TariffsConfig.model_validate(
            {
                "schema_version": 2,
                "period_unit": "day",
                "default_tariff": "base",
                "tariffs": [
                    {
                        "key": "base",
                        "billing_model": "period",
                        "period_unit": "day",
                        "monthly_gb": 100,
                        "enabled_periods": [7],
                        "prices_rub": {"7": 100},
                    }
                ],
            }
        )
        self.settings = SimpleNamespace(
            tariffs_config=catalog, USER_HWID_DEVICE_LIMIT=3, USER_TRAFFIC_STRATEGY="NO_RESET"
        )
        self.payment = Payment(
            payment_id=77,
            user_id=10,
            status="succeeded",
            sale_mode="subscription@base|d7|gift",
            tariff_key="base",
            amount=100,
            subscription_duration_days=7,
            subscription_duration_months=0,
            subscription_terms_snapshot=freeze_subscription_terms(
                self.settings, "subscription@base|d7|gift"
            ),
        )
        self.gift = SubscriptionGift(
            gift_id=8, payment_id=77, purchaser_id=10, token="R" * 43, status="ready"
        )
        self.session = AsyncMock()
        self.service = AsyncMock()
        self.service.settings = self.settings
        self.service._subscription_billing_model = lambda _: "period"
        self.service.activate_subscription.side_effect = self.activate
        self.active = AsyncMock(return_value=None)
        self.pending = AsyncMock(return_value=None)
        for name, mock in (
            ("gift_dal.by_token", AsyncMock(return_value=self.gift)),
            ("gift_dal.by_payment", AsyncMock(return_value=self.gift)),
            ("gift_dal.activating_for_user", self.pending),
            ("payment_dal.get_payment_by_db_id_for_update", AsyncMock(return_value=self.payment)),
            ("user_dal.lock_user_by_id", AsyncMock(return_value=User(user_id=20, is_banned=False))),
            ("subscription_dal.get_active_subscription_by_user_id_for_update", self.active),
            ("message_log_dal.create_message_log_no_commit", AsyncMock()),
        ):
            patcher = patch(f"bot.services.subscription_gifts.{name}", mock)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def activate(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.assertEqual(self.gift.status, "activating")
        self.assertEqual(self.gift.recipient_id, 20)
        self.assertGreaterEqual(self.session.commit.await_count, 1)
        return {"end_date": kwargs["authoritative_end_at"]}

    async def claim(self, user_id: int = 20) -> SubscriptionGift:
        return await subscription_gifts.claim_gift(
            self.session, token=self.gift.token, user_id=user_id, service=self.service
        )

    async def test_reserves_before_panel_and_replays_without_extending_again(self) -> None:
        await self.claim()
        end = self.gift.activation_end_at
        self.assertEqual(self.gift.status, "activated")
        await self.claim()
        self.assertEqual(self.gift.activation_end_at, end)
        self.service.activate_subscription.assert_awaited_once()
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_used"):
            await self.claim(30)
        self.service.activate_subscription.assert_awaited_once()

    async def test_buyer_and_revoked_payment_cannot_claim(self) -> None:
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_own"):
            await self.claim(10)
        self.payment.status = "reversed"
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_unavailable"):
            await self.claim()
        self.service.activate_subscription.assert_not_awaited()

    async def test_rechecks_payment_after_recipient_reservation_commit(self) -> None:
        async def reverse_during_commit() -> None:
            self.payment.status = "reversed"

        self.session.commit.side_effect = reverse_during_commit
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_unavailable"):
            await self.claim()
        self.service.activate_subscription.assert_not_awaited()

    async def test_panel_failure_keeps_recipient_and_absolute_period_for_retry(self) -> None:
        self.service.activate_subscription.side_effect = None
        self.service.activate_subscription.return_value = None
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_activation_retry"):
            await self.claim()
        end = self.gift.activation_end_at
        self.assertEqual(self.gift.status, "activating")
        self.assertEqual(self.gift.recipient_id, 20)
        self.session.rollback.assert_awaited_once()
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_used"):
            await self.claim(30)
        self.service.activate_subscription.side_effect = self.activate
        await self.claim()
        self.assertEqual(self.gift.activation_end_at, end)
        self.assertEqual(self.gift.status, "activated")

    async def test_second_pending_gift_prevents_overlapping_activation(self) -> None:
        self.pending.return_value = SubscriptionGift(
            gift_id=9, status="activating", recipient_id=20
        )
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_other_activation_pending"):
            await self.claim()
        self.service.activate_subscription.assert_not_awaited()

    async def test_changed_tariff_cannot_replace_existing_paid_entitlements(self) -> None:
        self.active.return_value = Subscription(
            provider="manual", tariff_key="base", auto_renew_enabled=False, hwid_device_limit=3
        )
        self.settings.tariffs_config.tariffs[0].monthly_gb = 200
        with self.assertRaisesRegex(subscription_gifts.GiftError, "gift_tariff_conflict"):
            await self.claim()
        self.service.activate_subscription.assert_not_awaited()
        self.active.return_value = None
        self.settings.tariffs_config.tariffs.clear()
        await self.claim()
        self.service.activate_subscription.assert_awaited_once()

    async def test_trial_policy_is_frozen_independently_of_buyer_subscription(self) -> None:
        for strategy in ("add_remaining", "start_from_payment"):
            with self.subTest(strategy=strategy):
                self.gift.status = "ready"
                self.gift.recipient_id = None
                before = datetime.now(UTC)
                trial_end = before + timedelta(days=3)
                self.active.return_value = Subscription(provider="trial", end_date=trial_end)
                bundle = attach_gift_delivery(
                    CheckoutBundle(),
                    WebAppPaymentCreatePayload.model_validate(
                        {"method": "yookassa", "months": 1, "gift": True}
                    ),
                    "add_remaining" if strategy == "add_remaining" else "start_from_payment",
                )
                self.payment.checkout_bundle_snapshot = bundle.snapshot
                assert bundle.snapshot is not None
                self.assertEqual(json.loads(bundle.snapshot)["trial_days_strategy"], strategy)
                await self.claim()
                if strategy == "add_remaining":
                    self.assertEqual(self.gift.activation_end_at, trial_end + timedelta(days=7))
                else:
                    self.assertGreaterEqual(self.gift.activation_end_at, before + timedelta(days=7))
                    self.assertLessEqual(
                        self.gift.activation_end_at, datetime.now(UTC) + timedelta(days=7)
                    )

    async def test_reversal_revokes_unused_gift_without_changing_subscription(self) -> None:
        with patch(
            "bot.services.payment_fulfillment.payment_dal.update_payment_status_by_db_id",
            AsyncMock(),
        ) as update:
            await reverse_payment_fulfillment(
                self.session,
                payment_id=77,
                actor_admin_id=1,
                reason="Refund",
                restore_promo_usage=False,
                subscription_service=self.service,
            )
        self.assertEqual(self.gift.status, "revoked")
        update.assert_awaited_once_with(self.session, 77, "reversed")
        self.service.activate_subscription.assert_not_awaited()
        for status in ("activating", "activated"):
            self.gift.status = status
            with self.assertRaisesRegex(PaymentFulfillmentError, "claimed gift"):
                await reverse_payment_fulfillment(
                    self.session,
                    payment_id=77,
                    actor_admin_id=1,
                    reason="Refund",
                    restore_promo_usage=False,
                    subscription_service=self.service,
                )

    def test_authoritative_paid_period_keeps_independent_promo_days(self) -> None:
        start = datetime(2026, 9, 1, tzinfo=UTC)
        provider_end = start + timedelta(days=30)
        self.assertEqual(paid_period_end(start, 37, provider_end, 7), start + timedelta(days=37))
