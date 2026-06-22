from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from bot.payment_providers.shared import RecurringChargeContext
from bot.payment_providers.yookassa import YooKassaConfig, YooKassaService


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


def _context(saved_method_id: str = "pm-yookassa-1"):
    return RecurringChargeContext(
        session=SimpleNamespace(),
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
    )


class YooKassaRecurringProviderTests(IsolatedAsyncioTestCase):
    async def test_saved_method_charge_uses_shared_recurring_context(self):
        service = _service(response={"id": "yk-auto-7", "status": "waiting_for_capture"})

        result = await service.charge_saved_payment_method(_context())

        self.assertTrue(result.initiated)
        self.assertEqual(result.provider_payment_id, "yk-auto-7")
        self.assertEqual(result.status, "waiting_for_capture")
        service.create_payment.assert_awaited_once_with(
            amount=199.0,
            currency="RUB",
            description="Auto-renewal for 1 months",
            metadata={
                "user_id": "42",
                "auto_renew_for_subscription_id": "7",
                "subscription_months": "1",
                "sale_mode": "subscription@standard",
            },
            payment_method_id="pm-yookassa-1",
            save_payment_method=False,
            capture=True,
        )

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
