"""Tests for the traffic top-up unlock gate (``resolve_traffic_topup_availability``).

The gate mirrors the web app rules (``frontend/src/lib/webapp/billingView.ts``):
the bot menu button and the ``tariff_topup:list`` callback must offer top-ups
only once usage crosses ``TRAFFIC_TOPUP_UNLOCK_PERCENT`` of the limit. The
per-tariff ``topup_always_available`` / ``premium_topup_always_available``
admin toggles and traffic-billed tariffs bypass the threshold independently
for regular vs. premium traffic; unlimited overrides hide the offer entirely.
"""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from bot.services.traffic_topup_availability import (
    TRAFFIC_TOPUP_UNLOCK_PERCENT,
    resolve_traffic_topup_availability,
)
from config.settings import Settings

GB = 2**30


def _tariffs_payload(
    *,
    topup_rub=None,
    premium_topup_rub=None,
    topup_always_available: bool = False,
    premium_topup_always_available: bool = False,
) -> dict:
    tariff: dict[str, Any] = {
        "key": "standard",
        "names": {"en": "Standard"},
        "descriptions": {"en": "Base"},
        "squad_uuids": ["main"],
        "billing_model": "period",
        "monthly_gb": 100,
        "prices_rub": {"1": 100},
        "prices_stars": {"1": 0},
        "enabled_periods": [1],
        "enabled": True,
        "topup_always_available": topup_always_available,
    }
    if topup_rub:
        tariff["topup_packages"] = {"rub": topup_rub, "stars": []}
    if premium_topup_rub:
        tariff["premium_squad_uuids"] = ["premium-squad"]
        tariff["premium_monthly_gb"] = 20
        tariff["premium_topup_packages"] = {"rub": premium_topup_rub, "stars": []}
        tariff["premium_topup_always_available"] = premium_topup_always_available
    return {"default_tariff": "standard", "tariffs": [tariff]}


def _traffic_tariffs_payload() -> dict:
    tariff: dict[str, Any] = {
        "key": "traffic",
        "names": {"en": "Traffic"},
        "descriptions": {"en": "Traffic"},
        "squad_uuids": ["main"],
        "billing_model": "traffic",
        "traffic_packages": {"rub": [{"gb": 100, "price": 100}], "stars": []},
        "enabled": True,
    }
    return {"default_tariff": "traffic", "tariffs": [tariff]}


def _make_settings(tmpdir: str, payload: dict) -> Settings:
    config_path = Path(tmpdir) / "tariffs.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        TARIFFS_CONFIG_PATH=str(config_path),
    )


def _active(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tariff_key": "standard",
        "traffic_limit_bytes": 100 * GB,
        "traffic_used_bytes": 0,
        "premium_limit_bytes": 0,
        "premium_used_bytes": 0,
        "regular_unlimited_override": False,
        "premium_unlimited_override": False,
    }
    base.update(overrides)
    return base


class TrafficTopupAvailabilityTests(unittest.TestCase):
    def test_locked_below_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_payload(topup_rub=[{"gb": 10, "price": 50}]))
            availability = resolve_traffic_topup_availability(
                settings, _active(traffic_used_bytes=50 * GB)
            )
        self.assertTrue(availability.regular_offer_exists)
        self.assertTrue(availability.has_offers)
        self.assertFalse(availability.regular_unlocked)
        self.assertFalse(availability.unlocked)

    def test_unlocked_at_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_payload(topup_rub=[{"gb": 10, "price": 50}]))
            used = TRAFFIC_TOPUP_UNLOCK_PERCENT * GB  # 80% of the 100 GB limit
            availability = resolve_traffic_topup_availability(
                settings, _active(traffic_used_bytes=used)
            )
        self.assertTrue(availability.regular_unlocked)
        self.assertTrue(availability.unlocked)

    def test_always_available_toggle_bypasses_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(
                    topup_rub=[{"gb": 10, "price": 50}],
                    topup_always_available=True,
                ),
            )
            availability = resolve_traffic_topup_availability(
                settings, _active(traffic_used_bytes=0)
            )
        self.assertTrue(availability.regular_always_available)
        self.assertTrue(availability.regular_unlocked)

    def test_premium_always_available_toggle_is_independent_of_regular(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(
                    topup_rub=[{"gb": 10, "price": 50}],
                    premium_topup_rub=[{"gb": 10, "price": 50}],
                    topup_always_available=False,
                    premium_topup_always_available=True,
                ),
            )
            availability = resolve_traffic_topup_availability(
                settings,
                _active(
                    traffic_used_bytes=0,
                    premium_limit_bytes=20 * GB,
                    premium_used_bytes=0,
                ),
            )
        self.assertFalse(availability.regular_always_available)
        self.assertTrue(availability.premium_always_available)
        self.assertFalse(availability.regular_unlocked)
        self.assertTrue(availability.premium_unlocked)

    def test_traffic_billing_model_bypasses_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _traffic_tariffs_payload())
            availability = resolve_traffic_topup_availability(
                settings,
                _active(tariff_key="traffic", traffic_used_bytes=0),
            )
        self.assertTrue(availability.regular_offer_exists)
        self.assertTrue(availability.regular_unlocked)

    def test_regular_unlimited_override_hides_offer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(
                    topup_rub=[{"gb": 10, "price": 50}],
                    topup_always_available=True,
                ),
            )
            availability = resolve_traffic_topup_availability(
                settings,
                _active(traffic_used_bytes=90 * GB, regular_unlimited_override=True),
            )
        self.assertFalse(availability.regular_unlocked)

    def test_zero_limit_hides_offer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_payload(topup_rub=[{"gb": 10, "price": 50}]))
            availability = resolve_traffic_topup_availability(
                settings, _active(traffic_limit_bytes=0)
            )
        self.assertFalse(availability.regular_unlocked)

    def test_premium_tracked_separately_from_regular(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(
                tmpdir,
                _tariffs_payload(premium_topup_rub=[{"gb": 10, "price": 50}]),
            )
            availability = resolve_traffic_topup_availability(
                settings,
                _active(
                    traffic_used_bytes=0,
                    premium_limit_bytes=20 * GB,
                    premium_used_bytes=19 * GB,
                ),
            )
        self.assertFalse(availability.regular_offer_exists)
        self.assertTrue(availability.premium_offer_exists)
        self.assertFalse(availability.regular_unlocked)
        self.assertTrue(availability.premium_unlocked)
        self.assertTrue(availability.unlocked)

    def test_no_offers_without_packages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_payload())
            availability = resolve_traffic_topup_availability(
                settings, _active(traffic_used_bytes=90 * GB)
            )
        self.assertFalse(availability.has_offers)
        self.assertFalse(availability.unlocked)

    def test_unknown_tariff_returns_locked_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_payload(topup_rub=[{"gb": 10, "price": 50}]))
            availability = resolve_traffic_topup_availability(
                settings, _active(tariff_key="missing")
            )
        self.assertFalse(availability.has_offers)
        self.assertFalse(availability.unlocked)

    def test_no_active_details_returns_locked_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = _make_settings(tmpdir, _tariffs_payload(topup_rub=[{"gb": 10, "price": 50}]))
            availability = resolve_traffic_topup_availability(settings, None)
        self.assertFalse(availability.has_offers)
        self.assertFalse(availability.unlocked)


if __name__ == "__main__":
    unittest.main()
