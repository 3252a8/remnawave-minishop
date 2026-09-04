from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from bot.services.partner_checkout_balance import PartnerCheckoutBalanceService
from bot.services.partner_commission_service import PartnerCommissionService
from bot.services.user_balance_service import UserBalanceService
from db.dal import message_log_dal, payment_dal


class PaymentDalIdempotenceTests(IsolatedAsyncioTestCase):
    async def test_create_or_get_uses_unique_idempotence_key_conflict_clause(self):
        payment = SimpleNamespace(payment_id=17)
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: 17))
        )
        payload = {
            "user_id": 42,
            "amount": 199.0,
            "currency": "RUB",
            "status": "pending_yookassa",
            "provider": "yookassa",
            "idempotence_key": "yk-auto-cycle-7",
        }

        with (
            patch.object(
                payment_dal,
                "get_payment_by_idempotence_key",
                AsyncMock(side_effect=[None, payment]),
            ),
            patch.object(
                payment_dal,
                "_validate_payment_record_references",
                AsyncMock(),
            ),
        ):
            result, created = await payment_dal.create_or_get_payment_record_by_idempotence_key(
                session,
                payload,
            )

        self.assertIs(result, payment)
        self.assertTrue(created)
        statement = session.execute.await_args.args[0]
        rendered = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("ON CONFLICT (idempotence_key) DO NOTHING", rendered)
        self.assertIn("RETURNING payments.payment_id", rendered)


class PaymentDalStatusUpdateTests(IsolatedAsyncioTestCase):
    async def test_provider_payment_lookup_filters_by_provider_and_external_id(self):
        payment = SimpleNamespace(payment_id=1)
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: payment))
        )

        result = await payment_dal.get_payment_by_provider_payment_id(
            session,
            "stripe",
            "shared-id",
        )

        self.assertIs(result, payment)
        statement = session.execute.await_args.args[0]
        rendered = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("payments.provider = 'stripe'", rendered)
        self.assertIn("payments.provider_payment_id = 'shared-id'", rendered)

    async def test_update_payment_status_preserves_succeeded_payment(self):
        session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
        payment = SimpleNamespace(
            payment_id=1,
            status="succeeded",
            yookassa_payment_id=None,
        )

        with patch.object(
            payment_dal,
            "get_payment_by_db_id_for_update",
            AsyncMock(return_value=payment),
        ):
            result = await payment_dal.update_payment_status_by_db_id(
                session,
                1,
                "canceled",
                yk_payment_id="yk-1",
            )

        self.assertIs(result, payment)
        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.yookassa_payment_id, "yk-1")
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(payment)

    async def test_provider_status_update_preserves_succeeded_payment(self):
        session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
        payment = SimpleNamespace(
            payment_id=2,
            status="succeeded",
            provider_payment_id=None,
            provider_payment_url=None,
        )

        with patch.object(
            payment_dal,
            "get_payment_by_db_id_for_update",
            AsyncMock(return_value=payment),
        ):
            result = await payment_dal.update_provider_payment_and_status(
                session,
                2,
                "provider-2",
                "failed",
                provider_payment_url="https://pay.example/2",
            )

        self.assertIs(result, payment)
        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.provider_payment_id, "provider-2")
        self.assertEqual(payment.provider_payment_url, "https://pay.example/2")
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(payment)

    async def test_provider_status_update_keeps_pending_payment_mutable(self):
        session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
        payment = SimpleNamespace(
            payment_id=3,
            status="pending_platega",
            provider_payment_id=None,
            provider_payment_url=None,
        )

        with patch.object(
            payment_dal,
            "get_payment_by_db_id_for_update",
            AsyncMock(return_value=payment),
        ):
            result = await payment_dal.update_provider_payment_and_status(
                session,
                3,
                "provider-3",
                "failed",
            )

        self.assertIs(result, payment)
        self.assertEqual(payment.status, "failed")
        self.assertEqual(payment.provider_payment_id, "provider-3")
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(payment)

    async def test_success_reactivates_a_previously_released_partner_spend(self):
        savepoint = AsyncMock()
        session = SimpleNamespace(
            begin_nested=AsyncMock(return_value=savepoint),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )
        payment = SimpleNamespace(payment_id=4, status="failed_creation")

        with (
            patch.object(
                payment_dal,
                "get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "ensure_consumed",
                AsyncMock(),
            ) as ensure_consumed,
            patch.object(
                PartnerCheckoutBalanceService,
                "release_if_terminal",
                AsyncMock(),
            ),
            patch.object(payment_dal, "_add_payment_success_log", AsyncMock()),
        ):
            await payment_dal.update_payment_status_by_db_id(session, 4, "succeeded")

        ensure_consumed.assert_awaited_once_with(session, payment_id=4)
        self.assertEqual(payment.status, "succeeded")

    async def test_success_adds_user_payment_log_once(self):
        savepoint = AsyncMock()
        session = SimpleNamespace(
            begin_nested=AsyncMock(return_value=savepoint),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )
        payment = SimpleNamespace(
            payment_id=91,
            user_id=42,
            status="pending_yookassa",
            amount=0.0,
            currency="rub",
            provider="yookassa",
            sale_mode="subscription@standard",
        )

        with (
            patch.object(
                payment_dal,
                "get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "ensure_consumed",
                AsyncMock(),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "release_if_terminal",
                AsyncMock(),
            ),
            patch.object(
                message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ) as create_log,
        ):
            await payment_dal.update_payment_status_by_db_id(session, 91, "succeeded")
            await payment_dal.update_payment_status_by_db_id(session, 91, "succeeded")

        create_log.assert_awaited_once_with(
            session,
            {
                "user_id": 42,
                "event_type": "payment_succeeded",
                "content": (
                    "amount=0.0 currency=RUB payment_id=91 "
                    "provider=yookassa sale_mode=subscription@standard"
                ),
                "is_admin_event": False,
                "target_user_id": 42,
            },
        )
        self.assertEqual(payment.status, "succeeded")

    async def test_balance_topup_keeps_its_specialized_success_log(self):
        savepoint = AsyncMock()
        session = SimpleNamespace(
            begin_nested=AsyncMock(return_value=savepoint),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )
        payment = SimpleNamespace(
            payment_id=1041,
            user_id=42,
            status="pending",
            amount=500.0,
            currency="RUB",
            provider="yookassa",
            sale_mode="balance_topup|account",
        )

        with (
            patch.object(
                payment_dal,
                "get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "ensure_consumed",
                AsyncMock(),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "release_if_terminal",
                AsyncMock(),
            ),
            patch.object(
                message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ) as create_log,
        ):
            await payment_dal.update_payment_status_by_db_id(session, 1041, "succeeded")

        create_log.assert_not_awaited()

    async def test_terminal_status_releases_partner_spend(self):
        savepoint = AsyncMock()
        session = SimpleNamespace(
            begin_nested=AsyncMock(return_value=savepoint),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )
        payment = SimpleNamespace(payment_id=5, status="pending")

        with (
            patch.object(
                payment_dal,
                "get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "release_if_terminal",
                AsyncMock(),
            ) as release_if_terminal,
        ):
            await payment_dal.update_payment_status_by_db_id(session, 5, "canceled")

        release_if_terminal.assert_awaited_once_with(
            session,
            payment_id=5,
            status="canceled",
        )
        self.assertEqual(payment.status, "canceled")

    async def test_balance_topup_reversal_is_retried_idempotently(self):
        savepoint = AsyncMock()
        session = SimpleNamespace(
            begin_nested=AsyncMock(return_value=savepoint),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )
        payment = SimpleNamespace(
            payment_id=6,
            status="reversed",
            sale_mode="balance_topup|account",
            user_balance_amount_minor=None,
            yookassa_payment_id=None,
        )
        reverse_topup = AsyncMock(return_value=SimpleNamespace(entry_id=9))

        with (
            patch.object(
                payment_dal,
                "get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "release_if_terminal",
                AsyncMock(),
            ),
            patch.object(UserBalanceService, "reverse_payment_topup", reverse_topup),
        ):
            await payment_dal.update_payment_status_by_db_id(session, 6, "reversed")

        reverse_topup.assert_awaited_once_with(
            session,
            payment_id=6,
            reason="payment reversed",
        )
        self.assertEqual(payment.status, "reversed")

    async def test_balance_topup_reversal_failure_aborts_status_update(self):
        savepoint = AsyncMock()
        session = SimpleNamespace(
            begin_nested=AsyncMock(return_value=savepoint),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )
        payment = SimpleNamespace(
            payment_id=7,
            status="succeeded",
            sale_mode="balance_topup",
            user_balance_amount_minor=None,
            yookassa_payment_id=None,
        )

        with (
            patch.object(
                payment_dal,
                "get_payment_by_db_id_for_update",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PartnerCheckoutBalanceService,
                "release_if_terminal",
                AsyncMock(),
            ),
            patch.object(PartnerCommissionService, "reverse_payment", AsyncMock()),
            patch.object(
                UserBalanceService,
                "reverse_payment_topup",
                AsyncMock(side_effect=RuntimeError("ledger unavailable")),
            ),
            self.assertRaisesRegex(RuntimeError, "ledger unavailable"),
        ):
            await payment_dal.update_payment_status_by_db_id(session, 7, "refunded")

        session.flush.assert_not_awaited()
        session.refresh.assert_not_awaited()


class PaymentDalFinalizationClaimTests(IsolatedAsyncioTestCase):
    async def test_get_payment_fresh_reloads_existing_identity(self):
        payment = SimpleNamespace(payment_id=5)
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: payment))
        )

        result = await payment_dal.get_payment_by_db_id(session, 5, fresh=True)

        self.assertIs(result, payment)
        statement = session.execute.await_args.args[0]
        self.assertTrue(statement.get_execution_options()["populate_existing"])

    async def test_get_payment_for_update_uses_transaction_lock(self):
        payment = SimpleNamespace(payment_id=5)
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: payment))
        )

        result = await payment_dal.get_payment_by_db_id_for_update(session, 5)

        self.assertIs(result, payment)
        statement = session.execute.await_args.args[0]
        rendered = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("FOR UPDATE", rendered)

    async def test_claim_finalization_uses_conditional_update_returning(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
        )

        result = await payment_dal.claim_payment_finalization(
            session,
            5,
            provider_payment_id="provider-5",
        )

        self.assertIsNone(result)
        statement = session.execute.await_args.args[0]
        rendered = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("UPDATE payments SET", rendered)
        self.assertIn("succeeded_pending_finalization", rendered)
        self.assertIn("lower(payments.status) != 'succeeded'", rendered)
        self.assertIn("RETURNING payments.payment_id", rendered)
