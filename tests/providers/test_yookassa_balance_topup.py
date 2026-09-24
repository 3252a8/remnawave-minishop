from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers.yookassa import success as yookassa_success


class YooKassaBalanceTopupTests(IsolatedAsyncioTestCase):
    async def test_balance_topup_uses_balance_finalizer_without_extending_subscription(
        self,
    ) -> None:
        await self._assert_independent_sale("balance_topup")

    async def test_extension_order_uses_frozen_identity_without_extending_subscription(
        self,
    ) -> None:
        await self._assert_independent_sale("extension|" + "a" * 32)

    async def _assert_independent_sale(self, sale_mode: str) -> None:
        payment = SimpleNamespace(
            payment_id=91,
            status="pending_yookassa",
            user_id=42,
            amount=55.0,
            currency="RUB",
            provider="yookassa",
            sale_mode=sale_mode,
            subscription_duration_months=1,
            purchased_gb=None,
            purchased_hwid_devices=None,
            entitlement_context_snapshot=None,
            promo_code_id=None,
            tariff_key=None,
        )
        payment_info = {
            "id": "yk-balance-topup",
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "55.00", "currency": "RUB"},
            "metadata": {
                "user_id": "42",
                "subscription_months": "1",
                "payment_db_id": "91",
                "sale_mode": "balance_topup",
            },
        }
        subscription_service = SimpleNamespace(activate_subscription=AsyncMock())
        finalizer = AsyncMock(return_value=SimpleNamespace())
        claim = AsyncMock()

        with (
            patch.object(
                yookassa_success.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(yookassa_success.payment_dal, "claim_payment_finalization", claim),
            patch.object(yookassa_success, "finalize_successful_payment", finalizer),
        ):
            result = await yookassa_success.process_successful_payment(
                AsyncMock(),
                AsyncMock(),
                payment_info,
                AsyncMock(),
                SimpleNamespace(traffic_sale_mode=False),
                AsyncMock(),
                subscription_service,
                AsyncMock(),
            )

        self.assertIsNone(result)
        finalizer.assert_awaited_once()
        finalizer_call = finalizer.await_args
        self.assertIsNotNone(finalizer_call)
        assert finalizer_call is not None
        request = finalizer_call.args[0]
        self.assertIs(request.payment, payment)
        self.assertEqual(request.sale_mode, sale_mode)
        self.assertEqual(request.amount, 55.0)
        self.assertEqual(request.currency, "RUB")
        self.assertEqual(request.provider_subscription, "yookassa")
        claim.assert_not_awaited()
        subscription_service.activate_subscription.assert_not_awaited()
