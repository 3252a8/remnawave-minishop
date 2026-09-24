"""Exercise transaction boundaries and replays against a real SQL database."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.plugins.extensions import (
    DurableSubscription,
    ExtensionContributions,
    ExtensionError,
    FulfillmentResult,
    JobHandler,
    ProductProvider,
    ProductQuote,
    UserContext,
)
from bot.plugins.extensions.commerce import accept_payment, create_order, request_refund
from bot.plugins.extensions.jobs import enqueue, publish, run_once
from bot.plugins.extensions.registry import ExtensionRegistry, set_registry
from bot.plugins.extensions.rewards import Reward, grant
from db.base import Base
from db.dal import extension_accounts_dal, payment_dal, user_balance_dal
from db.extension_models import ExtensionOperation, ExtensionOrder
from db.models import PromoCode, Subscription, User


class ExtensionOperationsTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")

        @event.listens_for(self.engine.sync_engine, "connect")
        def disable_legacy_transactions(connection, _record):
            connection.isolation_level = None

        @event.listens_for(self.engine.sync_engine, "begin")
        def begin(connection):
            connection.exec_driver_sql("BEGIN")

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.registry = ExtensionRegistry()
        set_registry(self.registry)
        self.handler = AsyncMock(return_value={"done": True})
        self.fulfill = AsyncMock(return_value=FulfillmentResult(reference="external-42"))
        self.revoke = AsyncMock()
        self.quote = AsyncMock(
            return_value=ProductQuote(
                title="External service",
                amount_minor=1250,
                currency="RUB",
                terms={"plan": "one"},
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        self.contributions = ExtensionContributions(
            jobs=(JobHandler("delivery", self.handler),),
            events=(DurableSubscription("payment.succeeded", "delivery"),),
            products=(ProductProvider("service", self.quote, self.fulfill, self.revoke),),
            permissions=frozenset(
                {"rewards.balance", "rewards.days", "rewards.traffic", "rewards.codes"}
            ),
        )
        self.registry.register("test-owner", "1.0", self.contributions)
        self.runtime = SimpleNamespace(require_session_factory=lambda: self.sessions)
        self.generation = patch(
            "bot.plugins.extensions.jobs.generation_is_current", return_value=True
        )
        self.generation.start()
        self.operation_generation = patch(
            "bot.plugins.packages.generation_is_current", return_value=True
        )
        self.operation_generation.start()
        async with self.sessions.begin() as session:
            session.add_all([User(user_id=1), User(user_id=2)])

    async def asyncTearDown(self):
        self.generation.stop()
        self.operation_generation.stop()
        set_registry(ExtensionRegistry())
        await self.engine.dispose()

    async def order(self, user_id=1, key="purchase"):
        async with self.sessions.begin() as session:
            return await create_order(
                UserContext(session, user_id, "en"),
                product="test-owner:service",
                options={},
                idempotency_key=key,
            )

    async def pay(self, order):
        async with self.sessions.begin() as session:
            payment = await payment_dal.create_payment_record(
                session,
                {
                    "user_id": int(order.user_id),
                    "amount": 12.50,
                    "currency": "RUB",
                    "description": "External service",
                    "provider": "test",
                    "status": "pending",
                    "sale_mode": f"extension|{order.id}",
                },
            )
            await accept_payment(session, payment)
            await payment_dal.update_payment_status_by_db_id(
                session, payment.payment_id, "succeeded"
            )
            return payment

    async def test_enqueue_rolls_back_with_business_transaction(self):
        async with self.sessions() as session:
            await enqueue(
                session, job="test-owner:delivery", idempotency_key="ticket-1", payload={}
            )
            await session.rollback()
        async with self.sessions() as session:
            self.assertEqual(
                await session.scalar(select(func.count()).select_from(ExtensionOperation)), 0
            )

    async def test_event_replay_is_once_and_payload_change_conflicts(self):
        async with self.sessions.begin() as session:
            for _ in range(2):
                await publish(
                    session, event="payment.succeeded", event_id="9", payload={"amount": 5}
                )
            with self.assertRaisesRegex(ExtensionError, "idempotency_conflict"):
                await publish(
                    session, event="payment.succeeded", event_id="9", payload={"amount": 6}
                )
        self.assertTrue(await run_once(self.runtime))
        self.assertFalse(await run_once(self.runtime))
        self.handler.assert_awaited_once()

    async def test_disabled_owner_keeps_work_until_reenabled(self):
        async with self.sessions.begin() as session:
            operation = await enqueue(
                session, job="test-owner:delivery", idempotency_key="queued", payload={}
            )
        set_registry(ExtensionRegistry())
        await run_once(self.runtime)
        async with self.sessions.begin() as session:
            row = await session.get(ExtensionOperation, operation.id)
            self.assertEqual((row.state, row.attempts), ("blocked", 0))
            row.not_before = datetime.now(UTC) - timedelta(seconds=1)
        set_registry(self.registry)
        await run_once(self.runtime)
        self.handler.assert_awaited_once()

    async def test_failure_retries_same_operation_without_leaking_exception(self):
        self.handler.side_effect = [RuntimeError("credential=secret"), {"done": True}]
        async with self.sessions.begin() as session:
            operation = await enqueue(
                session, job="test-owner:delivery", idempotency_key="retry", payload={}
            )
        await run_once(self.runtime)
        async with self.sessions.begin() as session:
            row = await session.get(ExtensionOperation, operation.id)
            self.assertEqual(row.error_code, "extension_operation_failed")
            row.not_before = datetime.now(UTC) - timedelta(seconds=1)
        await run_once(self.runtime)
        ids = [call.args[0].operation_id for call in self.handler.await_args_list]
        self.assertEqual(ids, [operation.id, operation.id])

    async def test_expired_lease_is_recovered_and_fenced(self):
        async with self.sessions.begin() as session:
            operation = await enqueue(
                session, job="test-owner:delivery", idempotency_key="lease", payload={}
            )
            operation.state = "running"
            operation.lease_token = "old"
            operation.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await run_once(self.runtime)
        self.assertNotEqual(self.handler.await_args.args[0].lease_token, "old")
        async with self.sessions() as session:
            self.assertEqual(
                (await session.get(ExtensionOperation, operation.id)).state, "succeeded"
            )

    async def test_lost_lease_cannot_commit_a_stale_handler_result(self):
        async def replaced(operation, _payload):
            async with self.sessions.begin() as session:
                row = await session.get(ExtensionOperation, operation.operation_id)
                row.lease_token = "replacement"
                row.state = "queued"
            return {"stale": True}

        self.handler.side_effect = replaced
        async with self.sessions.begin() as session:
            operation = await enqueue(
                session, job="test-owner:delivery", idempotency_key="fence", payload={}
            )
        await run_once(self.runtime)
        async with self.sessions() as session:
            row = await session.get(ExtensionOperation, operation.id)
            self.assertEqual(row.state, "queued")
            self.assertIsNone(row.result_json)

    async def test_period_grant_retries_panel_sync_without_adding_days_again(self):
        end = datetime.now(UTC) + timedelta(days=10)
        sync = AsyncMock(side_effect=[False, True])
        self.runtime.require_subscription_service = lambda: SimpleNamespace(
            sync_main_traffic_limit_to_panel=sync
        )
        async with self.sessions.begin() as session:
            session.add(
                Subscription(user_id=1, panel_user_uuid="panel-1", end_date=end, is_active=True)
            )
        async with self.sessions.begin() as session:
            operation = await grant(
                session,
                owner="test-owner",
                user_id=1,
                idempotency_key="period",
                reward=Reward(kind="days", amount=3),
            )
        await run_once(self.runtime)
        async with self.sessions.begin() as session:
            row = await session.get(ExtensionOperation, operation.id)
            self.assertIn('"applied":true', row.result_json)
            row.not_before = datetime.now(UTC) - timedelta(seconds=1)
            await grant(
                session,
                owner="test-owner",
                user_id=1,
                idempotency_key="period",
                reward=Reward(kind="days", amount=3),
            )
        await run_once(self.runtime)
        async with self.sessions() as session:
            subscription = await session.scalar(
                select(Subscription).where(Subscription.user_id == 1)
            )
            self.assertEqual(subscription.end_date.replace(tzinfo=UTC), end + timedelta(days=3))
        self.assertEqual(sync.await_count, 2)

    async def test_personal_code_grant_is_single_use_and_replayed(self):
        async with self.sessions.begin() as session:
            for _ in range(2):
                await grant(
                    session,
                    owner="test-owner",
                    user_id=1,
                    idempotency_key="code",
                    reward=Reward(kind="codes", amount=7),
                )
            rows = (await session.scalars(select(PromoCode))).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].max_activations, 1)

    async def test_payment_captures_event_delivery_before_worker_and_disable(self):
        await self.pay(await self.order())
        set_registry(ExtensionRegistry())
        async with self.sessions() as session:
            rows = (
                await session.scalars(
                    select(ExtensionOperation).where(ExtensionOperation.kind == "delivery")
                )
            ).all()
            self.assertEqual(len(rows), 1)
            self.assertIn('"event":"payment.succeeded"', rows[0].payload_json)

    async def test_repeated_order_uses_original_quote(self):
        first = await self.order()
        self.quote.side_effect = RuntimeError("catalog offline")
        second = await self.order()
        self.assertEqual(first.id, second.id)
        self.quote.assert_awaited_once()
        async with self.sessions() as session:
            with self.assertRaisesRegex(ExtensionError, "idempotency_conflict"):
                await create_order(
                    UserContext(session, 1, "en"),
                    product="test-owner:service",
                    options={"changed": True},
                    idempotency_key="purchase",
                )

    async def test_payment_amount_and_owner_cannot_be_substituted(self):
        order = await self.order()
        async with self.sessions() as session:
            payment = await payment_dal.create_payment_record(
                session,
                {
                    "user_id": 1,
                    "amount": 1,
                    "currency": "RUB",
                    "provider": "test",
                    "status": "pending",
                    "sale_mode": f"extension|{order.id}",
                },
            )
            with self.assertRaisesRegex(ExtensionError, "payment_mismatch"):
                await accept_payment(session, payment)
            payment.user_id = 2
            with self.assertRaisesRegex(ExtensionError, "order_not_found"):
                await accept_payment(session, payment)

    async def test_paid_invoice_survives_disable_and_repeated_webhook(self):
        order = await self.order()
        set_registry(ExtensionRegistry())
        payment = await self.pay(order)
        async with self.sessions.begin() as session:
            await accept_payment(session, payment)
        set_registry(self.registry)
        await run_once(self.runtime)
        self.fulfill.assert_awaited_once()
        self.assertEqual(self.fulfill.await_args.args[1].quote.amount_minor, 1250)

    async def test_refund_credits_only_after_revocation_and_once(self):
        order = await self.order()
        await self.pay(order)
        for _ in range(2):
            await run_once(self.runtime)
        self.revoke.side_effect = RuntimeError("remote unavailable")
        async with self.sessions.begin() as session:
            await request_refund(session, order_id=order.id, user_id=1)
            await request_refund(session, order_id=order.id, user_id=1)
        await run_once(self.runtime)
        async with self.sessions.begin() as session:
            self.assertEqual(await user_balance_dal.balance_minor(session, 1, "RUB"), 0)
            row = await session.scalar(
                select(ExtensionOperation).where(ExtensionOperation.kind == "_revoke")
            )
            row.not_before = datetime.now(UTC) - timedelta(seconds=1)
        self.revoke.side_effect = None
        await run_once(self.runtime)
        async with self.sessions.begin() as session:
            await request_refund(session, order_id=order.id, user_id=1)
            self.assertEqual(await user_balance_dal.balance_minor(session, 1, "RUB"), 1250)
            self.assertEqual(
                (await session.get(ExtensionOrder, order.id)).payment_state, "refunded"
            )

    async def test_grant_rolls_back_and_replay_never_credits_twice(self):
        async with self.sessions() as session:
            await grant(
                session,
                owner="test-owner",
                user_id=1,
                idempotency_key="spin",
                reward=Reward(kind="balance", amount=10),
            )
            await session.rollback()
        async with self.sessions.begin() as session:
            self.assertEqual(await user_balance_dal.balance_minor(session, 1, "RUB"), 0)
            for _ in range(2):
                await grant(
                    session,
                    owner="test-owner",
                    user_id=1,
                    idempotency_key="spin",
                    reward=Reward(kind="balance", amount=10),
                )
            self.assertEqual(await user_balance_dal.balance_minor(session, 1, "RUB"), 10)

    async def test_merge_preserves_both_orders_and_blocks_running_operations(self):
        first, second = await self.order(1), await self.order(2)
        async with self.sessions.begin() as session:
            operation = await enqueue(
                session,
                job="test-owner:delivery",
                idempotency_key=uuid.uuid4().hex,
                payload={},
                user_id=1,
            )
            operation.state = "running"
            operation.lease_until = datetime.now(UTC) + timedelta(minutes=1)
            await session.flush()
            with self.assertRaisesRegex(ValueError, "in_progress"):
                await extension_accounts_dal.merge(session, 1, 2)
            operation.state = "queued"
            await session.flush()
            await extension_accounts_dal.merge(session, 1, 2)
        async with self.sessions() as session:
            rows = (await session.scalars(select(ExtensionOrder))).all()
            self.assertEqual({row.id for row in rows}, {first.id, second.id})
            self.assertEqual({row.user_id for row in rows}, {2})
            self.assertEqual(len({row.idempotency_key for row in rows}), 2)
