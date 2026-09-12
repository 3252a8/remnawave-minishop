import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.services.tariff_worker import TariffTrafficWorker
from config.tariffs_config import TariffsConfig


def _tariffs_config() -> TariffsConfig:
    return TariffsConfig.model_validate(
        {
            "default_tariff": "standard",
            "tariffs": [
                {
                    "key": "standard",
                    "names": {"en": "Standard"},
                    "descriptions": {"en": "Standard"},
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "prices_rub": {"1": 100},
                    "enabled_periods": [1],
                    "enabled": True,
                }
            ],
        }
    )


def _subscription() -> SimpleNamespace:
    return SimpleNamespace(
        subscription_id=1,
        user_id=42,
        panel_user_uuid="panel-user",
        tariff_key="standard",
        provider="payment",
        status_from_panel="ACTIVE",
        gift_terms_snapshot=None,
        is_active=True,
        end_date=datetime.now(UTC) + timedelta(days=30),
    )


def _worker(panel_service: SimpleNamespace) -> TariffTrafficWorker:
    return TariffTrafficWorker(
        settings=SimpleNamespace(tariffs_config=_tariffs_config()),
        session_factory=SimpleNamespace(),
        panel_service=panel_service,
        subscription_service=SimpleNamespace(),
    )


def test_reconciliation_preserves_manual_remnawave_tag() -> None:
    db_user = SimpleNamespace(
        user_id=42,
        panel_user_uuid="panel-user",
        managed_panel_tariff_tag="old-tariff",
    )
    result = SimpleNamespace(all=lambda: [(db_user, _subscription())])
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    panel_service = SimpleNamespace(
        get_user_by_uuid=AsyncMock(return_value={"uuid": "panel-user", "tag": "operator"}),
        update_user_details_on_panel=AsyncMock(),
    )

    asyncio.run(_worker(panel_service).panel_tariff_tag_cleanup_tick(session))

    panel_service.update_user_details_on_panel.assert_not_awaited()
    assert db_user.managed_panel_tariff_tag is None


def test_reconciliation_sets_and_confirms_missing_tariff_tag() -> None:
    db_user = SimpleNamespace(
        user_id=42,
        panel_user_uuid="panel-user",
        managed_panel_tariff_tag=None,
    )
    result = SimpleNamespace(all=lambda: [(db_user, _subscription())])
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    panel_service = SimpleNamespace(
        get_user_by_uuid=AsyncMock(
            side_effect=[
                {"uuid": "panel-user", "tag": None},
                {"uuid": "panel-user", "tag": "STANDARD"},
            ]
        ),
        update_user_details_on_panel=AsyncMock(return_value={"tag": "STANDARD"}),
    )

    asyncio.run(_worker(panel_service).panel_tariff_tag_cleanup_tick(session))

    panel_service.update_user_details_on_panel.assert_awaited_once_with(
        "panel-user",
        {"tag": "STANDARD"},
    )
    assert db_user.managed_panel_tariff_tag == "STANDARD"
