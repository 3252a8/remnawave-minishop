import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from config.tariffs_config import TariffsConfig
from db.migrator import MIGRATIONS
from db.tariff_squad_sync import (
    snapshot_previous_tariff_squads,
    tariff_squad_override_detection_uuids,
)


def _config(squad_uuids: list[str], premium_squad_uuids: list[str]) -> TariffsConfig:
    return TariffsConfig.model_validate(
        {
            "default_tariff": "standard",
            "tariffs": [
                {
                    "key": "standard",
                    "names": {"en": "Standard"},
                    "descriptions": {"en": "Standard"},
                    "squad_uuids": squad_uuids,
                    "premium_squad_uuids": premium_squad_uuids,
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "prices_rub": {"1": 100},
                    "enabled_periods": [1],
                    "enabled": True,
                }
            ],
        }
    )


def test_tariff_squad_snapshot_migration_is_registered() -> None:
    assert "0076_track_tariff_managed_squads" in [migration.id for migration in MIGRATIONS]


def test_override_detection_keeps_previous_and_current_tariff_squads_managed() -> None:
    subscription = SimpleNamespace(tariff_managed_squad_uuids='["old-base","old-premium"]')
    tariff = _config(["new-base"], ["new-premium"]).default

    assert tariff_squad_override_detection_uuids(subscription, tariff) == [
        "old-base",
        "old-premium",
        "new-base",
        "new-premium",
    ]


def test_catalog_edit_snapshots_previous_squads_before_worker_reconciliation() -> None:
    subscription = SimpleNamespace(
        tariff_key="standard",
        tariff_managed_squad_uuids='["pending-old"]',
    )
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [subscription])
    )

    changed = asyncio.run(
        snapshot_previous_tariff_squads(
            session,
            _config(["old-base"], ["old-premium"]),
            _config(["new-base"], ["new-premium"]),
        )
    )

    assert changed == 1
    assert json.loads(subscription.tariff_managed_squad_uuids) == [
        "pending-old",
        "old-base",
        "old-premium",
    ]
    session.flush.assert_awaited_once()
