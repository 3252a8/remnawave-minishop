from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from db.dal import payment_dal


class PaymentDalStatusUpdateTests(IsolatedAsyncioTestCase):
    async def test_update_payment_status_preserves_succeeded_payment(self):
        session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
        payment = SimpleNamespace(
            payment_id=1,
            status="succeeded",
            yookassa_payment_id=None,
        )

        with patch.object(
            payment_dal,
            "get_payment_by_db_id",
            AsyncMock(return_value=payment),
        ):
            result = await payment_dal.update_payment_status_by_db_id(
                session,
                1,
                "canceled",
                yk_payment_id="yk-1",
            )

        self.assertIs(result, payment)
        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.yookassa_payment_id, "yk-1")
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(payment)

    async def test_provider_status_update_preserves_succeeded_payment(self):
        session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
        payment = SimpleNamespace(
            payment_id=2,
            status="succeeded",
            provider_payment_id=None,
            provider_payment_url=None,
        )

        with patch.object(
            payment_dal,
            "get_payment_by_db_id",
            AsyncMock(return_value=payment),
        ):
            result = await payment_dal.update_provider_payment_and_status(
                session,
                2,
                "provider-2",
                "failed",
                provider_payment_url="https://pay.example/2",
            )

        self.assertIs(result, payment)
        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.provider_payment_id, "provider-2")
        self.assertEqual(payment.provider_payment_url, "https://pay.example/2")
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(payment)

    async def test_provider_status_update_keeps_pending_payment_mutable(self):
        session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
        payment = SimpleNamespace(
            payment_id=3,
            status="pending_platega",
            provider_payment_id=None,
            provider_payment_url=None,
        )

        with patch.object(
            payment_dal,
            "get_payment_by_db_id",
            AsyncMock(return_value=payment),
        ):
            result = await payment_dal.update_provider_payment_and_status(
                session,
                3,
                "provider-3",
                "failed",
            )

        self.assertIs(result, payment)
        self.assertEqual(payment.status, "failed")
        self.assertEqual(payment.provider_payment_id, "provider-3")
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(payment)
