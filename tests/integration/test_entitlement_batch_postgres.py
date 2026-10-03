"""Exact entitlement boundaries and purchase interleaving on disposable PostgreSQL."""

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers.admin.sync_admin_snapshot import capture_subscription_snapshot
from bot.services.panel_api_service import PanelApiService
from bot.services.regular_topup_settlement import RegularTopupPeriod, settle_regular_topup
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.dal import subscription_dal, tariff_dal, user_panel_squad_override_dal
from db.dal.tariff_read_batch import clear_tariff_read_batch, prefetch_tariff_read_batch
from db.migrator.chain_0098_topup_period_lifetime import CHAIN_0098_TOPUP_PERIOD_LIFETIME
from db.migrator.chain_0099_regular_topup_accounting import CHAIN_0099_REGULAR_TOPUP_ACCOUNTING
from db.models import (
    Base,
    FlexibleTrafficLimit,
    HwidDevicePurchase,
    Subscription,
    TrafficTopup,
    User,
)

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")
NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


def run_scenario(scenario: Callable[[Any], Awaitable[None]]) -> None:
    async def run() -> None:
        schema = "performance_test_" + uuid.uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with factory() as session:
                session.add(User(user_id=1))
                await session.flush()
                session.add_all(
                    [
                        Subscription(
                            subscription_id=i,
                            user_id=1,
                            panel_user_uuid=f"panel-{i}",
                            end_date=NOW + timedelta(days=30),
                            premium_topup_balance_bytes=100,
                        )
                        for i in (1, 2)
                    ]
                )
                await session.commit()
            await scenario(factory)
        finally:
            await engine.dispose()
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(run())


def test_batch_matches_sql_for_overlapping_future_expired_and_empty_entitlements() -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as session:
            for start, end, amount in ((-1, 1, 100), (-1, 2, 200), (-2, 0, 500), (1, 2, 1000)):
                session.add(
                    FlexibleTrafficLimit(
                        subscription_id=1,
                        kind="premium_traffic",
                        tariff_key="test",
                        limit_bytes=amount,
                        valid_from=NOW + timedelta(days=start),
                        valid_until=NOW + timedelta(days=end),
                    )
                )
            for devices, hwid_start, hwid_end, bonus in (
                (2, None, None, None),
                (3, -1, 1, 512),
                (9, -1, 0, 0),
                (4, 1, 2, 0),
            ):
                session.add(
                    HwidDevicePurchase(
                        subscription_id=1,
                        purchased_devices=devices,
                        traffic_bonus_bytes=bonus,
                        valid_from=NOW + timedelta(days=hwid_start)
                        if hwid_start is not None
                        else None,
                        valid_until=NOW + timedelta(days=hwid_end)
                        if hwid_end is not None
                        else None,
                    )
                )
            for amount, offset, kind in (
                (100, 0, "premium_topup"),
                (200, 1, "premium_topup"),
                (999, -1, "premium_topup"),
                (888, 0, "other"),
            ):
                session.add(
                    TrafficTopup(
                        subscription_id=1,
                        purchased_bytes=amount,
                        kind=kind,
                        created_at=NOW + timedelta(seconds=offset),
                    )
                )
            await session.commit()
            subs = list(
                await session.scalars(select(Subscription).order_by(Subscription.subscription_id))
            )

            async def read() -> list[Any]:
                return [
                    (
                        await tariff_dal.get_active_flexible_traffic_limits(
                            session, subscription_id=sub.subscription_id, at=NOW
                        ),
                        await tariff_dal.get_flexible_traffic_limit_history_start(
                            session, subscription_id=sub.subscription_id, kind="premium_traffic"
                        ),
                        await tariff_dal.get_hwid_device_entitlement_summary(
                            session, subscription_id=sub.subscription_id, at=NOW
                        ),
                        await tariff_dal.sum_traffic_topups(
                            session,
                            subscription_id=sub.subscription_id,
                            kinds=["premium_topup"],
                            created_at_gte=NOW,
                        ),
                    )
                    for sub in subs
                ]

            expected = await read()
            assert expected[0][0] == {"premium_traffic": 200}
            assert expected[0][2]["active_devices"] == 5
            assert expected[0][2]["next_valid_from"] == NOW + timedelta(days=1)
            assert expected[0][3] == 300
            assert expected[1][0] == {} and expected[1][3] == 0
            await prefetch_tariff_read_batch(session, subs)
            assert await read() == expected
            assert (
                await user_panel_squad_override_dal.deactivate_panel_internal_overrides_for_squads(
                    session, user_id=1, panel_user_uuid="panel-1", squad_uuids=["managed"]
                )
                == 0
            )
            assert "tariff_read_batch" in session.info
            await tariff_dal.create_traffic_topup(
                session,
                subscription_id=1,
                payment_id=None,
                purchased_bytes=77,
                kind="premium_topup",
            )
            assert (
                await tariff_dal.sum_traffic_topups(
                    session, subscription_id=1, kinds=["premium_topup"]
                )
                == 1376
            )
            await session.rollback()

    run_scenario(scenario)


def test_reload_and_row_lock_preserve_a_purchase_between_worker_batches() -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as worker:
            stale = await worker.get(Subscription, 1)
            assert stale.premium_topup_balance_bytes == 100
            await worker.commit()
            async with factory() as purchase:
                sub = await purchase.get(Subscription, 1, with_for_update=True)
                sub.premium_topup_balance_bytes += 250
                await tariff_dal.create_traffic_topup(
                    purchase,
                    subscription_id=1,
                    payment_id=None,
                    purchased_bytes=250,
                    kind="premium_topup",
                )
                await purchase.commit()
            current = (
                await worker.scalars(
                    select(Subscription)
                    .where(Subscription.subscription_id == 1)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).one()
            await prefetch_tariff_read_batch(worker, [current])
            assert current.premium_topup_balance_bytes == 350
            assert await tariff_dal.sum_traffic_topups(worker, subscription_id=1) == 250
            current.premium_used_bytes = 40
            clear_tariff_read_batch(worker)
            await worker.commit()
        async with factory() as verify:
            saved = await verify.get(Subscription, 1)
            assert saved.premium_topup_balance_bytes == 350 and saved.premium_used_bytes == 40

    run_scenario(scenario)


def test_full_sync_does_not_overwrite_a_concurrent_extension() -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as sync:
            snapshot = await capture_subscription_snapshot(sync)
            assert snapshot is not None
            stale = await sync.get(Subscription, 1)
            original_end = stale.end_date
            async with factory() as purchase:
                sub = await purchase.get(Subscription, 1, with_for_update=True)
                sub.end_date += timedelta(days=30)
                await purchase.commit()
            applied = await subscription_dal.update_subscription(
                sync,
                1,
                {"end_date": original_end, "is_active": False},
                expected_version=snapshot.versions[1],
                refresh=False,
            )
            assert applied is None
            # An untouched row from the same snapshot is still applied.
            assert (
                await subscription_dal.update_subscription(
                    sync,
                    2,
                    {"status_from_panel": "ACTIVE"},
                    expected_version=snapshot.versions[2],
                    refresh=False,
                )
                is not None
            )
            await sync.commit()
        async with factory() as verify:
            sub = await verify.get(Subscription, 1)
            assert sub.end_date == original_end + timedelta(days=30)
            assert sub.is_active

    run_scenario(scenario)


@pytest.mark.parametrize("days", [1, 2])
def test_regular_missed_resets_use_expired_flexible_and_device_entitlements(days: int) -> None:
    async def scenario(factory: Any) -> None:
        gb = 1024**3
        start = datetime(2026, 9, 1, tzinfo=UTC)
        end = start + timedelta(days=days)
        settings = Settings(HWID_DEVICE_TRAFFIC_BONUS_GB=0)
        service = SubscriptionService(settings, PanelApiService(settings))
        source = SimpleNamespace(
            get_user_bandwidth_stats=AsyncMock(
                return_value={
                    "categories": ["2026-09-01", "2026-09-02"],
                    "sparklineData": [80 * gb, 80 * gb],
                }
            )
        )
        async with factory() as session:
            sub = await session.get(Subscription, 1)
            sub.tier_baseline_bytes = 50 * gb
            sub.topup_balance_bytes = 50 * gb
            sub.traffic_topup_accounting_state = RegularTopupPeriod(
                period_start_at=start,
                lifetime_start_bytes=480 * gb,
                allowance_bytes=50 * gb,  # the worker last ran before the purchases
                observed_used_bytes=0,
                observed_overflow_bytes=0,
                panel_user_uuid="panel-1",
                traffic_strategy="DAY",
                tariff_baseline_bytes=50 * gb,
                regular_bonus_bytes=0,
                unlimited=False,
            ).model_dump_json()
            session.add_all(
                [
                    FlexibleTrafficLimit(
                        subscription_id=1,
                        kind="traffic",
                        tariff_key="standard",
                        limit_bytes=100 * gb,
                        valid_from=start,
                        valid_until=start + timedelta(days=1),
                    ),
                    HwidDevicePurchase(
                        subscription_id=1,
                        purchased_devices=1,
                        traffic_bonus_bytes=15 * gb,
                        valid_from=start,
                        valid_until=start + timedelta(days=1),
                    ),
                ]
            )
            await session.commit()
            await prefetch_tariff_read_batch(session, [sub])
            consumed = await settle_regular_topup(
                session,
                sub,
                SimpleNamespace(monthly_bytes=50 * gb),
                subscription_service=service,
                used_bytes=0,
                panel_user_data={
                    "userTraffic": {"lifetimeUsedTrafficBytes": (480 + 80 * days) * gb}
                },
                previous_period_start=start,
                period_start=end,
                traffic_strategy="DAY",
                now=end,
                usage_source=source,
            )
            await session.commit()
            # Day one had 115 GB; day two had 50 GB and spent 30 GB of the pack.
            expected = 30 * gb if days == 2 else 0
            assert (consumed, sub.topup_balance_bytes) == (expected, 50 * gb - expected)
            await session.refresh(sub)
            state = RegularTopupPeriod.model_validate_json(sub.traffic_topup_accounting_state)
            assert (state.allowance_bytes, state.lifetime_start_bytes) == (
                50 * gb,
                (480 + 80 * days) * gb,
            )
            clear_tariff_read_batch(session)
        if days == 2:
            source.get_user_bandwidth_stats.assert_awaited_once_with(
                "panel-1", start="2026-09-01", end="2026-09-02"
            )
        else:
            source.get_user_bandwidth_stats.assert_not_awaited()

    run_scenario(scenario)


def test_regular_accounting_migrations_are_nullable_and_idempotent() -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as session:
            await session.execute(
                text("ALTER TABLE subscriptions DROP COLUMN traffic_period_lifetime_start_bytes")
            )
            await session.execute(
                text("ALTER TABLE subscriptions DROP COLUMN traffic_topup_accounting_state")
            )
            connection = await session.connection()
            migrations = [*CHAIN_0098_TOPUP_PERIOD_LIFETIME, *CHAIN_0099_REGULAR_TOPUP_ACCOUNTING]
            for _ in range(2):
                for migration in migrations:
                    await connection.run_sync(migration.upgrade)
            values = await session.execute(
                text(
                    "SELECT traffic_period_lifetime_start_bytes, "
                    "traffic_topup_accounting_state FROM subscriptions ORDER BY subscription_id"
                )
            )
            assert values.all() == [(None, None), (None, None)]
            await session.commit()

    run_scenario(scenario)
