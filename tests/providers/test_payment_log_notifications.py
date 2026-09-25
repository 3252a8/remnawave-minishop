from types import SimpleNamespace
from typing import ClassVar
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from bot.infra.payment_events import PaymentPurchase
from bot.services.notification_service import NotificationService


class _I18n:
    messages: ClassVar[dict[str, str]] = {
        "log_open_profile_link": "Profile",
        "log_payment_received": (
            "{provider_emoji} Payment Received\n"
            "User: {user_display}\n"
            "Amount: {amount} {currency}\n"
            "Period: {months} mo.\n"
            "Provider: {payment_provider}\n"
            "Time: {timestamp}"
        ),
        "log_balance_topup_received": (
            "{provider_emoji} User balance topped up\n"
            "User: {user_display}\n"
            "Credited: {amount} {currency}\n"
            "Provider: {payment_provider}\n"
            "Payment ID: {payment_id}\n"
            "Time: {timestamp}"
        ),
        "log_payment_received_traffic": (
            "{provider_emoji} Payment Received (traffic top-up)\n"
            "User: {user_display}\n"
            "Amount: {amount} {currency}\n"
            "Purchase: {traffic_summary}\n"
            "{tariff_line}"
            "Provider: {payment_provider}\n"
            "Time: {timestamp}"
        ),
        "log_payment_received_with_purchases": (
            "{provider_emoji} Payment Received\n"
            "User: {user_display}\n"
            "Amount: {amount} {currency}\n"
            "{period_line}"
            "{purchase_summary_line}"
            "{tariff_line}"
            "Provider: {payment_provider}\n"
            "Time: {timestamp}"
        ),
        "log_payment_period_line": "Period: {months} mo.\n",
        "log_payment_purchase_summary_line": "Purchase: {summary}\n",
        "log_payment_traffic_purchase_line": "{gb} GB - {kind}",
        "log_payment_traffic_kind_regular": "regular traffic",
        "log_payment_traffic_kind_premium": "premium traffic",
        "log_payment_hwid_devices_purchase_line": "+{count} HWID devices",
        "log_payment_generic_purchase_line": "{amount} {unit} - {kind}",
        "log_payment_tariff_line": "Plan: {name}\n",
        "log_payment_promo_code_line": "Promo code: {promo_code}",
        "log_payment_discount_line": "Discount: {discount_amount} {currency}",
    }

    def gettext(self, _language, key, **kwargs):
        return self.messages.get(key, key).format(**kwargs)


def _service() -> NotificationService:
    service = NotificationService(
        bot=SimpleNamespace(send_message=AsyncMock()),
        settings=SimpleNamespace(
            LOG_PAYMENTS=True,
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY="RUB",
        ),
        i18n=_I18n(),
    )
    service._send_to_log_channel = AsyncMock()
    return service


class PaymentLogNotificationTests(IsolatedAsyncioTestCase):
    async def test_wata_payment_log_uses_public_account_id(self):
        service = _service()
        public_id = "ms_" + "a" * 32

        await service.notify_payment_received(
            user_id=1000000000000,
            minishop_id=public_id,
            amount=190,
            currency="RUB",
            months=1,
            payment_provider="wata",
            email="user@example.test",
        )

        message = service._send_to_log_channel.await_args.args[0]
        self.assertIn(f"ID {public_id}", message)
        self.assertNotIn("1000000000000", message)
        self.assertIn("190 RUB", message)

    async def test_payment_log_includes_promo_code_and_actual_discount(self):
        service = _service()

        await service.notify_payment_received(
            user_id=42,
            amount=72,
            currency="RUB",
            months=1,
            payment_provider="yookassa",
            username="alice",
            promo_code="AGATA<&",
            discount_amount=28,
        )

        message = service._send_to_log_channel.await_args.args[0]
        self.assertIn("Promo code: AGATA&lt;&amp;", message)
        self.assertIn("Discount: 28 RUB", message)

    async def test_balance_topup_log_names_the_flow_and_payment(self):
        service = _service()

        await service.notify_payment_received(
            user_id=42,
            amount=750,
            currency="RUB",
            months=0,
            payment_provider="yookassa",
            username="alice",
            sale_mode="balance_topup",
            payment_id=91,
        )

        message = service._send_to_log_channel.await_args.args[0]
        self.assertIn("User balance topped up", message)
        self.assertIn("alice", message)
        self.assertIn("750 RUB", message)
        self.assertIn("yookassa", message)
        self.assertIn("Payment ID: 91", message)
        self.assertNotIn("Period: 0 mo.", message)

    async def test_hwid_only_log_uses_devices_instead_of_zero_month_period(self):
        service = _service()

        await service.notify_payment_received(
            user_id=42,
            amount=80,
            currency="RUB",
            months=0,
            payment_provider="yookassa",
            username="alice",
            purchased_hwid_devices=2,
            tariff_key="standard",
        )

        message = service._send_to_log_channel.await_args.args[0]
        self.assertIn("+2 HWID devices", message)
        self.assertIn("Plan: standard", message)
        self.assertNotIn("Period: 0 mo.", message)

    async def test_subscription_hwid_log_includes_period_and_devices(self):
        service = _service()

        await service.notify_payment_received(
            user_id=42,
            amount=180,
            currency="RUB",
            months=1,
            payment_provider="wata",
            username="alice",
            purchased_hwid_devices=1,
            tariff_key="standard",
        )

        message = service._send_to_log_channel.await_args.args[0]
        self.assertIn("Period: 1 mo.", message)
        self.assertIn("+1 HWID devices", message)

    async def test_traffic_log_can_include_hwid_devices(self):
        service = _service()

        await service.notify_payment_received(
            user_id=42,
            amount=220,
            currency="RUB",
            months=0,
            payment_provider="wata",
            username="alice",
            traffic_gb=10,
            purchased_hwid_devices=2,
            tariff_key="standard",
        )

        message = service._send_to_log_channel.await_args.args[0]
        self.assertIn("10 GB - regular traffic", message)
        self.assertIn("+2 HWID devices", message)

    async def test_generic_purchase_log_supports_plugin_units(self):
        service = _service()

        await service.notify_payment_received(
            user_id=42,
            amount=50,
            currency="RUB",
            months=1,
            payment_provider="plugin",
            username="alice",
            tariff_key="standard",
            purchases=(PaymentPurchase(kind="extra_seats", amount=3, unit="seat"),),
        )

        message = service._send_to_log_channel.await_args.args[0]
        self.assertIn("3 seat - extra_seats", message)
        self.assertIn("Period: 1 mo.", message)
