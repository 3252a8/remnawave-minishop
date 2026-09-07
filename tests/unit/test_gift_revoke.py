from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.gift_revoke import GiftRevokeError, revoke_paid_gift
from db.gift_models import SubscriptionGift
from db.models import Payment


class GiftRevokeTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.gift = SubscriptionGift(
            gift_id=8,
            payment_id=77,
            purchaser_id=10,
            token="R" * 43,
            status="ready",
        )
        self.payment = Payment(
            payment_id=77,
            user_id=10,
            status="succeeded",
            amount=100,
            checkout_total_amount=123.45,
            currency="USD",
        )
        self.session = AsyncMock()
        self.session.get.return_value = self.gift
        self.credit = AsyncMock(return_value=SimpleNamespace(entry_id=1))
        self.update_status = AsyncMock(return_value=self.payment)
        for name, mock in (
            ("payment_dal.get_payment_by_db_id_for_update", AsyncMock(return_value=self.payment)),
            ("gift_dal.by_payment", AsyncMock(return_value=self.gift)),
            ("payment_dal.update_payment_status_by_db_id", self.update_status),
            ("UserBalanceService.credit_gift_refund", self.credit),
            ("promo_code_dal.release_promo_activation", AsyncMock(return_value=True)),
        ):
            patcher = patch(f"bot.services.gift_revoke.{name}", mock)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def revoke(self, **changes: object) -> SubscriptionGift:
        refund_to_balance = bool(changes.pop("refund_to_balance", True))
        reason = str(changes.pop("reason", " duplicate purchase "))
        return await revoke_paid_gift(
            self.session,
            gift_id=8,
            actor_admin_id=99,
            reason=reason,
            restore_promo_usage=True,
            refund_to_balance=refund_to_balance,
            **changes,
        )

    async def test_refunds_checkout_total_with_actor_reason_and_currency_scale(self) -> None:
        result = await self.revoke()

        self.assertIs(result, self.gift)
        self.assertEqual(self.gift.status, "revoked")
        self.assertEqual(self.payment.reversed_by_admin_id, 99)
        self.assertEqual(self.payment.reversal_note, "duplicate purchase")
        self.credit.assert_awaited_once_with(
            self.session,
            gift_id=8,
            purchaser_id=10,
            amount=123.45,
            currency="USD",
            actor_admin_id=99,
            reason="duplicate purchase",
        )
        self.session.flush.assert_awaited_once()

    async def test_revocation_marks_payment_reversed(self) -> None:
        await self.revoke()

        self.update_status.assert_awaited_once_with(self.session, 77, "reversed")

    async def test_falls_back_to_payment_amount_and_does_not_require_enabled_balance(self) -> None:
        self.payment.checkout_total_amount = None
        await self.revoke()

        credit_call = self.credit.await_args
        self.assertIsNotNone(credit_call)
        assert credit_call is not None
        self.assertEqual(credit_call.kwargs["amount"], 100)

    async def test_replay_does_not_credit_a_revoked_gift_twice(self) -> None:
        self.gift.status = "revoked"
        self.payment.status = "reversed"
        await self.revoke()

        self.credit.assert_not_awaited()
        self.session.flush.assert_not_awaited()

    async def test_legacy_revoked_gift_finishes_the_payment_reversal_without_crediting_again(
        self,
    ) -> None:
        self.gift.status = "revoked"
        await self.revoke()

        self.credit.assert_not_awaited()
        self.assertEqual(self.payment.reversed_by_admin_id, 99)
        self.update_status.assert_awaited_once_with(self.session, 77, "reversed")

    async def test_activation_or_completed_gifts_are_rejected_under_the_lock(self) -> None:
        for status in ("activating", "activated"):
            with self.subTest(status=status):
                self.gift.status = status
                with self.assertRaisesRegex(GiftRevokeError, "gift_revoke_unavailable"):
                    await self.revoke()
                self.gift.status = "ready"

    async def test_refund_can_be_explicitly_skipped(self) -> None:
        await self.revoke(refund_to_balance=False)

        self.credit.assert_not_awaited()

    async def test_revocation_without_reason_records_an_empty_reason(self) -> None:
        await self.revoke(reason="   ", without_reason=True)

        self.assertEqual(self.payment.reversal_note, "")
        credit_call = self.credit.await_args
        self.assertIsNotNone(credit_call)
        assert credit_call is not None
        self.assertEqual(credit_call.kwargs["reason"], "")

    async def test_revocation_requires_a_reason_without_the_explicit_flag(self) -> None:
        with self.assertRaisesRegex(GiftRevokeError, "invalid_gift_revoke_reason"):
            await self.revoke(reason="   ")
