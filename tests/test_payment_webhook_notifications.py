from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers.shared import webhooks
from bot.payment_providers.shared.success import PaymentSuccessRequest, finalize_successful_payment


class _PaymentWithLazyUser:
    payment_id = 12
    user_id = 42

    @property
    def user(self):
        raise RuntimeError("lazy relationship access is not allowed here")


class _I18n:
    def gettext(self, _language, key, **_kwargs):
        return key


class PaymentWebhookNotificationTests(IsolatedAsyncioTestCase):
    async def test_failed_payment_notification_loads_user_explicitly(self):
        user = SimpleNamespace(user_id=42, language_code="ru", email="u@example.test")
        bot = SimpleNamespace(send_message=AsyncMock())
        settings = SimpleNamespace(DEFAULT_LANGUAGE="en", SUBSCRIPTION_MINI_APP_URL="")

        with (
            patch.object(
                webhooks.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=user),
            ) as get_user,
            patch.object(
                webhooks,
                "send_user_notification_email",
                AsyncMock(),
            ) as send_email,
        ):
            await webhooks.notify_user_payment_failed(
                bot=bot,
                settings=settings,
                i18n=_I18n(),
                session=AsyncMock(),
                payment=_PaymentWithLazyUser(),
            )

        get_user.assert_awaited_once()
        bot.send_message.assert_awaited_once_with(42, "payment_failed")
        send_email.assert_awaited_once()

    async def test_finalize_failure_marks_payment_retryable(self):
        session = AsyncMock()
        payment = SimpleNamespace(payment_id=12, user_id=42, status="succeeded")
        subscription_service = SimpleNamespace(
            activate_subscription=AsyncMock(side_effect=RuntimeError("panel failed"))
        )

        with patch(
            "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
            AsyncMock(return_value=payment),
        ) as update_status:
            result = await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
                    i18n=_I18n(),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=SimpleNamespace(),
                    payment=payment,
                    user_id=42,
                    amount=50,
                    currency="RUB",
                    sale_mode="hwid_devices@standard",
                    months=1,
                    traffic_amount=1,
                    provider_subscription="platega",
                    provider_notification="platega",
                )
            )

        self.assertIsNone(result)
        session.rollback.assert_awaited_once()
        update_status.assert_awaited_once_with(session, 12, "activation_failed")
        session.commit.assert_awaited_once()
