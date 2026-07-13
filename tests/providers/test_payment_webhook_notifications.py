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
        payment = SimpleNamespace(
            payment_id=12,
            user_id=42,
            status="succeeded_pending_finalization",
        )
        subscription_service = SimpleNamespace(
            activate_subscription=AsyncMock(side_effect=RuntimeError("panel failed"))
        )

        with (
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
                AsyncMock(return_value=payment),
            ) as update_status,
        ):
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

    async def test_finalize_none_activation_rolls_back_and_marks_payment_failed(self):
        session = AsyncMock()
        payment = SimpleNamespace(
            payment_id=12,
            user_id=42,
            status="succeeded_pending_finalization",
        )
        subscription_service = SimpleNamespace(activate_subscription=AsyncMock(return_value=None))
        referral_service = SimpleNamespace(apply_referral_bonuses_for_payment=AsyncMock())

        with (
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
                AsyncMock(return_value=payment),
            ) as update_status,
            patch(
                "bot.payment_providers.shared.success.events.emit_model",
                AsyncMock(),
            ) as emit_model,
        ):
            result = await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
                    i18n=_I18n(),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=referral_service,
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
        referral_service.apply_referral_bonuses_for_payment.assert_not_awaited()
        emit_model.assert_not_awaited()

    async def test_finalize_subscription_without_end_date_is_activation_failure(self):
        session = AsyncMock()
        payment = SimpleNamespace(
            payment_id=12,
            user_id=42,
            status="succeeded_pending_finalization",
        )
        subscription_service = SimpleNamespace(
            activate_subscription=AsyncMock(return_value={"subscription_id": 55})
        )
        referral_service = SimpleNamespace(apply_referral_bonuses_for_payment=AsyncMock())

        with (
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
                AsyncMock(return_value=payment),
            ) as update_status,
            patch(
                "bot.payment_providers.shared.success.events.emit_model",
                AsyncMock(),
            ) as emit_model,
        ):
            result = await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
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
                )
            )

        self.assertIsNone(result)
        session.rollback.assert_awaited_once()
        update_status.assert_awaited_once_with(session, 12, "activation_failed")
        session.commit.assert_awaited_once()
        referral_service.apply_referral_bonuses_for_payment.assert_not_awaited()
        emit_model.assert_not_awaited()

    async def test_finalize_uses_payment_tariff_and_emits_referral_after_commit(self):
        order = []

        async def commit():
            order.append("commit")

        async def emit_model(payload, **payload_options):
            order.append(
                (
                    "emit",
                    payload.EVENT_NAME,
                    payload.to_payload(**payload_options),
                )
            )

        async def update_status(_session, _payment_id, status):
            order.append(("status", status))
            return payment

        session = AsyncMock()
        session.commit = AsyncMock(side_effect=commit)
        payment = SimpleNamespace(
            payment_id=12,
            user_id=42,
            status="pending",
            tariff_key="premium",
        )
        # Payment notification payloads preserve legacy naive DB datetimes in tests.
        activation_end = datetime(2026, 1, 1)  # noqa: DTZ001
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
            "reason": "payment",
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
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.payment_providers.shared.success.events.emit_model",
                AsyncMock(side_effect=emit_model),
            ),
            patch(
                "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
                AsyncMock(side_effect=update_status),
            ) as update_status_mock,
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
        update_status_mock.assert_awaited_once_with(session, 12, "succeeded")
        self.assertEqual(order[0], ("status", "succeeded"))
        self.assertEqual(order[1], "commit")
        emitted_names = [item[1] for item in order[2:]]
        self.assertIn("payment.succeeded", emitted_names)
        self.assertIn("subscription.extended", emitted_names)
        self.assertIn("referral.bonus_granted", emitted_names)

    async def test_finalize_skips_duplicate_payment_after_locked_reload(self):
        session = AsyncMock()
        pending_payment = SimpleNamespace(
            payment_id=12,
            user_id=42,
            status="succeeded_pending_finalization",
            tariff_key="standard",
        )
        succeeded_payment = SimpleNamespace(
            payment_id=12,
            user_id=42,
            status="succeeded",
            tariff_key="standard",
        )
        subscription_service = SimpleNamespace(
            activate_subscription=AsyncMock(
                return_value={
                    "subscription_id": 55,
                    "end_date": datetime(2026, 1, 1),  # noqa: DTZ001
                    "tariff_key": "standard",
                    "was_extension": True,
                }
            )
        )
        referral_service = SimpleNamespace(
            apply_referral_bonuses_for_payment=AsyncMock(return_value=None)
        )

        def request(payment):
            return PaymentSuccessRequest(
                bot=SimpleNamespace(),
                settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
                i18n=_I18n(),
                session=session,
                subscription_service=subscription_service,
                referral_service=referral_service,
                payment=payment,
                user_id=42,
                amount=50,
                currency="RUB",
                sale_mode="subscription@standard",
                months=1,
                traffic_amount=None,
                provider_subscription="platega",
                provider_notification="platega",
                db_user=SimpleNamespace(user_id=42, language_code="en", referred_by_id=None),
                skip_keyboard=True,
            )

        with (
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(side_effect=[pending_payment, succeeded_payment]),
            ),
            patch(
                "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
                AsyncMock(return_value=succeeded_payment),
            ),
            patch("bot.payment_providers.shared.success.events.emit_model", AsyncMock()),
            patch(
                "bot.payment_providers.shared.success.prepare_config_links",
                AsyncMock(return_value=("link", "https://example.test/sub")),
            ),
            patch(
                "bot.payment_providers.shared.success.send_success_message_to_user",
                AsyncMock(),
            ) as send_success,
        ):
            first = await finalize_successful_payment(request(pending_payment))
            second = await finalize_successful_payment(request(pending_payment))

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        subscription_service.activate_subscription.assert_awaited_once()
        send_success.assert_awaited_once()
