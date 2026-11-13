from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import main_worker
from sqlalchemy.dialects import postgresql
from yookassa.domain.exceptions import (
    BadRequestError,
    InternalServerError,
    TooManyRequestsError,
)

from bot.payment_providers.shared import RecurringChargeContext
from bot.payment_providers.yookassa import YooKassaConfig, YooKassaService
from bot.payment_providers.yookassa import service as service_module
from bot.payment_providers.yookassa import success as success_module
from bot.payment_providers.yookassa.auto_renew import (
    YooKassaProviderRequestSnapshot,
    attempt_idempotence_key,
    classify_request_exception,
)
from bot.services.auto_renew_retry_worker import AutoRenewRetryWorker
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.dal import auto_renew_dal, subscription_dal


def _settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "AUTO_RENEW_RETRY_ENABLED": True,
        "AUTO_RENEW_RETRY_DRY_RUN": False,
        "AUTO_RENEW_MAX_FINANCIAL_ATTEMPTS": 2,
        "AUTO_RENEW_MAX_TRANSPORT_REPLAYS": 4,
        "AUTO_RENEW_RETRY_GRACE_HOURS": 24,
        "AUTO_RENEW_WORKER_TICK_SECONDS": 60,
        "AUTO_RENEW_WORKER_BATCH_SIZE": 50,
        "PAYMENT_REQUEST_TIMEOUT_SECONDS": 20,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(*, response: dict[str, Any] | None = None) -> YooKassaService:
    service = object.__new__(YooKassaService)
    service.settings = _settings()
    service.config = YooKassaConfig(
        SHOP_ID="shop",
        SECRET_KEY="secret",
        RETURN_URL="https://example.test/return",
        DEFAULT_RECEIPT_EMAIL="receipt@example.test",
        AUTOPAYMENTS_ENABLED=True,
    )
    service._sdk_configured_for = ("shop", "secret")
    service._configured_return_url_override = None
    service._bot_username_for_default_return = None
    service.subscription_service = None
    service.create_payment = AsyncMock(
        return_value=response or {"id": "yk-remote-1", "status": "pending"}
    )
    return service


def _context(
    session: AsyncMock,
    *,
    cycle_id: int | None = None,
    retry_kind: str | None = None,
) -> RecurringChargeContext:
    cycle_end = datetime.now(UTC) + timedelta(hours=18)
    return RecurringChargeContext(
        session=session,
        user_id=42,
        subscription_id=7,
        saved_method=SimpleNamespace(
            method_id=9,
            provider_payment_method_id="pm-1",
        ),
        amount=199.0,
        currency="RUB",
        months=1,
        sale_mode="subscription@standard",
        description="Renewal",
        metadata={
            "user_id": "42",
            "auto_renew_for_subscription_id": "7",
            "subscription_months": "1",
            "sale_mode": "subscription@standard",
        },
        idempotence_key="yk-auto-base",
        renewal_cycle_end=cycle_end,
        consent_version=3,
        payment_method_db_id=9,
        auto_renew_cycle_id=cycle_id,
        retry_kind=retry_kind,
    )


def _cycle(
    context: RecurringChargeContext,
    *,
    state: str = "scheduled",
    current_payment_id: int | None = None,
    financial_attempts: int = 0,
    transport_replays: int = 0,
) -> SimpleNamespace:
    from bot.payment_providers.yookassa.auto_renew import YooKassaRecurringSnapshot

    snapshot = YooKassaRecurringSnapshot(
        amount=context.amount,
        currency=context.currency,
        months=context.months,
        sale_mode=context.sale_mode,
        description=context.description,
        metadata=dict(context.metadata),
        hwid_quote=None,
        entitlement_context_snapshot=None,
    )
    return SimpleNamespace(
        cycle_id=11,
        subscription_id=context.subscription_id,
        user_id=context.user_id,
        provider="yookassa",
        base_idempotence_key=context.idempotence_key,
        consent_version=context.consent_version,
        payment_method_id=context.payment_method_db_id,
        payment_method_provider_id="pm-1",
        request_snapshot=snapshot.to_json(),
        state=state,
        stopped_reason=None,
        current_payment_id=current_payment_id,
        financial_attempts=financial_attempts,
        transport_replays=transport_replays,
        renewal_cycle_end=context.renewal_cycle_end,
    )


class RequestFailureClassificationTests(IsolatedAsyncioTestCase):
    async def test_provider_and_transport_failures_have_stable_retry_policy(self) -> None:
        bad_request = classify_request_exception(BadRequestError(None))
        rate_limited = classify_request_exception(TooManyRequestsError(None))
        server_error = classify_request_exception(InternalServerError(None))
        timeout = classify_request_exception(TimeoutError())

        self.assertEqual((bad_request.http_status, bad_request.retryable), (400, False))
        self.assertEqual((rate_limited.http_status, rate_limited.retryable), (429, True))
        self.assertFalse(rate_limited.uncertain)
        self.assertEqual((server_error.http_status, server_error.retryable), (500, True))
        self.assertTrue(server_error.uncertain)
        self.assertEqual(timeout.kind, "request_timeout")
        self.assertTrue(timeout.uncertain)

    async def test_financial_attempt_uses_a_distinct_stable_key(self) -> None:
        self.assertEqual(attempt_idempotence_key("base", 1), "base")
        second = attempt_idempotence_key("base", 2)
        self.assertEqual(second, attempt_idempotence_key("base", 2))
        self.assertNotEqual(second, "base")
        self.assertLessEqual(len(second), 64)


class AttributedChargeTests(IsolatedAsyncioTestCase):
    async def _charge(
        self,
        *,
        response: dict[str, Any],
        cycle_state: str = "scheduled",
        current_payment: SimpleNamespace | None = None,
        retry_kind: str | None = None,
        financial_attempts: int = 0,
        transport_replays: int = 0,
        valid_consent: bool = True,
    ) -> tuple[Any, YooKassaService, SimpleNamespace, SimpleNamespace]:
        service = _service(response=response)
        session = AsyncMock()
        context = _context(
            session,
            cycle_id=11 if retry_kind else None,
            retry_kind=retry_kind,
        )
        cycle = _cycle(
            context,
            state=cycle_state,
            current_payment_id=(
                current_payment.payment_id if current_payment is not None else None
            ),
            financial_attempts=financial_attempts,
            transport_replays=transport_replays,
        )
        payment = SimpleNamespace(
            payment_id=22 if retry_kind != "financial" else 23,
            status="pending_yookassa",
            yookassa_payment_id=None,
            provider_payment_id=None,
            provider_request_snapshot=None,
            created_at=datetime.now(UTC),
        )

        async def prepare(*_args: Any, request_snapshot: str, **_kwargs: Any) -> Any:
            payment.provider_request_snapshot = request_snapshot
            return payment

        with (
            patch.object(
                service_module.auto_renew_dal,
                "create_or_get_cycle",
                AsyncMock(return_value=(cycle, True)),
            ),
            patch.object(
                service_module.auto_renew_dal,
                "get_cycle",
                AsyncMock(return_value=cycle),
            ),
            patch.object(
                service_module.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=current_payment),
            ),
            patch.object(
                service_module.payment_dal,
                "create_or_get_payment_record_by_idempotence_key",
                AsyncMock(return_value=(payment, True)),
            ) as create_payment_record,
            patch.object(
                service_module.auto_renew_dal,
                "prepare_payment_dispatch",
                AsyncMock(side_effect=prepare),
            ),
            patch.object(
                service_module.auto_renew_dal,
                "record_payment_dispatch",
                AsyncMock(),
            ),
            patch.object(
                service_module.auto_renew_dal,
                "validate_dispatch_context_for_update",
                AsyncMock(return_value=valid_consent),
            ),
            patch.object(
                service_module.payment_dal,
                "update_payment_status_by_db_id",
                AsyncMock(),
            ),
            patch.object(
                service_module.auto_renew_dal,
                "mark_waiting_provider",
                AsyncMock(),
            ),
            patch.object(
                service_module.auto_renew_dal,
                "mark_request_failure",
                AsyncMock(),
            ),
            patch.object(
                service_module.auto_renew_dal,
                "schedule_transport_retry",
                AsyncMock(),
            ),
            patch.object(
                service_module.auto_renew_dal,
                "stop_cycle",
                AsyncMock(),
            ),
        ):
            result = await service.charge_saved_payment_method(context)
        return result, service, cycle, create_payment_record

    async def test_initial_charge_persists_exact_snapshot_before_provider_call(self) -> None:
        result, service, _, create_payment_record = await self._charge(
            response={"id": "yk-1", "status": "pending"},
        )

        self.assertTrue(result.initiated)
        provider_call = service.create_payment.await_args.kwargs
        snapshot = YooKassaProviderRequestSnapshot(
            merchant_id=service.config.SHOP_ID,
            amount=provider_call["amount"],
            currency=provider_call["currency"],
            description=provider_call["description"],
            metadata=provider_call["metadata"],
            receipt_customer=provider_call["receipt_customer_override"],
            receipt_vat_code=provider_call["receipt_vat_code"],
            receipt_payment_mode=provider_call["receipt_payment_mode"],
            receipt_payment_subject=provider_call["receipt_payment_subject"],
            payment_method_id=provider_call["payment_method_id"],
        )
        self.assertEqual(provider_call["idempotence_key"], "yk-auto-base")
        self.assertEqual(snapshot.metadata["payment_db_id"], "22")
        local_payload = create_payment_record.await_args.args[1]
        self.assertEqual(local_payload["renewal_attempt_number"], 1)
        self.assertEqual(local_payload["renewal_consent_version"], 3)

    async def test_retryable_unknown_response_queues_same_key_transport_replay(self) -> None:
        result, service, cycle, _ = await self._charge(
            response={
                "error": True,
                "failure_kind": "request_timeout",
                "retryable": True,
                "uncertain": True,
            },
        )

        self.assertFalse(result.initiated)
        self.assertTrue(result.retryable)
        self.assertEqual(
            service.create_payment.await_args.kwargs["idempotence_key"], "yk-auto-base"
        )
        self.assertEqual(cycle.transport_replays, 0)

    async def test_final_400_response_is_not_retried(self) -> None:
        result, _, _, _ = await self._charge(
            response={
                "error": True,
                "failure_kind": "request_rejected",
                "retryable": False,
                "http_status": 400,
            },
        )

        self.assertFalse(result.initiated)
        self.assertFalse(result.retryable)
        self.assertEqual(result.http_status, 400)

    async def test_financial_retry_creates_only_attempt_two_with_new_key(self) -> None:
        canceled = SimpleNamespace(
            payment_id=22,
            status="canceled",
            yookassa_payment_id="yk-old",
            provider_payment_id=None,
            created_at=datetime.now(UTC),
        )
        result, service, _, create_payment_record = await self._charge(
            response={"id": "yk-new", "status": "pending"},
            cycle_state="financial_retry",
            current_payment=canceled,
            retry_kind="financial",
            financial_attempts=1,
        )

        self.assertTrue(result.initiated)
        local_payload = create_payment_record.await_args.args[1]
        self.assertEqual(local_payload["renewal_attempt_number"], 2)
        self.assertEqual(
            service.create_payment.await_args.kwargs["idempotence_key"],
            attempt_idempotence_key("yk-auto-base", 2),
        )

    async def test_final_consent_check_prevents_network_call(self) -> None:
        result, service, _, _ = await self._charge(
            response={"id": "must-not-run", "status": "pending"},
            valid_consent=False,
        )

        self.assertFalse(result.initiated)
        self.assertEqual(result.message, "consent_or_method_changed")
        service.create_payment.assert_not_awaited()

    async def test_transport_replay_cap_stops_before_local_or_remote_charge(self) -> None:
        result, service, _, create_payment_record = await self._charge(
            response={"id": "must-not-run", "status": "pending"},
            cycle_state="transport_retry",
            retry_kind="transport",
            financial_attempts=1,
            transport_replays=4,
        )

        self.assertFalse(result.initiated)
        self.assertEqual(result.message, "transport_replay_cap")
        create_payment_record.assert_not_awaited()
        service.create_payment.assert_not_awaited()


class AutoRenewWorkerTests(IsolatedAsyncioTestCase):
    async def test_preflight_rejects_disabled_or_changed_consent(self) -> None:
        worker = AutoRenewRetryWorker(
            cast(Any, _settings()),
            cast(Any, SimpleNamespace()),
            cast(Any, SimpleNamespace()),
        )
        cycle = SimpleNamespace(
            provider="yookassa",
            consent_version=3,
            renewal_cycle_end=datetime.now(UTC) + timedelta(hours=1),
        )
        base = {
            "is_active": True,
            "auto_renew_enabled": True,
            "provider": "yookassa",
            "auto_renew_consent_version": 3,
            "end_date": cycle.renewal_cycle_end,
        }

        self.assertEqual(
            worker._preflight_stop_reason(
                cycle,
                SimpleNamespace(**{**base, "auto_renew_enabled": False}),
            ),
            "consent_disabled",
        )
        self.assertEqual(
            worker._preflight_stop_reason(
                cycle,
                SimpleNamespace(**{**base, "auto_renew_consent_version": 4}),
            ),
            "consent_version_changed",
        )

    async def test_dry_run_defers_without_charging(self) -> None:
        recurring_service = SimpleNamespace(
            recurring_active=True,
            charge_saved_payment_method=AsyncMock(),
        )
        worker = AutoRenewRetryWorker(
            cast(Any, _settings(AUTO_RENEW_RETRY_DRY_RUN=True)),
            cast(Any, SimpleNamespace()),
            cast(
                Any,
                SimpleNamespace(
                    recurring_provider_services={"yookassa": recurring_service},
                    recurring_service_for=lambda _provider: recurring_service,
                ),
            ),
        )
        session = AsyncMock()
        cycle = SimpleNamespace(
            cycle_id=11,
            provider="yookassa",
            state="transport_retry",
            subscription_id=7,
            user_id=42,
            consent_version=3,
            payment_method_id=9,
            payment_method_provider_id="pm-1",
            current_payment_id=22,
            renewal_cycle_end=datetime.now(UTC) + timedelta(hours=1),
        )
        sub = SimpleNamespace(
            is_active=True,
            auto_renew_enabled=True,
            provider="yookassa",
            auto_renew_consent_version=3,
            end_date=cycle.renewal_cycle_end,
        )
        method = SimpleNamespace(
            method_id=9,
            provider_payment_method_id="pm-1",
        )

        class SessionContext:
            async def __aenter__(self) -> AsyncMock:
                return session

            async def __aexit__(self, *_args: Any) -> bool:
                return False

        worker.session_factory = cast(Any, lambda: SessionContext())
        with (
            patch(
                "bot.services.auto_renew_retry_worker.auto_renew_dal.get_cycle",
                AsyncMock(return_value=cycle),
            ),
            patch(
                "bot.services.auto_renew_retry_worker.subscription_dal."
                "get_subscription_by_id_for_update",
                AsyncMock(return_value=sub),
            ),
            patch(
                "bot.services.auto_renew_retry_worker.user_billing_dal."
                "get_user_default_payment_method",
                AsyncMock(return_value=method),
            ),
            patch(
                "bot.services.auto_renew_retry_worker.auto_renew_dal.cycle_has_blocking_payment",
                AsyncMock(return_value=False),
            ),
            patch(
                "bot.services.auto_renew_retry_worker.auto_renew_dal.defer_cycle",
                AsyncMock(),
            ) as defer_cycle,
        ):
            await worker._retry_cycle(11)

        defer_cycle.assert_awaited_once()
        recurring_service.charge_saved_payment_method.assert_not_awaited()

    async def test_changed_default_method_stops_cycle_without_charging(self) -> None:
        charge = AsyncMock()
        recurring_service = SimpleNamespace(
            recurring_active=True,
            charge_saved_payment_method=charge,
        )
        worker = AutoRenewRetryWorker(
            cast(Any, _settings()),
            cast(Any, SimpleNamespace()),
            cast(
                Any,
                SimpleNamespace(
                    recurring_provider_services={"yookassa": recurring_service},
                    recurring_service_for=lambda _provider: recurring_service,
                ),
            ),
        )
        session = AsyncMock()
        cycle_end = datetime.now(UTC) + timedelta(hours=1)
        cycle = SimpleNamespace(
            cycle_id=11,
            provider="yookassa",
            state="financial_retry",
            subscription_id=7,
            user_id=42,
            consent_version=3,
            payment_method_id=9,
            payment_method_provider_id="pm-old",
            current_payment_id=22,
            renewal_cycle_end=cycle_end,
        )
        sub = SimpleNamespace(
            is_active=True,
            auto_renew_enabled=True,
            provider="yookassa",
            auto_renew_consent_version=3,
            end_date=cycle_end,
        )
        method = SimpleNamespace(
            method_id=10,
            provider_payment_method_id="pm-new",
        )

        class SessionContext:
            async def __aenter__(self) -> AsyncMock:
                return session

            async def __aexit__(self, *_args: Any) -> bool:
                return False

        worker.session_factory = cast(Any, lambda: SessionContext())
        with (
            patch(
                "bot.services.auto_renew_retry_worker.auto_renew_dal.get_cycle",
                AsyncMock(return_value=cycle),
            ),
            patch(
                "bot.services.auto_renew_retry_worker.subscription_dal."
                "get_subscription_by_id_for_update",
                AsyncMock(return_value=sub),
            ),
            patch(
                "bot.services.auto_renew_retry_worker.user_billing_dal."
                "get_user_default_payment_method",
                AsyncMock(return_value=method),
            ),
            patch(
                "bot.services.auto_renew_retry_worker.auto_renew_dal.stop_cycle",
                AsyncMock(),
            ) as stop_cycle,
        ):
            await worker._retry_cycle(11)

        stop_cycle.assert_awaited_once_with(session, 11, "payment_method_changed")
        charge.assert_not_awaited()


class AutoRenewCancellationTests(IsolatedAsyncioTestCase):
    async def _cancel(
        self,
        reason: str,
        *,
        retry_enabled: bool = True,
        financial_attempts: int = 1,
    ) -> tuple[dict[str, Any] | None, AsyncMock, AsyncMock, AsyncMock]:
        payment = SimpleNamespace(
            payment_id=22,
            auto_renew_cycle_id=11,
            status="canceled",
        )
        cycle = SimpleNamespace(
            cycle_id=11,
            financial_attempts=financial_attempts,
            renewal_cycle_end=datetime.now(UTC) + timedelta(hours=18),
        )
        schedule_retry = AsyncMock()
        stop_cycle = AsyncMock()
        invalidate_consent = AsyncMock()
        with (
            patch.object(
                success_module.payment_dal,
                "update_payment_status_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                success_module.auto_renew_dal,
                "record_provider_cancellation",
                AsyncMock(),
            ),
            patch.object(
                success_module.auto_renew_dal,
                "get_cycle",
                AsyncMock(return_value=cycle),
            ),
            patch.object(
                success_module.auto_renew_dal,
                "schedule_financial_retry",
                schedule_retry,
            ),
            patch.object(
                success_module.auto_renew_dal,
                "stop_cycle",
                stop_cycle,
            ),
            patch.object(
                success_module.subscription_dal,
                "invalidate_user_auto_renew_consent",
                invalidate_consent,
            ),
        ):
            payload = await success_module.process_cancelled_payment(
                AsyncMock(),
                cast(Any, SimpleNamespace()),
                {
                    "id": "yk-22",
                    "status": "canceled",
                    "metadata": {"user_id": "42", "payment_db_id": "22"},
                    "cancellation_details": {
                        "party": "yoo_money",
                        "reason": reason,
                    },
                },
                cast(Any, SimpleNamespace()),
                cast(
                    Any,
                    _settings(AUTO_RENEW_RETRY_ENABLED=retry_enabled),
                ),
            )
        return payload, schedule_retry, stop_cycle, invalidate_consent

    async def test_allowlisted_decline_schedules_exactly_one_financial_retry(self) -> None:
        payload, schedule_retry, stop_cycle, invalidate_consent = await self._cancel(
            "insufficient_funds"
        )

        assert payload is not None
        self.assertTrue(payload["auto_renew_retry_scheduled"])
        self.assertEqual(payload["message_key"], "autorenew_retry_scheduled")
        schedule_retry.assert_awaited_once()
        stop_cycle.assert_not_awaited()
        invalidate_consent.assert_not_awaited()

    async def test_revoked_permission_disables_consent_and_never_retries(self) -> None:
        payload, schedule_retry, stop_cycle, invalidate_consent = await self._cancel(
            "permission_revoked"
        )

        assert payload is not None
        self.assertFalse(payload["auto_renew_retry_scheduled"])
        schedule_retry.assert_not_awaited()
        invalidate_consent.assert_awaited_once()
        invalidate_call = invalidate_consent.await_args
        assert invalidate_call is not None
        self.assertTrue(invalidate_call.kwargs["disable"])
        stop_cycle.assert_awaited_once()

    async def test_unknown_decline_reason_stops_without_retry(self) -> None:
        payload, schedule_retry, stop_cycle, _ = await self._cancel("fraud_suspected")

        assert payload is not None
        self.assertFalse(payload["auto_renew_retry_scheduled"])
        schedule_retry.assert_not_awaited()
        stop_cycle.assert_awaited_once()

    async def test_second_financial_failure_is_final(self) -> None:
        payload, schedule_retry, stop_cycle, _ = await self._cancel(
            "insufficient_funds",
            financial_attempts=2,
        )

        assert payload is not None
        self.assertFalse(payload["auto_renew_retry_scheduled"])
        schedule_retry.assert_not_awaited()
        stop_cycle.assert_awaited_once()


class AutoRenewDalTests(IsolatedAsyncioTestCase):
    async def test_due_cycle_claim_uses_skip_locked_and_a_bounded_lease(self) -> None:
        result = SimpleNamespace(scalar_one_or_none=lambda: None)
        session = AsyncMock()
        session.execute.return_value = result

        claimed = await auto_renew_dal.claim_due_cycle(
            session,
            11,
            lease_seconds=90,
        )

        self.assertIsNone(claimed)
        statement = session.execute.await_args.args[0]
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()
        self.assertIn("for update skip locked", sql)
        self.assertIn("auto_renew_cycles.cycle_id = 11", sql)

    async def test_balance_candidates_exclude_existing_cycles_on_the_same_utc_date(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(all=list)
        await auto_renew_dal.list_due_subscriptions(
            session, providers=("user_balance",), hours_ahead=24, limit=50, initial_only=True
        )
        statement = session.execute.await_args.args[0]
        sql = str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        ).lower()
        self.assertIn("subscriptions.auto_renew_enabled is true", sql)
        self.assertIn("not (exists", sql)
        self.assertIn("auto_renew_cycles.subscription_id = subscriptions.subscription_id", sql)
        self.assertIn("cycle_anchor = cast(timezone('utc', subscriptions.end_date) as date)", sql)


class AutoRenewSchedulerTests(IsolatedAsyncioTestCase):
    async def test_first_balance_charge_runs_with_default_recovery_flags(self) -> None:
        await self._check_balance_charge(scheduler=False)

    async def test_external_dry_run_does_not_prevent_first_balance_charge(self) -> None:
        await self._check_balance_charge(scheduler=True)

    async def _check_balance_charge(self, *, scheduler: bool) -> None:
        settings = cast(
            Settings,
            _settings(
                AUTO_RENEW_RETRY_ENABLED=False,
                AUTO_RENEW_RETRY_DRY_RUN=True,
                AUTO_RENEW_SCHEDULER_ENABLED=scheduler,
            ),
        )
        sub = SimpleNamespace(
            is_active=True,
            auto_renew_enabled=True,
            provider="user_balance",
            end_date=datetime.now(UTC) + timedelta(hours=2),
        )
        external_sub = SimpleNamespace(**{**vars(sub), "provider": "yookassa"})
        service = SimpleNamespace(
            recurring_provider_services={
                provider: SimpleNamespace(recurring_active=True)
                for provider in ("partner_balance", "user_balance", "yookassa")
            },
            charge_subscription_renewal=AsyncMock(),
        )
        session = AsyncMock()
        session_factory = MagicMock()
        session_factory.return_value.__aenter__.return_value = session
        lock_context = MagicMock()
        lock_context.__aenter__.return_value = True
        worker = AutoRenewRetryWorker(settings, session_factory, cast(SubscriptionService, service))
        with (
            patch("bot.services.auto_renew_retry_worker.redis_lock", return_value=lock_context),
            patch.object(
                auto_renew_dal,
                "list_due_subscriptions",
                side_effect=lambda _session, **kwargs: [
                    auto_renew_dal.AutoRenewSubscriptionCandidate(
                        subscription_id=7 if "user_balance" in kwargs["providers"] else 8,
                        user_id=42,
                    )
                ],
            ) as due,
            patch.object(
                subscription_dal,
                "get_subscription_by_id_for_update",
                side_effect=lambda _session, sub_id: sub if sub_id == 7 else external_sub,
            ),
            patch.object(auto_renew_dal, "list_due_cycles") as retries,
        ):
            await worker.tick()

        self.assertEqual(
            [call.kwargs["providers"] for call in due.await_args_list],
            [("partner_balance", "user_balance"), ("yookassa",)]
            if scheduler
            else [("partner_balance", "user_balance")],
        )
        self.assertTrue(due.await_args_list[0].kwargs["initial_only"])
        service.charge_subscription_renewal.assert_awaited_once_with(
            session, sub, renewal_cycle_end=sub.end_date
        )
        retries.assert_not_awaited()


def test_core_worker_registers_renewal_before_a_balance_source_is_enabled() -> None:
    tasks = {task.name: task for task in main_worker._core_worker_tasks()}
    assert tasks["AutoRenewRetryWorker"].enabled is None
