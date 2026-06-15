from datetime import datetime
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
    async def test_failed_payment_notification_emits_cancel_event(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        settings = SimpleNamespace(DEFAULT_LANGUAGE="en", SUBSCRIPTION_MINI_APP_URL="")

        with patch.object(webhooks.events, "emit", AsyncMock()) as emit_event:
            await webhooks.notify_user_payment_failed(
                bot=bot,
                settings=settings,
                i18n=_I18n(),
                session=AsyncMock(),
                payment=_PaymentWithLazyUser(),
            )

        bot.send_message.assert_not_called()
        emit_event.assert_awaited_once_with(
            "payment.canceled",
            {
                "user_id": 42,
                "payment_db_id": 12,
                "provider": None,
                "provider_payment_id": None,
                "status": None,
                "message_key": "payment_failed",
            },
        )

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

    async def test_finalize_uses_payment_tariff_and_emits_referral_after_commit(self):
        order = []

        async def commit():
            order.append("commit")

        async def emit(name, payload):
            order.append(("emit", name, payload))

        session = AsyncMock()
        session.commit = AsyncMock(side_effect=commit)
        payment = SimpleNamespace(
            payment_id=12,
            user_id=42,
            status="pending",
            tariff_key="premium",
        )
        activation_end = datetime(2026, 1, 1)
        subscription_service = SimpleNamespace(
            activate_subscription=AsyncMock(
                return_value={
                    "subscription_id": 55,
                    "end_date": activation_end,
                    "tariff_key": "premium",
                    "was_extension": True,
                }
            )
        )
        referral_event = {
            "referee_user_id": 42,
            "inviter_bonus_applied": True,
            "inviter_user_id": 1,
        }
        referral_service = SimpleNamespace(
            apply_referral_bonuses_for_payment=AsyncMock(
                return_value={
                    "referee_bonus_applied_days": 3,
                    "referee_new_end_date": activation_end,
                    "event_payload": referral_event,
                }
            )
        )

        with (
            patch("bot.payment_providers.shared.success.events.emit", AsyncMock(side_effect=emit)),
            patch(
                "bot.payment_providers.shared.success.prepare_config_links",
                AsyncMock(return_value=("link", "https://example.test/sub")),
            ),
            patch("bot.payment_providers.shared.success.send_success_message_to_user", AsyncMock()),
        ):
            result = await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en", SUBSCRIPTION_MINI_APP_URL=""),
                    i18n=_I18n(),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=referral_service,
                    payment=payment,
                    user_id=42,
                    amount=50,
                    currency="RUB",
                    sale_mode="subscription",
                    months=1,
                    traffic_amount=None,
                    provider_subscription="platega",
                    provider_notification="platega",
                    db_user=SimpleNamespace(user_id=42, language_code="en", referred_by_id=None),
                    skip_keyboard=True,
                )
            )

        self.assertIsNotNone(result)
        activation_kwargs = subscription_service.activate_subscription.await_args.kwargs
        self.assertEqual(activation_kwargs["tariff_key"], "premium")
        referral_kwargs = referral_service.apply_referral_bonuses_for_payment.await_args.kwargs
        self.assertEqual(referral_kwargs["tariff_key"], "premium")
        self.assertEqual(order[0], "commit")
        emitted_names = [item[1] for item in order[1:]]
        self.assertIn("payment.succeeded", emitted_names)
        self.assertIn("subscription.extended", emitted_names)
        self.assertIn("referral.bonus_granted", emitted_names)
