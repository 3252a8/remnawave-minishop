from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

from bot.app.web.webapp import billing_payments
from bot.payment_providers.base import PaymentProviderSpec
from bot.payment_providers.shared.entitlement_context import (
    EntitlementContextError,
    EntitlementPreflightStatus,
    build_entitlement_context_snapshot,
    parse_entitlement_context_snapshot,
    preflight_payment_entitlement,
)
from tests.support.settings_stub import settings_stub


def _trial(tariff_key: str | None, *, provider: str = "trial") -> SimpleNamespace:
    return SimpleNamespace(
        subscription_id=11,
        tariff_key=tariff_key,
        provider=provider,
        status_from_panel="TRIAL" if provider == "manual" else "ACTIVE",
    )


def _payment(snapshot: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        sale_mode="traffic_package@traffic",
        tariff_key="traffic",
        entitlement_context_snapshot=snapshot,
    )


@pytest.mark.parametrize("tariff_key", [None, "standard", "traffic"])
@pytest.mark.parametrize("provider", ["trial", "manual"])
def test_trial_traffic_purchase_keeps_the_quoted_subscription_context(
    tariff_key: str | None, provider: str
) -> None:
    trial = _trial(tariff_key, provider=provider)
    snapshot = build_entitlement_context_snapshot(
        sale_mode="traffic_package@traffic", active_subscription=trial
    )
    parsed = parse_entitlement_context_snapshot(snapshot)
    assert parsed is not None
    assert parsed.active_subscription_id == 11
    assert parsed.active_tariff_key == tariff_key
    assert parsed.target_tariff_key == "traffic"
    payment = _payment(snapshot)
    assert preflight_payment_entitlement(payment, trial).allowed

    replaced = _trial(tariff_key, provider=provider)
    replaced.subscription_id = 12
    stale = preflight_payment_entitlement(payment, replaced)
    assert stale.reason == "active_subscription_changed"
    assert not stale.allowed

    changed = _trial("other", provider=provider)
    stale = preflight_payment_entitlement(payment, changed)
    assert stale.reason == "active_tariff_changed"
    assert not stale.allowed
    assert not preflight_payment_entitlement(payment, None).allowed


@pytest.mark.parametrize("tariff_key", [None, "standard"])
def test_trial_traffic_purchase_cannot_land_on_a_paid_subscription(
    tariff_key: str | None,
) -> None:
    trial = _trial(tariff_key)
    snapshot = build_entitlement_context_snapshot(
        sale_mode="traffic_package@traffic", active_subscription=trial
    )
    trial.provider = "yookassa"
    result = preflight_payment_entitlement(_payment(snapshot), trial)
    assert result.status is EntitlementPreflightStatus.DETERMINISTIC_STALE
    assert result.reason == "active_tariff_mismatch"
    with pytest.raises(EntitlementContextError, match="active_tariff_mismatch"):
        build_entitlement_context_snapshot(
            sale_mode="traffic_package@traffic", active_subscription=trial
        )


@pytest.mark.parametrize(
    "sale_mode",
    ["topup", "premium_topup", "hwid_device", "hwid_devices", "hwid_devices_renewal"],
)
def test_trial_does_not_bypass_cross_tariff_addon_guards(sale_mode: str) -> None:
    trial = _trial("standard")
    with pytest.raises(EntitlementContextError, match="active_tariff_mismatch"):
        build_entitlement_context_snapshot(
            sale_mode=f"{sale_mode}@traffic", active_subscription=trial
        )
    payment = _payment(None)
    payment.sale_mode = f"{sale_mode}@traffic"
    assert not preflight_payment_entitlement(payment, trial).allowed


@pytest.mark.parametrize("tariff_key", [None, "standard", "traffic"])
@pytest.mark.parametrize("provider", ["trial", "manual"])
def test_webapp_creates_traffic_payment_for_a_trial(tariff_key: str | None, provider: str) -> None:
    trial = _trial(tariff_key, provider=provider)
    create_payment = AsyncMock(return_value=web.json_response({"ok": True}))
    provider_spec = PaymentProviderSpec(
        id="provider",
        provider_key="provider",
        label="Provider",
        pending_status="pending_provider",
        enabled=lambda _settings: True,
        create_webapp_payment=create_payment,
    )
    with (
        patch("db.dal.gift_dal.activating_for_user", AsyncMock(return_value=None)),
        patch.object(billing_payments, "get_settings", return_value=settings_stub()),
        patch.object(billing_payments, "get_i18n", return_value=None),
        patch.object(
            billing_payments.subscription_dal,
            "get_active_subscription_by_user_id",
            AsyncMock(return_value=trial),
        ),
        patch("bot.payment_providers.get_provider_spec", return_value=provider_spec),
    ):
        response = asyncio.run(
            billing_payments._create_subscription_payment(
                request=cast(Any, SimpleNamespace(app={})),
                session=AsyncMock(),
                user_id=42,
                method="provider",
                months=10,
                price=100,
                stars_price=None,
                lang="en",
                currency="RUB",
                sale_mode="traffic_package@traffic",
                traffic_gb=10,
            )
        )
    assert response.status == 200, json.loads(response.body)
    create_payment.assert_awaited_once()
    assert create_payment.await_args is not None
    context = create_payment.await_args.args[0]
    assert context.sale_mode == "traffic_package@traffic"
    assert context.traffic_gb == 10
    payment = _payment(context.entitlement_context_snapshot)
    assert preflight_payment_entitlement(payment, trial).allowed
