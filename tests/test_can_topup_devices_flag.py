"""Tests for the ``can_topup_devices`` flag emitted by ``_serialize_subscription``.

The flag drives whether the Web App shows the "buy HWID devices" button on the
Devices screen. Before this flag existed, the button was rendered for any
active subscription with a finite ``max_devices``, even if the user's tariff
had no HWID device packages configured. Clicking led the user into an empty
modal with "no options available" — confusing.

These tests pin the visibility contract:

* unlimited subscribers (max_devices == 0) → flag is False (no point in top-up);
* tariff without HWID packages → flag is False;
* tariff with rub-only or stars-only packages → flag is True;
* legacy mode without a tariffs catalog → flag is False;
* malformed tariff lookup → flag is False (and does not raise).
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Importing the facade populates ``webapp.serializers`` with helpers like
# ``_format_remaining`` that come from ``_runtime`` via the facade init dance.
import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp.serializers import _serialize_subscription
from config.settings import Settings


def _tariffs_payload(*, hwid_rub=None, hwid_stars=None, has_premium=False) -> dict:
    tariff: Dict[str, Any] = {
        "key": "standard",
        "names": {"en": "Standard"},
        "descriptions": {"en": "Base"},
        "squad_uuids": ["main"],
        "billing_model": "period",
        "monthly_gb": 100,
        "prices_rub": {"1": 100},
        "prices_stars": {"1": 0},
        "enabled_periods": [1],
        "hwid_device_limit": 3,
        "enabled": True,
    }
    if has_premium:
        tariff.update(
            premium_squad_uuids=["premium-squad"],
            premium_monthly_gb=20,
        )
    if hwid_rub or hwid_stars:
        tariff["hwid_device_packages"] = {
            "rub": hwid_rub or [],
            "stars": hwid_stars or [],
        }
    return {"default_tariff": "standard", "tariffs": [tariff]}


def _traffic_tariffs_payload(*, hwid_rub=None) -> dict:
    tariff: Dict[str, Any] = {
        "key": "traffic",
        "names": {"en": "Traffic"},
        "descriptions": {"en": "Traffic"},
        "squad_uuids": ["main"],
        "billing_model": "traffic",
        "traffic_packages": {"rub": [{"gb": 100, "price": 100}], "stars": []},
        "hwid_device_limit": 3,
        "enabled": True,
    }
    if hwid_rub:
        tariff["hwid_device_packages"] = {"rub": hwid_rub, "stars": []}
    return {"default_tariff": "traffic", "tariffs": [tariff]}


def _make_settings(tmpdir: str, payload: Optional[dict] = None, **overrides: Any) -> Settings:
    values: Dict[str, Any] = {
        "_env_file": None,
        "BOT_TOKEN": "token",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
    }
    if payload is not None:
        config_path = Path(tmpdir) / "tariffs.json"
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        values["TARIFFS_CONFIG_PATH"] = str(config_path)
    values.update(overrides)
    return Settings(**values)


def _active(**overrides) -> Dict[str, Any]:
    """Build a minimal ``active`` dict shaped like ``get_active_subscription_details``."""
    base: Dict[str, Any] = {
        "tariff_key": "standard",
        "status_from_panel": "ACTIVE",
        "end_date": datetime.now(timezone.utc) + timedelta(days=30),
        "traffic_limit_bytes": 0,
        "traffic_used_bytes": 0,
        "premium_baseline_bytes": 0,
        "premium_topup_balance_bytes": 0,
        "premium_topup_used_bytes": 0,
        "premium_used_bytes": 0,
        "premium_limit_bytes": 0,
        "max_devices": 3,
        "base_hwid_device_limit": 3,
        "extra_hwid_devices": 0,
        "billing_model": "period",
        "tariff_name": "Standard",
        "tariff_description": "Base",
        "premium_title": None,
        "config_link": None,
        "connect_button_url": None,
        "tier_baseline_bytes": 0,
        "topup_balance_bytes": 0,
        "premium_bonus_bytes": 0,
        "regular_bonus_bytes": 0,
        "regular_unlimited_override": False,
        "premium_unlimited_override": False,
        "premium_is_limited": False,
        "premium_squad_labels": [],
        "premium_node_labels": [],
        "period_start_at": None,
        "is_throttled": False,
        "traffic_limit_strategy": "",
    }
    base.update(overrides)
    return base


class CanTopupDevicesFlagTests(unittest.TestCase):
    def test_flag_is_true_when_tariff_has_rub_packages_and_limit_is_finite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(hwid_rub=[{"count": 1, "price": 50}]),
            )
            payload = _serialize_subscription(settings, _active(max_devices=3), None, "en")
        self.assertTrue(payload["can_topup_devices"])

    def test_flag_is_true_when_only_stars_packages_are_configured(self):
        # The bot only renders rub packages today, but the Web App grid renders
        # both. The flag drives the Web App, so stars-only must still be True.
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(hwid_stars=[{"count": 1, "price": 100}]),
            )
            payload = _serialize_subscription(settings, _active(max_devices=3), None, "en")
        self.assertTrue(payload["can_topup_devices"])

    def test_flag_is_false_when_max_devices_is_zero(self):
        # Unlimited subscribers: hwid_devices topup is a dead end.
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(hwid_rub=[{"count": 1, "price": 50}]),
            )
            payload = _serialize_subscription(settings, _active(max_devices=0), None, "en")
        self.assertFalse(payload["can_topup_devices"])

    def test_flag_is_false_when_max_devices_is_missing(self):
        # Missing device limit is unlimited for Remnawave HWID limits.
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(hwid_rub=[{"count": 1, "price": 50}]),
            )
            payload = _serialize_subscription(settings, _active(max_devices=None), None, "en")
        self.assertFalse(payload["can_topup_devices"])

    def test_flag_is_false_when_tariff_has_no_hwid_packages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_payload())
            payload = _serialize_subscription(settings, _active(), None, "en")
        self.assertFalse(payload["can_topup_devices"])

    def test_flag_is_false_when_packages_dict_is_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(hwid_rub=[], hwid_stars=[]),
            )
            payload = _serialize_subscription(settings, _active(), None, "en")
        self.assertFalse(payload["can_topup_devices"])

    def test_flag_is_false_in_legacy_mode_without_tariff_catalog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, payload=None)  # no tariffs catalog
            payload = _serialize_subscription(
                settings, _active(tariff_key=None, max_devices=3), None, "en"
            )
        self.assertFalse(payload["can_topup_devices"])

    def test_flag_is_false_when_tariff_key_does_not_resolve(self):
        # If the user's stored ``tariff_key`` was renamed/removed, the helper
        # raises inside ``settings.tariffs_config.require``; we should swallow
        # that and emit False, not 500.
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(hwid_rub=[{"count": 1, "price": 50}]),
            )
            payload = _serialize_subscription(
                settings, _active(tariff_key="missing-tariff"), None, "en"
            )
        self.assertFalse(payload["can_topup_devices"])

    def test_flag_is_false_for_traffic_tariff_even_with_packages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _traffic_tariffs_payload(hwid_rub=[{"count": 1, "price": 50}]),
            )
            payload = _serialize_subscription(
                settings,
                _active(tariff_key="traffic", billing_model="traffic"),
                None,
                "en",
            )
        self.assertFalse(payload["can_topup_devices"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
