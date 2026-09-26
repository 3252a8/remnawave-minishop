"""Contract coverage for provider-managed Wata subscriptions."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot.payment_providers.wata import subscriptions as wata_subscriptions
from db.dal import wata_subscription_dal


def test_subscription_schedule_accepts_subscription_periods_only():
    assert wata_subscriptions.subscription_terms_for_checkout(1, "subscription@base|d30") == (
        1,
        "Month",
    )
    assert wata_subscriptions.subscription_terms_for_checkout(14, "subscription@base|d14") == (
        2,
        "Week",
    )
    assert not wata_subscriptions.subscription_context_supported(None, 10, "traffic@base")
    assert not wata_subscriptions.subscription_context_supported(None, 1, "hwid_devices@base")
    assert wata_subscriptions.subscription_terms_for_checkout(365, "subscription@base|d365") is None


def test_recurring_bundle_rejects_proration_but_repeats_checkout_limits():
    bundle = {
        "items": [
            {
                "kind": "traffic",
                "selected_units": 150,
                "amount": 50,
                "future_amount": 50,
                "stars_amount": 25,
                "future_stars_amount": 25,
                "immediate_amount": 0,
                "immediate_stars_amount": 0,
            }
        ],
        "addons_amount": 50,
        "addons_stars": 25,
        "active_context": None,
    }
    encoded = json.dumps(bundle)

    assert wata_subscriptions.subscription_bundle_supported(encoded)

    active = SimpleNamespace(
        subscription_id=91,
        tariff_key="base",
        end_date=datetime(2026, 11, 1, tzinfo=UTC),
    )
    renewed = json.loads(wata_subscriptions.renewal_bundle_snapshot(encoded, active) or "{}")
    assert renewed["items"][0]["selected_units"] == 150
    assert renewed["items"][0]["amount"] == 50
    assert renewed["items"][0]["immediate_amount"] == 0
    assert renewed["active_context"] == {
        "subscription_id": 91,
        "tariff_key": "base",
        "end_at": "2026-11-01T00:00:00+00:00",
    }

    bundle["items"][0]["immediate_amount"] = 10
    bundle["items"][0]["amount"] = 60
    assert not wata_subscriptions.subscription_bundle_supported(json.dumps(bundle))


def test_subscription_mirror_freezes_authorized_terms(monkeypatch):
    monkeypatch.setattr(
        wata_subscription_dal,
        "get_subscription",
        AsyncMock(return_value=None),
    )
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    anchor = SimpleNamespace(
        payment_id=11,
        user_id=42,
        amount=175,
        currency="RUB",
        subscription_duration_months=1,
        subscription_duration_days=30,
        subscription_terms_snapshot='{"monthly_gb":100}',
        checkout_bundle_snapshot='{"items":[]}',
        sale_mode="subscription@base|d30",
        tariff_key="base",
    )

    record = asyncio.run(
        wata_subscription_dal.create_from_anchor(
            session,
            subscription_id="sub-1",
            anchor=anchor,
            interval="Month",
            period=1,
            max_periods=120,
        )
    )

    assert record.subscription_terms_snapshot == anchor.subscription_terms_snapshot
    assert record.checkout_bundle_snapshot == anchor.checkout_bundle_snapshot
    assert record.amount == 175
    assert record.tariff_key == "base"


def test_cancel_recurrence_marks_only_confirmed_remote_completions(monkeypatch):
    first = SimpleNamespace(wata_subscription_id="sub-1")
    second = SimpleNamespace(wata_subscription_id="sub-2")
    list_live = AsyncMock(return_value=[first, second])
    mark_status = AsyncMock()
    monkeypatch.setattr(wata_subscriptions.wata_subscription_dal, "list_live_for_user", list_live)
    monkeypatch.setattr(wata_subscriptions.wata_subscription_dal, "mark_status", mark_status)

    service = object.__new__(wata_subscriptions.WataSubscriptionMixin)
    service.complete_remote_subscription = AsyncMock(side_effect=[True, False])
    session = SimpleNamespace()

    completed = asyncio.run(service.cancel_provider_recurrence(session, user_id=42))

    assert completed is False
    mark_status.assert_awaited_once_with(session, first, "completed")
