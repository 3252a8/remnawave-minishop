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
