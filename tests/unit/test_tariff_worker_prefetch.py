import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot.services.tariff_worker import TariffTrafficWorker
from bot.services.tariff_worker_prefetch import prefetch_premium_periods
from config.settings import Settings
from config.tariffs_config import Tariff
from db.models import Subscription


@pytest.mark.parametrize("source", ["legacy", "missing-plan", "trial", "gift", "configured"])
def test_premium_prefetch_handles_optional_catalog_and_keeps_saved_terms(source):
    now = datetime(2026, 1, 15, tzinfo=UTC)
    tariff = Tariff(
        key="synthetic-plan",
        billing_model="period",
        monthly_gb=10,
        enabled_periods=[1],
        prices={"rub": {"1": 100}},
        premium_squad_uuids=["synthetic-squad"],
        premium_monthly_gb=5,
    )
    sub = Subscription(
        tariff_key=tariff.key if source in {"gift", "configured", "missing-plan"} else None,
        provider="gift" if source == "gift" else "trial" if source == "trial" else "manual",
        gift_terms_snapshot=json.dumps({"tariff": tariff.model_dump()})
        if source == "gift"
        else None,
    )
    config = Mock() if source == "configured" else None
    if config:
        config.require_configured.return_value = tariff
    worker = SimpleNamespace(
        settings=SimpleNamespace(tariffs_config=config),
        subscription_service=SimpleNamespace(
            _premium_accounting_period_start=Mock(return_value=now)
        ),
        _trial_premium_tariff=Mock(return_value=tariff),
        _is_trial_subscription=Mock(return_value=source == "trial"),
        _premium_node_uuids_for_tariff=AsyncMock(return_value=["synthetic-node"]),
        _premium_usage_snapshot_for_nodes=AsyncMock(),
    )
    asyncio.run(prefetch_premium_periods(worker, [sub], [{"uuid": "701"}], now))
    if source in {"legacy", "missing-plan"}:
        worker._premium_usage_snapshot_for_nodes.assert_not_awaited()
    else:
        worker._premium_usage_snapshot_for_nodes.assert_awaited_once_with(
            ["synthetic-node"], "2026-01-15", "2026-01-15"
        )
    if config:
        config.require_configured.assert_called_once_with(tariff.key)


def test_per_node_adapter_reuses_partial_snapshot_only_within_its_tick_and_period():
    async def run():
        panel = Mock(spec=["get_node_users_bandwidth_stats"])
        available = {"topUsers": [{"user": {"uuid": "u", "username": "alice"}, "total": 9}]}
        panel.get_node_users_bandwidth_stats = AsyncMock(
            side_effect=[available, None, available, available, available, available]
        )
        subscriptions = Mock()
        subscriptions._trial_premium_squad_uuids.return_value = []
        settings = Settings(
            _env_file=None, BOT_TOKEN="token", POSTGRES_USER="bench", POSTGRES_PASSWORD="bench"
        )
        worker = TariffTrafficWorker(settings, Mock(), panel, subscriptions)
        nodes = ["a", "b"]
        start, end = "2026-05-01", "2026-05-20"
        partial = await worker._premium_usage_snapshot_for_nodes(nodes, start, end)
        assert partial is not None and not partial.complete
        assert (
            await worker._premium_usage_snapshot_for_nodes(["b", "a", "b"], start, end) is partial
        )
        assert (
            await worker._premium_usage_for_user("u", nodes, start, end, panel_username="alice")
            == 9
        )
        assert (
            worker._premium_usage_with_partial_stats_floor(
                Subscription(premium_used_bytes=12), 9, nodes, start, end, same_period=True
            )
            == 12
        )
        assert await worker._premium_usage_for_user("u", nodes, start, "2026-05-21") == 18
        assert panel.get_node_users_bandwidth_stats.await_count == 4
        assert not worker._premium_usage_snapshot_cache

        # A normal fast tick drops both source lookups and their merged view.
        empty_result = Mock()
        empty_result.scalars.return_value = []
        await worker.premium_fast_tick(Mock(execute=AsyncMock(return_value=empty_result)))
        refreshed = await worker._premium_usage_snapshot_for_nodes(nodes, start, end)
        assert refreshed is not None and refreshed.complete
        assert refreshed.totals["by_uuid"]["u"] == 18
        assert panel.get_node_users_bandwidth_stats.await_count == 6

    asyncio.run(run())
