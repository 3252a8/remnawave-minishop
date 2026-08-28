import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.tariff_worker_shared import resolve_flexible_limit_baseline


class FlexibleLimitBaselineTests(unittest.IsolatedAsyncioTestCase):
    async def test_future_window_preserves_current_baseline(self) -> None:
        now = datetime(2026, 8, 28, 12, tzinfo=UTC)
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = now + timedelta(days=2)

        baseline = await resolve_flexible_limit_baseline(
            session,
            subscription_id=652,
            kind="traffic",
            at=now,
            active_baseline=None,
            stored_baseline=1000,
            default_baseline=500,
            preserve_without_history=True,
        )

        self.assertEqual(baseline, 1000)
        statement = session.scalar.await_args.args[0]
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()
        self.assertIn("min(flexible_traffic_limits.valid_from)", sql)
        self.assertIn("flexible_traffic_limits.subscription_id = 652", sql)
        self.assertIn("flexible_traffic_limits.kind = 'traffic'", sql)

    async def test_expired_window_returns_to_tariff_default(self) -> None:
        now = datetime(2026, 8, 28, 12, tzinfo=UTC)
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = now - timedelta(days=30)

        baseline = await resolve_flexible_limit_baseline(
            session,
            subscription_id=652,
            kind="traffic",
            at=now,
            active_baseline=None,
            stored_baseline=1000,
            default_baseline=500,
            preserve_without_history=True,
        )

        self.assertEqual(baseline, 500)

    async def test_no_premium_history_tracks_tariff_default(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = None

        baseline = await resolve_flexible_limit_baseline(
            session,
            subscription_id=652,
            kind="premium_traffic",
            at=datetime(2026, 8, 28, 12, tzinfo=UTC),
            active_baseline=None,
            stored_baseline=50,
            default_baseline=25,
            preserve_without_history=False,
        )

        self.assertEqual(baseline, 25)

    async def test_active_window_wins_without_history_lookup(self) -> None:
        session = AsyncMock(spec=AsyncSession)

        baseline = await resolve_flexible_limit_baseline(
            session,
            subscription_id=652,
            kind="traffic",
            at=datetime(2026, 8, 28, 12, tzinfo=UTC),
            active_baseline=1000,
            stored_baseline=500,
            default_baseline=500,
            preserve_without_history=True,
        )

        self.assertEqual(baseline, 1000)
        session.scalar.assert_not_awaited()
