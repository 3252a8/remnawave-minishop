from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import main_worker
from sqlalchemy.dialects import postgresql

from bot.services.yookassa_reconciliation_worker import YooKassaReconciliationWorker
from db.dal import payment_dal
from db.dal.payment_dal import YooKassaReconciliationCandidate


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionFactory:
    def __init__(self) -> None:
        self.sessions: list[AsyncMock] = []

    def __call__(self) -> _SessionContext:
        session = AsyncMock()
        self.sessions.append(session)
        return _SessionContext(session)


def _candidate() -> YooKassaReconciliationCandidate:
    return YooKassaReconciliationCandidate(payment_id=42, provider_payment_id="yk-42")


def _provider_payload(*, status: str = "succeeded", paid: bool = True) -> dict[str, Any]:
    return {
        "id": "yk-42",
        "status": status,
        "paid": paid,
        "amount_value": 299.0,
        "amount_currency": "RUB",
        "metadata": {
            "payment_db_id": "42",
            "user_id": "1001",
            "subscription_months": "1",
            "sale_mode": "subscription",
        },
    }


class YooKassaReconciliationWorkerTests(IsolatedAsyncioTestCase):
    def _worker(
        self,
        payload: dict[str, Any] | None,
    ) -> tuple[YooKassaReconciliationWorker, AsyncMock, _SessionFactory]:
        service = SimpleNamespace(configured=True, get_payment_info=AsyncMock(return_value=payload))
        session_factory = _SessionFactory()
        worker = YooKassaReconciliationWorker(
            cast(Any, SimpleNamespace()),
            cast(Any, session_factory),
            cast(Any, service),
            cast(Any, SimpleNamespace()),
            cast(Any, SimpleNamespace()),
            cast(Any, SimpleNamespace()),
            cast(Any, SimpleNamespace()),
            cast(Any, SimpleNamespace()),
            None,
        )
        return worker, service.get_payment_info, session_factory

    async def test_succeeded_payment_is_finalized_and_emitted(self) -> None:
        worker, get_payment_info, session_factory = self._worker(_provider_payload())
        event_payload = {"user_id": 1001, "payment_db_id": 42}

        with (
            patch.object(
                payment_dal,
                "list_yookassa_reconciliation_candidates",
                AsyncMock(return_value=[_candidate()]),
            ),
            patch(
                "bot.services.yookassa_reconciliation_worker.process_successful_payment",
                AsyncMock(return_value=event_payload),
            ) as process_success,
            patch(
                "bot.services.yookassa_reconciliation_worker.emit_yookassa_success_events",
                AsyncMock(),
            ) as emit_success,
        ):
            await worker.tick()

        get_payment_info.assert_awaited_once_with("yk-42")
        normalized_payload = process_success.await_args.args[2]
        self.assertEqual(
            normalized_payload["amount"],
            {"value": "299.0", "currency": "RUB"},
        )
        self.assertEqual(len(session_factory.sessions), 2)
        session_factory.sessions[1].commit.assert_awaited_once()
        emit_success.assert_awaited_once_with(event_payload)

    async def test_duplicate_success_is_committed_without_duplicate_event(self) -> None:
        worker, _, session_factory = self._worker(_provider_payload())

        with (
            patch.object(
                payment_dal,
                "list_yookassa_reconciliation_candidates",
                AsyncMock(return_value=[_candidate()]),
            ),
            patch(
                "bot.services.yookassa_reconciliation_worker.process_successful_payment",
                AsyncMock(return_value=None),
            ) as process_success,
            patch(
                "bot.services.yookassa_reconciliation_worker.emit_yookassa_success_events",
                AsyncMock(),
            ) as emit_success,
        ):
            await worker.tick()

        process_success.assert_awaited_once()
        session_factory.sessions[1].commit.assert_awaited_once()
        emit_success.assert_not_awaited()

    async def test_pending_payment_is_deferred_for_a_later_poll(self) -> None:
        worker, _, session_factory = self._worker(_provider_payload(status="pending", paid=False))

        with (
            patch.object(
                payment_dal,
                "list_yookassa_reconciliation_candidates",
                AsyncMock(return_value=[_candidate()]),
            ),
            patch.object(
                payment_dal,
                "mark_yookassa_reconciliation_checked",
                AsyncMock(),
            ) as mark_checked,
        ):
            await worker.tick()

        mark_checked.assert_awaited_once_with(session_factory.sessions[1], 42)
        session_factory.sessions[1].commit.assert_awaited_once()

    async def test_transient_empty_response_is_deferred(self) -> None:
        worker, _, _ = self._worker(None)

        with (
            patch.object(
                payment_dal,
                "list_yookassa_reconciliation_candidates",
                AsyncMock(return_value=[_candidate()]),
            ),
            patch.object(
                payment_dal,
                "mark_yookassa_reconciliation_checked",
                AsyncMock(),
            ) as mark_checked,
        ):
            await worker.tick()

        mark_checked.assert_awaited_once()

    async def test_cancelled_payment_is_finalized_and_emitted(self) -> None:
        worker, _, session_factory = self._worker(_provider_payload(status="canceled", paid=False))
        event_payload = {
            "user_id": 1001,
            "payment_db_id": 42,
            "provider": "yookassa",
            "status": "canceled",
        }

        with (
            patch.object(
                payment_dal,
                "list_yookassa_reconciliation_candidates",
                AsyncMock(return_value=[_candidate()]),
            ),
            patch(
                "bot.services.yookassa_reconciliation_worker.process_cancelled_payment",
                AsyncMock(return_value=event_payload),
            ) as process_cancelled,
            patch(
                "bot.services.yookassa_reconciliation_worker.events.emit_model",
                AsyncMock(),
            ) as emit_model,
        ):
            await worker.tick()

        process_cancelled.assert_awaited_once()
        session_factory.sessions[1].commit.assert_awaited_once()
        emit_model.assert_awaited_once()

    async def test_mismatched_provider_or_metadata_id_is_not_finalized(self) -> None:
        for payload in (
            {**_provider_payload(), "id": "yk-other"},
            {
                **_provider_payload(),
                "metadata": {**_provider_payload()["metadata"], "payment_db_id": "43"},
            },
        ):
            with self.subTest(payload=payload):
                worker, _, _ = self._worker(payload)
                with (
                    patch.object(
                        payment_dal,
                        "list_yookassa_reconciliation_candidates",
                        AsyncMock(return_value=[_candidate()]),
                    ),
                    patch.object(
                        payment_dal,
                        "mark_yookassa_reconciliation_checked",
                        AsyncMock(),
                    ) as mark_checked,
                    patch(
                        "bot.services.yookassa_reconciliation_worker.process_successful_payment",
                        AsyncMock(),
                    ) as process_success,
                ):
                    await worker.tick()

                mark_checked.assert_awaited_once()
                process_success.assert_not_awaited()


class YooKassaReconciliationDalTests(IsolatedAsyncioTestCase):
    async def test_candidate_query_is_bounded_and_provider_scoped(self) -> None:
        result = SimpleNamespace(all=lambda: [(42, "yk-42")])
        session = AsyncMock()
        session.execute.return_value = result

        candidates = await payment_dal.list_yookassa_reconciliation_candidates(
            session,
            limit=25,
            grace_seconds=60,
        )

        self.assertEqual(candidates, [_candidate()])
        statement = session.execute.await_args.args[0]
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()
        self.assertIn("lower(payments.provider) = 'yookassa'", sql)
        self.assertIn("pending_yookassa", sql)
        self.assertIn("waiting_for_capture", sql)
        self.assertIn(
            "coalesce(payments.yookassa_payment_id, payments.provider_payment_id) is not null",
            sql,
        )
        self.assertIn("limit 25", sql)


def test_core_worker_registers_yookassa_reconciliation() -> None:
    assert "YooKassaReconciliationWorker" in {
        task.name for task in main_worker._core_worker_tasks()
    }
