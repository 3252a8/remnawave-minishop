"""Parity test for the admin subscription response contract.

``_serialize_subscription`` now routes through ``AdminSubscriptionOut``; this pins
the serialized JSON (keys, order and values) so the typed model stays byte-shape
identical to the legacy dict the admin/webapp clients consume.
"""

from datetime import datetime
from types import SimpleNamespace

from bot.app.web.admin_api_impl.common import _serialize_subscription


def _subscription(**overrides):
    values = {
        "subscription_id": 7,
        "panel_user_uuid": "puuid",
        "panel_subscription_uuid": "psuuid",
        # Admin JSON contracts serialize legacy naive DB datetimes without offsets.
        "start_date": datetime(2026, 1, 1, 12, 0, 0),  # noqa: DTZ001
        "end_date": datetime(2026, 2, 1, 12, 0, 0),  # noqa: DTZ001
        "duration_months": 1,
        "is_active": True,
        "status_from_panel": "ACTIVE",
        "traffic_limit_bytes": 5000,
        "traffic_used_bytes": 1234,
        "tier_baseline_bytes": 4000,
        "topup_balance_bytes": 500,
        "premium_used_bytes": 30,
        "premium_baseline_bytes": 1000,
        "premium_topup_balance_bytes": 200,
        "premium_topup_used_bytes": 50,
        "premium_bonus_bytes": 10,
        "regular_bonus_bytes": 20,
        "regular_unlimited_override": False,
        "premium_unlimited_override": False,
        "premium_is_limited": False,
        "hwid_device_limit": 3,
        "extra_hwid_devices": 2,
        "tariff_key": "premium_1m",
        "provider": "stripe",
        "auto_renew_enabled": True,
        "is_throttled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_serialize_subscription_matches_legacy_contract():
    result = _serialize_subscription(_subscription())
    expected = {
        "subscription_id": 7,
        "panel_user_uuid": "puuid",
        "panel_subscription_uuid": "psuuid",
        "start_date": "2026-01-01T12:00:00",
        "end_date": "2026-02-01T12:00:00",
        "duration_months": 1,
        "is_active": True,
        "status_from_panel": "ACTIVE",
        "traffic_limit_bytes": 5000,
        "traffic_used_bytes": 1234,
        "tier_baseline_bytes": 4000,
        "topup_balance_bytes": 500,
        "premium_used_bytes": 30,
        "premium_limit_bytes": 1260,
        "premium_baseline_bytes": 1000,
        "premium_topup_balance_bytes": 200,
        "premium_topup_used_bytes": 50,
        "premium_bonus_bytes": 10,
        "regular_bonus_bytes": 20,
        "regular_unlimited_override": False,
        "premium_unlimited_override": False,
        "premium_is_limited": False,
        "hwid_device_limit": 3,
        "extra_hwid_devices": 2,
        "tariff_key": "premium_1m",
        "display_label": "premium_1m",
        "is_trial": False,
        "auto_renew_enabled": True,
        "provider": "stripe",
        "is_throttled": False,
        "billing_model": None,
        "traffic_limit_strategy": None,
        "traffic_strategy_editable": False,
        "traffic_strategy_lock_reason": None,
    }
    assert result == expected
    # Key order is part of the contract (model_dump preserves field order).
    assert list(result.keys()) == list(expected.keys())


def test_serialize_subscription_trial_uses_trial_label():
    result = _serialize_subscription(
        _subscription(provider="trial", tariff_key=None, start_date=None, end_date=None)
    )
    assert result["is_trial"] is True
    assert result["display_label"] == "Trial"
    assert result["start_date"] is None
    assert result["end_date"] is None


def test_serialize_subscription_premium_limit_is_sum_of_components():
    result = _serialize_subscription(
        _subscription(
            premium_baseline_bytes=100,
            premium_topup_balance_bytes=20,
            premium_topup_used_bytes=3,
            premium_bonus_bytes=1,
        )
    )
    assert result["premium_limit_bytes"] == 124
