import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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


@pytest.mark.parametrize(
    "provider", ["payment", "referral", "promo", "bonus", "admin", "gift", "trial"]
)
def test_reconciliation_sets_and_confirms_missing_tariff_tag(provider) -> None:
    db_user = SimpleNamespace(
        user_id=42,
        panel_user_uuid="panel-user",
        managed_panel_tariff_tag=None,
    )
    sub = _subscription()
    sub.provider = provider
    expected_tag = "TRIAL" if provider == "trial" else "STANDARD"
    result = SimpleNamespace(all=lambda: [(db_user, sub)])
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    panel_service = SimpleNamespace(
        get_user_by_uuid=AsyncMock(
            side_effect=[
                {"uuid": "panel-user", "tag": None},
                {"uuid": "panel-user", "tag": expected_tag},
            ]
        ),
        update_user_details_on_panel=AsyncMock(return_value={"tag": expected_tag}),
    )

    asyncio.run(_worker(panel_service).panel_tariff_tag_cleanup_tick(session))

    panel_service.update_user_details_on_panel.assert_awaited_once_with(
        "panel-user",
        {"tag": expected_tag},
    )
    assert db_user.managed_panel_tariff_tag == expected_tag


@pytest.mark.parametrize(
    ("key", "status", "current", "expected"),
    [
        (None, "TRIAL", None, "TRIAL"),
        ("retired", "ACTIVE", None, "RETIRED"),
        ("standard", "ACTIVE", "TRIAL", "STANDARD"),
        (None, "ACTIVE", "TRIAL", None),
    ],
)
def test_reconciliation_handles_legacy_bindings_and_trial_transitions(
    key, status, current, expected
):
    user = SimpleNamespace(
        user_id=42, panel_user_uuid="panel-user", managed_panel_tariff_tag=current
    )
    sub = _subscription()
    sub.tariff_key, sub.status_from_panel = key, status
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(user, sub)]))
    )
    panel = SimpleNamespace(
        get_user_by_uuid=AsyncMock(side_effect=[{"tag": current}, {"tag": expected}]),
        update_user_details_on_panel=AsyncMock(return_value={"tag": expected}),
    )
    asyncio.run(_worker(panel).panel_tariff_tag_cleanup_tick(session))
    panel.update_user_details_on_panel.assert_awaited_once_with("panel-user", {"tag": expected})
    assert user.managed_panel_tariff_tag == expected


@pytest.mark.parametrize("tag", ["TRIAL", "STANDARD"])
def test_reconciliation_clears_expired_or_revoked_access(tag):
    user = SimpleNamespace(user_id=42, panel_user_uuid="panel-user", managed_panel_tariff_tag=tag)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(user, None)]))
    )
    panel = SimpleNamespace(
        get_user_by_uuid=AsyncMock(side_effect=[{"tag": tag}, {"tag": None}]),
        update_user_details_on_panel=AsyncMock(return_value={"tag": None}),
    )
    asyncio.run(_worker(panel).panel_tariff_tag_cleanup_tick(session))
    panel.update_user_details_on_panel.assert_awaited_once_with("panel-user", {"tag": None})
    assert user.managed_panel_tariff_tag is None


def test_reconciliation_continues_after_one_user_update_fails():
    users = [
        SimpleNamespace(user_id=i, panel_user_uuid=str(i), managed_panel_tariff_tag=None)
        for i in [1, 2]
    ]
    rows = [(user, _subscription()) for user in users]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    panel = SimpleNamespace(
        get_all_panel_users=AsyncMock(return_value=[{"uuid": "1"}, {"uuid": "2"}]),
        get_user_by_uuid=AsyncMock(return_value={"tag": "STANDARD"}),
        update_user_details_on_panel=AsyncMock(
            side_effect=[RuntimeError("unavailable"), {"tag": "STANDARD"}]
        ),
    )
    asyncio.run(_worker(panel).panel_tariff_tag_cleanup_tick(session))
    assert panel.update_user_details_on_panel.await_count == 2
    assert users[0].managed_panel_tariff_tag is None
    assert users[1].managed_panel_tariff_tag == "STANDARD"
