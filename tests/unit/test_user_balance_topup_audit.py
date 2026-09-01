from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers.shared.success import (
    PaymentSuccessRequest,
    finalize_successful_payment,
)


def _request(payment, session) -> PaymentSuccessRequest:
    return PaymentSuccessRequest(
        bot=object(),
        settings=SimpleNamespace(),
        i18n=object(),
        session=session,
        subscription_service=object(),
        referral_service=object(),
        payment=payment,
        user_id=42,
        amount=750,
        currency="RUB",
        sale_mode="balance_topup",
        months=1,
        traffic_amount=None,
        provider_subscription="qa",
        provider_notification="QA",
    )


class UserBalanceTopupAuditTests(IsolatedAsyncioTestCase):
    async def test_success_writes_admin_audit_with_payment_details(self) -> None:
        payment = SimpleNamespace(
            payment_id=91,
            status="pending",
            user_id=42,
            amount=750,
            currency="RUB",
            sale_mode="balance_topup",
            provider="qa",
        )
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        audit = AsyncMock()

        with (
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.payment_providers.shared.success.user_dal.lock_user_by_id",
                AsyncMock(return_value=SimpleNamespace(user_id=42)),
            ),
            patch(
                "bot.payment_providers.shared.success.UserBalanceService.credit_payment_topup",
                AsyncMock(
                    return_value=SimpleNamespace(
                        amount_minor=75000,
                        currency_scale=2,
                        currency="RUB",
                    )
                ),
            ),
            patch(
                "bot.payment_providers.shared.success.message_log_dal.create_message_log_no_commit",
                audit,
            ),
            patch(
                "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
                AsyncMock(),
            ),
            patch(
                "bot.payment_providers.shared.success.payment_units_for_activation",
                return_value=1,
            ),
            patch(
                "bot.payment_providers.shared.success.build_payment_succeeded_payload",
                return_value={},
            ),
            patch("bot.payment_providers.shared.success.PaymentSucceededPayload.model_validate"),
            patch("bot.payment_providers.shared.success.events.emit_model", AsyncMock()),
            patch(
                "bot.payment_providers.shared.success.resolve_user_language",
                AsyncMock(return_value=(SimpleNamespace(user_id=42), "ru")),
            ),
            patch(
                "bot.payment_providers.shared.success.make_translator",
                return_value=lambda _key, **_kwargs: "ok",
            ),
            patch(
                "bot.payment_providers.shared.success.send_success_message_to_user",
                AsyncMock(),
            ),
        ):
            outcome = await finalize_successful_payment(_request(payment, session))

        self.assertIsNotNone(outcome)
        audit.assert_awaited_once()
        audit_call = audit.await_args
        self.assertIsNotNone(audit_call)
        assert audit_call is not None
        payload = audit_call.args[1]
        self.assertEqual(payload["user_id"], 42)
        self.assertEqual(payload["event_type"], "balance_topup_succeeded")
        self.assertIn("amount=750.00", payload["content"])
        self.assertIn("currency=RUB", payload["content"])
        self.assertIn("payment_id=91", payload["content"])
        self.assertIn("provider=qa", payload["content"])
        session.commit.assert_awaited_once()

    async def test_duplicate_success_does_not_repeat_audit(self) -> None:
        payment = SimpleNamespace(payment_id=91, status="succeeded")
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        audit = AsyncMock()

        with (
            patch(
                "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch(
                "bot.payment_providers.shared.success.message_log_dal.create_message_log_no_commit",
                audit,
            ),
        ):
            outcome = await finalize_successful_payment(_request(payment, session))

        self.assertIsNone(outcome)
        audit.assert_not_awaited()
        session.commit.assert_not_awaited()
