import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services.subscription_service_impl import lifecycle_extension
from bot.services.tariff_worker_core import TariffWorkerCoreMixin
from tests.unit.test_subscription_service_behavior import (
    _configure_persisted_panel_echo,
    _make_service,
    _make_settings,
    _tariffs_config_payload,
)


@pytest.mark.parametrize(
    "reason",
    [
        "promo code TEST",
        "referral bonus",
        "referral_welcome_bonus",
        "admin_manual_extension",
        "bonus",
    ],
)
@pytest.mark.parametrize("state", ["new", "new_default", "trial", "paid", "legacy", "gift"])
@pytest.mark.parametrize("manual_tag", [None, "OPERATOR"])
@pytest.mark.parametrize("confirmation_fails", [False, True])
def test_period_grants_assign_and_preserve_the_effective_tariff_tag(
    monkeypatch, tmp_path, reason, state, manual_tag, confirmation_fails
):
    payload = _tariffs_config_payload()
    other = {**payload["tariffs"][0], "key": "other", "monthly_gb": 200}
    payload["tariffs"].append(other)
    service = _make_service(_make_settings(payload, str(tmp_path), TRIAL_SQUAD_UUIDS="trial-squad"))
    old_end = datetime.now(UTC) + timedelta(days=10)
    user = SimpleNamespace(user_id=42, panel_user_uuid="panel-user", managed_panel_tariff_tag=None)
    sub = SimpleNamespace(
        subscription_id=1,
        user_id=42,
        panel_user_uuid="panel-user",
        panel_subscription_uuid="panel-sub",
        end_date=old_end,
        tariff_key="other" if state == "paid" else "retired" if state == "gift" else None,
        provider="trial" if state == "trial" else "gift" if state == "gift" else "bonus",
        status_from_panel="TRIAL" if state == "trial" else "ACTIVE",
        traffic_limit_bytes=200 * 1024**3,
        tier_baseline_bytes=200 * 1024**3,
        topup_balance_bytes=0,
        premium_topup_balance_bytes=0,
        premium_topup_used_bytes=0,
        premium_used_bytes=0,
        hwid_device_limit=3,
        extra_hwid_devices=0,
        effective_monthly_price_rub=100,
        is_active=True,
        auto_renew_enabled=False,
        gift_terms_snapshot=json.dumps({"tariff": {**other, "key": "retired", "monthly_gb": 777}})
        if state == "gift"
        else None,
    )
    initial_tag = manual_tag or ("TRIAL" if state == "trial" else None)
    _configure_persisted_panel_echo(service, initial={"uuid": "panel-user", "tag": initial_tag})
    service._get_or_create_panel_user_link_details = AsyncMock(
        return_value=("panel-user", "panel-sub", "short", False)
    )
    service._take_panel_user_link_snapshot = lambda _: {"tag": initial_tag}
    service.build_effective_panel_squad_fields = AsyncMock(return_value={})
    service._hwid_device_traffic_bonus_bytes_for_sub = AsyncMock(return_value=0)
    previous_key, previous_provider = sub.tariff_key, sub.provider
    if confirmation_fails:
        service._confirmed_panel_entitlement = AsyncMock(return_value=None)

    async def update(_session, _id, values):
        for key, value in values.items():
            setattr(sub, key, value)
        return sub

    async def extend(_session, _id, end):
        sub.end_date = end
        return sub

    async def create(_session, values):
        return await update(_session, 1, values)

    dal = lifecycle_extension.subscription_dal
    monkeypatch.setattr(
        lifecycle_extension.user_dal, "get_user_by_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=None if state.startswith("new") else sub),
    )
    monkeypatch.setattr(dal, "update_subscription", AsyncMock(side_effect=update))
    monkeypatch.setattr(dal, "update_subscription_end_date", AsyncMock(side_effect=extend))
    monkeypatch.setattr(dal, "upsert_subscription", AsyncMock(side_effect=create))
    monkeypatch.setattr(dal, "deactivate_other_active_subscriptions", AsyncMock())
    monkeypatch.setattr(
        lifecycle_extension.tariff_dal, "sum_active_hwid_devices", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(lifecycle_extension.tariff_dal, "create_tariff_change", AsyncMock())

    result = asyncio.run(
        service.extend_active_subscription_days(
            AsyncMock(),
            42,
            7,
            reason,
            tariff_key=None if state == "new_default" else "standard",
            extend_hwid_devices=False,
        )
    )

    if confirmation_fails:
        assert result is None
        assert user.managed_panel_tariff_tag is None
        if not state.startswith("new"):
            assert sub.tariff_key == previous_key
            assert sub.provider == previous_provider
            assert sub.end_date == old_end
        return
    assert result is not None
    assigned = state not in {"paid", "gift"} or "admin" in reason
    expected_key = "standard" if assigned else "retired" if state == "gift" else "other"
    assert sub.tariff_key == expected_key
    assert not TariffWorkerCoreMixin._is_trial_subscription(sub)
    sent = service.panel_service.update_user_details_on_panel.await_args.args[1]
    if manual_tag:
        assert "tag" not in sent
        assert user.managed_panel_tariff_tag is None
    else:
        assert sent["tag"] == expected_key.upper()
        assert user.managed_panel_tariff_tag == expected_key.upper()
    options = service._get_or_create_panel_user_link_details.await_args.kwargs["create_options"]
    assert options.tag == expected_key
    assert options.is_trial is False


def test_unassigned_extension_keeps_trial_tag(monkeypatch, tmp_path):
    service = _make_service(_make_settings(_tariffs_config_payload(), str(tmp_path)))
    sub = SimpleNamespace(
        subscription_id=1,
        tariff_key=None,
        provider="trial",
        status_from_panel="ACTIVE",
        end_date=datetime.now(UTC) + timedelta(days=2),
        traffic_limit_bytes=0,
        hwid_device_limit=1,
        extra_hwid_devices=0,
    )
    user = SimpleNamespace(user_id=42, panel_user_uuid="panel-user", managed_panel_tariff_tag=None)
    service._get_or_create_panel_user_link_details = AsyncMock(
        return_value=("panel-user", "panel-sub", "short", False)
    )
    service._take_panel_user_link_snapshot = lambda _: {"tag": None}
    _configure_persisted_panel_echo(service)
    monkeypatch.setattr(
        lifecycle_extension.user_dal, "get_user_by_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        lifecycle_extension.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=sub),
    )
    monkeypatch.setattr(
        lifecycle_extension.subscription_dal,
        "update_subscription_end_date",
        AsyncMock(return_value=sub),
    )
    monkeypatch.setattr(
        lifecycle_extension.subscription_dal, "update_subscription", AsyncMock(return_value=sub)
    )

    assert asyncio.run(
        service.extend_active_subscription_days(AsyncMock(), 42, 2, extend_hwid_devices=False)
    )
    assert service.panel_service.update_user_details_on_panel.await_args.args[1]["tag"] == "TRIAL"
    assert user.managed_panel_tariff_tag == "TRIAL"
    assert sub.provider == "trial"
