import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers import cryptopay, stars


class InvoiceProviderHwidMetadataTests(IsolatedAsyncioTestCase):
    async def test_cryptopay_subscription_hwid_quote_records_device_count(self):
        valid_from = datetime(2099, 2, 1, tzinfo=timezone.utc)
        valid_until = datetime(2099, 3, 1, tzinfo=timezone.utc)
        hwid_quote = {
            "device_count": 2,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "pricing_period_months": 1,
            "proration_ratio": 1.0,
            "full_price": 50.0,
        }
        payment = SimpleNamespace(payment_id=77)
        client = SimpleNamespace(
            create_invoice=AsyncMock(
                return_value=SimpleNamespace(
                    invoice_id=555,
                    status="active",
                    bot_invoice_url="https://cryptopay.example/invoice",
                )
            )
        )
        service = cryptopay.CryptoPayService.__new__(cryptopay.CryptoPayService)
        service.config = SimpleNamespace(
            ENABLED=True,
            TOKEN="token",
            NETWORK="testnet",
            CURRENCY_TYPE="fiat",
            ASSET="RUB",
        )
        service._client = client
        service._client_token = "token"
        service._client_network = "testnet"
        session = AsyncMock()

        with (
            patch.object(
                cryptopay.payment_dal,
                "create_payment_record",
                AsyncMock(return_value=payment),
            ) as create_record,
            patch.object(
                cryptopay.payment_dal,
                "update_provider_payment_and_status",
                AsyncMock(),
            ),
        ):
            url = await service.create_invoice(
                session=session,
                user_id=42,
                months=1,
                amount=150,
                description="Subscription",
                sale_mode="subscription@standard",
                hwid_quote=hwid_quote,
                currency="RUB",
            )

        assert url == "https://cryptopay.example/invoice"
        record_payload = create_record.await_args.args[1]
        assert record_payload["subscription_duration_months"] == 1
        assert record_payload["purchased_hwid_devices"] == 2
        assert record_payload["hwid_valid_from"] == valid_from
        assert record_payload["hwid_valid_until"] == valid_until
        provider_payload = json.loads(client.create_invoice.await_args.kwargs["payload"])
        assert provider_payload["subscription_months"] == "1"
        assert provider_payload["hwid_devices"] == 2

    async def test_stars_subscription_hwid_quote_records_device_count(self):
        valid_from = datetime(2099, 2, 1, tzinfo=timezone.utc)
        valid_until = datetime(2099, 3, 1, tzinfo=timezone.utc)
        hwid_quote = {
            "device_count": 1,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "pricing_period_months": 1,
            "proration_ratio": 1.0,
            "full_price": 50.0,
        }
        payment = SimpleNamespace(payment_id=88)
        bot = SimpleNamespace(send_invoice=AsyncMock())
        service = stars.StarsService(
            bot=bot,
            settings=SimpleNamespace(),
            i18n=SimpleNamespace(),
            subscription_service=SimpleNamespace(),
            referral_service=SimpleNamespace(),
        )
        session = AsyncMock()

        with patch.object(
            stars.payment_dal,
            "create_payment_record",
            AsyncMock(return_value=payment),
        ) as create_record:
            payment_id = await service.create_invoice(
                session=session,
                user_id=42,
                months=1,
                stars_price=150,
                description="Subscription",
                sale_mode="subscription@standard",
                hwid_quote=hwid_quote,
            )

        assert payment_id == 88
        record_payload = create_record.await_args.args[1]
        assert record_payload["subscription_duration_months"] == 1
        assert record_payload["purchased_hwid_devices"] == 1
        assert record_payload["hwid_valid_from"] == valid_from
        assert record_payload["hwid_valid_until"] == valid_until
        assert bot.send_invoice.await_args.kwargs["payload"] == "88:1:subscription@standard"
