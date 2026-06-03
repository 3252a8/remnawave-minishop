from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers import yookassa


class _I18n:
    def gettext(self, _lang, key, **kwargs):
        if key == "payment_successful_hwid_devices_full":
            return f"HWID +{kwargs['count']}"
        if key == "config_link_not_available":
            return "n/a"
        return key


class YooKassaHwidWebhookTests(IsolatedAsyncioTestCase):
    async def test_telegram_subscription_hwid_quote_is_stored_in_yookassa_metadata(self):
        valid_from = datetime(2099, 2, 1, tzinfo=timezone.utc)
        valid_until = datetime(2099, 3, 1, tzinfo=timezone.utc)
        session = AsyncMock()
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        service = SimpleNamespace(
            config=SimpleNamespace(DEFAULT_RECEIPT_EMAIL="receipt@example.test"),
            create_payment=AsyncMock(
                return_value={
                    "id": "yk-pay-1",
                    "status": "pending",
                    "confirmation_url": "https://pay.example.test/1",
                }
            ),
        )
        hwid_quote = {
            "device_count": 2,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "pricing_period_months": 1,
            "proration_ratio": 1.0,
            "full_price": 50.0,
        }
        payment = SimpleNamespace(payment_id=123)

        with (
            patch.object(
                yookassa.payment_dal,
                "create_payment_record",
                AsyncMock(return_value=payment),
            ) as create_record,
            patch.object(
                yookassa.payment_dal,
                "update_payment_status_by_db_id",
                AsyncMock(),
            ),
        ):
            result = await yookassa._initiate_yk_payment(
                callback,
                settings=SimpleNamespace(),
                session=session,
                yookassa_service=service,
                i18n=_I18n(),
                current_lang="en",
                get_text=lambda key, **kwargs: key,
                user_id=42,
                months=1,
                price_rub=150,
                currency_code_for_yk="RUB",
                save_payment_method=False,
                back_callback="tariff:period:standard:1",
                sale_mode="subscription@standard|hwid_renewal",
                hwid_quote=hwid_quote,
            )

        assert result is True
        record_payload = create_record.await_args.args[1]
        assert record_payload["sale_mode"] == "subscription@standard|hwid_renewal"
        assert record_payload["tariff_key"] == "standard"
        assert record_payload["purchased_hwid_devices"] == 2
        assert record_payload["hwid_valid_from"] == valid_from
        assert record_payload["hwid_valid_until"] == valid_until
        metadata = service.create_payment.await_args.kwargs["metadata"]
        assert metadata["sale_mode"] == "subscription@standard|hwid_renewal"
        assert metadata["hwid_devices"] == "2"
        assert metadata["hwid_valid_from"] == valid_from.isoformat()
        assert metadata["hwid_valid_until"] == valid_until.isoformat()
        assert metadata["hwid_pricing_period_months"] == "1"
        assert metadata["hwid_proration_ratio"] == "1.0"
        assert metadata["hwid_full_price"] == "50.0"
        assert service.create_payment.await_args.kwargs["amount"] == 150

    async def test_webapp_hwid_metadata_activates_device_count_without_end_date(self):
        payment = SimpleNamespace(payment_id=5, status="pending_yookassa", tariff_key="standard")
        updated_payment = SimpleNamespace(payment_id=5, status="succeeded", tariff_key="standard")
        db_user = SimpleNamespace(
            user_id=42,
            username="alice",
            language_code="en",
            referred_by_id=None,
        )
        subscription_service = SimpleNamespace(
            activate_subscription=AsyncMock(
                return_value={
                    "subscription_id": 11,
                    "purchased_hwid_devices": 2,
                }
            )
        )
        settings = SimpleNamespace(
            traffic_sale_mode=False,
            yookassa_autopayments_active=False,
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            LKNPD_RECEIPT_NAME_TRAFFIC="{gb} GB",
            LKNPD_RECEIPT_NAME_SUBSCRIPTION="{months} months",
        )
        payment_info = {
            "id": "yk-hwid-1",
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "120.00", "currency": "RUB"},
            "metadata": {
                "user_id": "42",
                "subscription_months": "0",
                "payment_db_id": "5",
                "sale_mode": "hwid_devices@standard",
                "hwid_devices": "2",
                "source": "webapp",
            },
            "description": "Extra HWID devices +2",
        }

        with (
            patch.object(
                yookassa.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                yookassa.payment_dal,
                "update_payment_status_by_db_id",
                AsyncMock(return_value=updated_payment),
            ) as update_status,
            patch.object(yookassa.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)),
            patch.object(
                yookassa,
                "prepare_config_links",
                AsyncMock(return_value=("link", "https://example.test/sub")),
            ),
            patch.object(
                yookassa,
                "ensure_user_install_guide_links",
                AsyncMock(return_value=SimpleNamespace(public_share_url=None)),
            ),
            patch.object(yookassa, "send_success_message_to_user", AsyncMock()) as send_success,
            patch.object(yookassa, "notify_admins_payment_received", AsyncMock()),
        ):
            await yookassa.process_successful_payment(
                AsyncMock(),
                AsyncMock(),
                payment_info,
                _I18n(),
                settings,
                AsyncMock(),
                subscription_service,
                AsyncMock(),
            )

        activation_args = subscription_service.activate_subscription.await_args.args
        activation_kwargs = subscription_service.activate_subscription.await_args.kwargs
        assert activation_args[2] == 2
        assert activation_kwargs["sale_mode"] == "hwid_devices@standard"
        assert activation_kwargs["traffic_gb"] is None
        update_status.assert_awaited_once()
        send_success.assert_awaited_once()

    async def test_auto_renew_hwid_metadata_is_persisted_for_activation(self):
        valid_from = datetime(2099, 2, 1, tzinfo=timezone.utc)
        valid_until = datetime(2099, 3, 1, tzinfo=timezone.utc)
        payment = SimpleNamespace(payment_id=5, status="pending_yookassa", tariff_key="standard")
        updated_payment = SimpleNamespace(payment_id=5, status="succeeded", tariff_key="standard")
        db_user = SimpleNamespace(
            user_id=42,
            username="alice",
            language_code="en",
            referred_by_id=None,
        )
        subscription_service = SimpleNamespace(
            activate_subscription=AsyncMock(
                return_value={
                    "subscription_id": 11,
                    "end_date": valid_until,
                    "hwid_devices_renewed_count": 2,
                    "hwid_devices_valid_until": valid_until,
                }
            )
        )
        referral_service = SimpleNamespace(
            apply_referral_bonuses_for_payment=AsyncMock(return_value={})
        )
        settings = SimpleNamespace(
            traffic_sale_mode=False,
            yookassa_autopayments_active=False,
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            LKNPD_RECEIPT_NAME_TRAFFIC="{gb} GB",
            LKNPD_RECEIPT_NAME_SUBSCRIPTION="{months} months",
        )
        payment_info = {
            "id": "yk-auto-hwid-1",
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "449.00", "currency": "RUB"},
            "metadata": {
                "user_id": "42",
                "subscription_months": "1",
                "auto_renew_for_subscription_id": "555",
                "sale_mode": "subscription@standard",
                "hwid_devices": "2",
                "hwid_valid_from": valid_from.isoformat(),
                "hwid_valid_until": valid_until.isoformat(),
                "hwid_pricing_period_months": "1",
                "hwid_proration_ratio": "1.0",
                "hwid_full_price": "50.0",
            },
            "description": "Auto-renewal for 1 months",
        }

        with (
            patch.object(
                yookassa.payment_dal,
                "get_payment_by_provider_payment_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                yookassa.payment_dal,
                "ensure_payment_with_provider_id",
                AsyncMock(return_value=payment),
            ) as ensure_payment,
            patch.object(
                yookassa.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                yookassa.payment_dal,
                "update_payment_status_by_db_id",
                AsyncMock(return_value=updated_payment),
            ),
            patch.object(yookassa.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)),
            patch.object(
                yookassa,
                "prepare_config_links",
                AsyncMock(return_value=("link", "https://example.test/sub")),
            ),
            patch.object(yookassa, "send_success_message_to_user", AsyncMock()) as send_success,
            patch.object(yookassa, "notify_admins_payment_received", AsyncMock()),
        ):
            await yookassa.process_successful_payment(
                AsyncMock(),
                AsyncMock(),
                payment_info,
                _I18n(),
                settings,
                AsyncMock(),
                subscription_service,
                referral_service,
            )

        ensure_payment.assert_awaited_once()
        ensure_kwargs = ensure_payment.await_args.kwargs
        assert ensure_kwargs["sale_mode"] == "subscription@standard"
        assert ensure_kwargs["tariff_key"] == "standard"
        assert ensure_kwargs["purchased_hwid_devices"] == 2
        assert ensure_kwargs["hwid_valid_from"] == valid_from
        assert ensure_kwargs["hwid_valid_until"] == valid_until
        assert ensure_kwargs["hwid_pricing_period_months"] == 1
        assert ensure_kwargs["hwid_proration_ratio"] == 1.0
        assert ensure_kwargs["hwid_full_price"] == 50.0
        activation_kwargs = subscription_service.activate_subscription.await_args.kwargs
        assert activation_kwargs["sale_mode"] == "subscription@standard"
        send_success.assert_awaited_once()
