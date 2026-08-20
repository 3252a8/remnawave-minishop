from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.payment_fulfillment import (
    PaymentFulfillmentError,
    payment_action_state,
    persist_payment_fulfillment,
    reverse_payment_fulfillment,
)


def _payment(**overrides):
    data = {
        "payment_id": 77,
        "user_id": 42,
        "status": "failed",
        "sale_mode": "subscription",
        "provider_payment_id": "provider-77",
        "yookassa_payment_id": None,
        "promo_code_id": None,
        "fulfillment_before_snapshot": None,
        "fulfillment_after_snapshot": None,
        "fulfillment_source": None,
        "reversed_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class PaymentFulfillmentTests(IsolatedAsyncioTestCase):
    async def test_action_state_requires_confirmation_for_reused_promo(self):
        payment = _payment(promo_code_id=5)
        with patch(
            "bot.services.payment_fulfillment.promo_code_dal.get_user_activation_for_promo",
            AsyncMock(return_value=SimpleNamespace(payment_id=76)),
        ):
            state = await payment_action_state(AsyncMock(), payment)

        self.assertTrue(state["can_manual_finalize"])
        self.assertTrue(state["manual_finalize_requires_promo_confirmation"])
        self.assertIn("promo_used_by_another_payment", state["manual_finalize_warnings"])

    async def test_action_state_allows_reversal_only_with_snapshots(self):
        state = await payment_action_state(
            AsyncMock(),
            _payment(
                status="succeeded",
                fulfillment_before_snapshot='{"version": 1, "users": []}',
                fulfillment_after_snapshot='{"version": 1, "users": []}',
            ),
        )

        self.assertTrue(state["can_reverse"])
        self.assertFalse(state["can_manual_finalize"])

    def test_persist_fulfillment_records_auditable_snapshots(self):
        payment = _payment()

        persist_payment_fulfillment(
            payment,
            before={"version": 1, "users": []},
            after={"version": 1, "users": [{"user_id": 42}]},
        )

        self.assertEqual(payment.fulfillment_source, "provider")
        self.assertIsNotNone(payment.fulfilled_at)
        self.assertIn('"version": 1', payment.fulfillment_before_snapshot)
        self.assertIn('"user_id": 42', payment.fulfillment_after_snapshot)

    async def test_reversal_rejects_legacy_payment_without_snapshot(self):
        payment = _payment(status="succeeded")
        with (
            patch(
                "bot.services.payment_fulfillment.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            self.assertRaisesRegex(PaymentFulfillmentError, "predates reversible"),
        ):
            await reverse_payment_fulfillment(
                AsyncMock(),
                payment_id=77,
                actor_admin_id=1,
                reason="Provider refund",
                restore_promo_usage=True,
                subscription_service=AsyncMock(),
            )

    async def test_reversal_rejects_a_later_successful_payment(self):
        timestamp = datetime.now(UTC)
        payment = _payment(
            status="succeeded",
            fulfilled_at=timestamp,
            fulfillment_before_snapshot='{"version": 1, "users": []}',
            fulfillment_after_snapshot='{"version": 1, "users": []}',
        )
        session = AsyncMock()
        session.scalar.return_value = 88
        with (
            patch(
                "bot.services.payment_fulfillment.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            self.assertRaises(PaymentFulfillmentError) as raised,
        ):
            await reverse_payment_fulfillment(
                session,
                payment_id=77,
                actor_admin_id=1,
                reason="Provider refund",
                restore_promo_usage=True,
                subscription_service=AsyncMock(),
            )

        self.assertEqual(raised.exception.code, "payment_reversal_conflict")
        self.assertEqual(raised.exception.details, ["later_payment:88"])
