import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers.shared import RecurringChargeContext
from bot.payment_providers.yookassa import YooKassaConfig, YooKassaService
from bot.payment_providers.yookassa import service as yookassa_service


def _service(*, autopayments_enabled: bool = True, response=None):
    service = object.__new__(YooKassaService)
    service.settings = SimpleNamespace()
    service.config = YooKassaConfig(
        SHOP_ID="shop-id",
        SECRET_KEY="secret-key",
        RETURN_URL="https://shop.example/return",
        DEFAULT_RECEIPT_EMAIL="receipt@example.test",
        AUTOPAYMENTS_ENABLED=autopayments_enabled,
    )
    service._sdk_configured_for = ("shop-id", "secret-key")
    service._configured_return_url_override = None
    service._bot_username_for_default_return = None
    service.subscription_service = None
    service.create_payment = AsyncMock(
        return_value=response or {"id": "yk-auto-1", "status": "pending"}
    )
    return service


def _context(
    saved_method_id: str = "pm-yookassa-1",
    *,
    session=None,
    idempotence_key: str | None = "yk-auto-cycle-7",
):
    return RecurringChargeContext(
        session=session or AsyncMock(),
        user_id=42,
        subscription_id=7,
        saved_method=SimpleNamespace(provider_payment_method_id=saved_method_id),
        amount=199.0,
        currency="RUB",
        months=1,
        sale_mode="subscription@standard",
        description="Auto-renewal for 1 months",
        metadata={
            "user_id": "42",
            "auto_renew_for_subscription_id": "7",
            "subscription_months": "1",
            "sale_mode": "subscription@standard",
        },
        idempotence_key=idempotence_key,
    )


class YooKassaRecurringProviderTests(IsolatedAsyncioTestCase):
    async def test_saved_method_charge_uses_shared_recurring_context(self):
        service = _service(response={"id": "yk-auto-7", "status": "waiting_for_capture"})
        session = AsyncMock()
        payment = SimpleNamespace(
            payment_id=17,
            status="pending_yookassa",
            yookassa_payment_id=None,
            provider_payment_id=None,
            created_at=datetime.now(UTC),
        )

        with (
            patch.object(
                yookassa_service.payment_dal,
                "create_or_get_payment_record_by_idempotence_key",
                AsyncMock(return_value=(payment, True)),
            ) as create_or_get_payment,
            patch.object(
                yookassa_service.payment_dal,
                "update_payment_status_by_db_id",
                AsyncMock(),
            ) as update_payment,
        ):
            result = await service.charge_saved_payment_method(_context(session=session))

        self.assertTrue(result.initiated)
        self.assertEqual(result.provider_payment_id, "yk-auto-7")
        self.assertEqual(result.status, "waiting_for_capture")
        local_payment = create_or_get_payment.await_args.args[1]
        self.assertEqual(local_payment["amount"], 199.0)
        self.assertEqual(local_payment["currency"], "RUB")
        self.assertEqual(local_payment["status"], "pending_yookassa")
        self.assertEqual(local_payment["provider"], "yookassa")
        self.assertEqual(local_payment["idempotence_key"], "yk-auto-cycle-7")
        service.create_payment.assert_awaited_once_with(
            amount=199.0,
            currency="RUB",
            description="Auto-renewal for 1 months",
            metadata={
                "user_id": "42",
                "auto_renew_for_subscription_id": "7",
                "subscription_months": "1",
                "sale_mode": "subscription@standard",
                "payment_db_id": "17",
            },
            payment_method_id="pm-yookassa-1",
            save_payment_method=False,
            capture=True,
            idempotence_key="yk-auto-cycle-7",
        )
        update_payment.assert_awaited_once_with(
            session,
            17,
            "pending_yookassa",
            "yk-auto-7",
        )
        self.assertEqual(session.commit.await_count, 2)

    async def test_duplicate_pending_charge_reuses_yookassa_idempotence_key(self):
        service = _service(response={"id": "yk-auto-7", "status": "pending"})
        session = AsyncMock()
        payment = SimpleNamespace(
            payment_id=17,
            status="pending_yookassa",
            yookassa_payment_id=None,
            provider_payment_id=None,
            created_at=datetime.now(UTC),
        )

        with (
            patch.object(
                yookassa_service.payment_dal,
                "create_or_get_payment_record_by_idempotence_key",
                AsyncMock(return_value=(payment, False)),
            ) as create_or_get_payment,
            patch.object(
                yookassa_service.payment_dal,
                "update_payment_status_by_db_id",
                AsyncMock(),
            ),
        ):
            first = await service.charge_saved_payment_method(
                _context(session=session, idempotence_key="yk-auto-cycle-stable")
            )
            second = await service.charge_saved_payment_method(
                _context(session=session, idempotence_key="yk-auto-cycle-stable")
            )

        self.assertTrue(first.initiated)
        self.assertTrue(second.initiated)
        self.assertEqual(create_or_get_payment.await_count, 2)
        self.assertEqual(service.create_payment.await_count, 2)
        keys = [call.kwargs["idempotence_key"] for call in service.create_payment.await_args_list]
        self.assertEqual(keys, ["yk-auto-cycle-stable", "yk-auto-cycle-stable"])

    async def test_known_pending_provider_payment_is_not_charged_again(self):
        service = _service()
        payment = SimpleNamespace(
            payment_id=17,
            status="pending_yookassa",
            yookassa_payment_id="yk-auto-7",
            provider_payment_id=None,
        )

        with patch.object(
            yookassa_service.payment_dal,
            "create_or_get_payment_record_by_idempotence_key",
            AsyncMock(return_value=(payment, False)),
        ):
            result = await service.charge_saved_payment_method(_context())

        self.assertTrue(result.initiated)
        self.assertEqual(result.provider_payment_id, "yk-auto-7")
        service.create_payment.assert_not_awaited()

    async def test_old_uncertain_payment_does_not_replay_after_idempotence_window(self):
        service = _service()
        payment = SimpleNamespace(
            payment_id=17,
            status="failed_metadata_error",
            yookassa_payment_id=None,
            provider_payment_id=None,
            created_at=datetime.now(UTC) - timedelta(hours=24, seconds=1),
        )

        with patch.object(
            yookassa_service.payment_dal,
            "create_or_get_payment_record_by_idempotence_key",
            AsyncMock(return_value=(payment, False)),
        ):
            result = await service.charge_saved_payment_method(_context())

        self.assertFalse(result.initiated)
        self.assertEqual(result.message, "idempotence_window_expired")
        service.create_payment.assert_not_awaited()

    async def test_saved_method_charge_stays_disabled_when_autopayments_are_off(self):
        service = _service(autopayments_enabled=False)

        result = await service.charge_saved_payment_method(_context())

        self.assertFalse(result.initiated)
        self.assertEqual(result.message, "recurring_inactive")
        service.create_payment.assert_not_awaited()

    async def test_saved_method_charge_rejects_missing_method_id(self):
        service = _service()

        result = await service.charge_saved_payment_method(_context(saved_method_id=""))

        self.assertFalse(result.initiated)
        self.assertEqual(result.message, "missing_saved_method")
        service.create_payment.assert_not_awaited()

    async def test_sdk_calls_are_bounded_by_timeout(self):
        service = _service()
        service._sdk_timeout_seconds = lambda: 0.01

        async def hanging_to_thread(*_args):
            await asyncio.sleep(60)

        with patch("bot.payment_providers.yookassa.service.asyncio.to_thread", hanging_to_thread):
            result = await service.get_payment_info("yk-timeout")

        self.assertIsNone(result)

    async def test_create_payment_uses_half_up_amount_for_invoice_and_receipt(self):
        class FakeBuilder:
            instance = None

            def __init__(self):
                type(self).instance = self
                self.amount = None
                self.receipt = None

            def set_amount(self, value):
                self.amount = value

            def set_capture(self, _value):
                pass

            def set_confirmation(self, _value):
                pass

            def set_description(self, _value):
                pass

            def set_metadata(self, _value):
                pass

            def set_save_payment_method(self, _value):
                pass

            def set_receipt(self, value):
                self.receipt = value

            def build(self):
                return {"amount": self.amount, "receipt": self.receipt}

        service = _service()
        del service.create_payment
        service._run_sdk_call = AsyncMock(
            return_value=SimpleNamespace(
                id="yk-half-up-1",
                confirmation=SimpleNamespace(confirmation_url="https://pay.example.test"),
                status="pending",
                paid=False,
                refundable=True,
                metadata={},
                created_at="now",
                description="Subscription",
                test=False,
                payment_method=None,
                amount=SimpleNamespace(value="1.13", currency="RUB"),
            )
        )

        with patch.object(yookassa_service, "PaymentRequestBuilder", FakeBuilder):
            response = await service.create_payment(
                amount=1.125,
                currency="RUB",
                description="Subscription",
                metadata={"user_id": "42"},
                idempotence_key="fixed-yookassa-key",
            )

        self.assertEqual(response["amount_value"], 1.13)
        self.assertEqual(response["idempotence_key_used"], "fixed-yookassa-key")
        self.assertEqual(service._run_sdk_call.await_args.args[3], "fixed-yookassa-key")
        self.assertEqual(FakeBuilder.instance.amount, {"value": "1.13", "currency": "RUB"})
        self.assertEqual(
            FakeBuilder.instance.receipt["items"][0]["amount"],
            {"value": "1.13", "currency": "RUB"},
        )
