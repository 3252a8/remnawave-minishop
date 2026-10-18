import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot.services.tariff_worker_prefetch import prefetch_premium_periods
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
