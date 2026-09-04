import unittest
from typing import Any, cast

from bot.services.device_topup_availability import (
    DeviceTopupUnavailableReason,
    resolve_device_topup_availability,
)
from config.settings import Settings
from config.tariffs_config import TariffsConfig
from tests.support.settings_stub import settings_stub


def _catalog(
    *,
    enabled: bool = True,
    billing_model: str = "period",
    packages: dict[str, list[dict[str, int]]] | None = None,
) -> dict[str, Any]:
    tariff: dict[str, Any] = {
        "key": "standard",
        "names": {"en": "Standard"},
        "enabled": enabled,
        "billing_model": billing_model,
        "squad_uuids": ["main"],
        "hwid_device_limit": 5,
    }
    if billing_model == "period":
        tariff.update(
            monthly_gb=100,
            enabled_periods=[1],
            prices={"rub": {"1": 100}},
        )
    else:
        tariff.update(
            traffic_packages={"rub": [{"gb": 100, "price": 100}]},
            conversion_rate_per_gb=1,
        )
    if packages is not None:
        tariff["hwid_device_packages"] = packages
    tariffs = [tariff]
    default_tariff = "standard"
    if not enabled:
        tariffs.append(
            {
                "key": "fallback",
                "names": {"en": "Fallback"},
                "enabled": True,
                "billing_model": "period",
                "squad_uuids": ["main"],
                "monthly_gb": 100,
                "enabled_periods": [1],
                "prices": {"rub": {"1": 100}},
            }
        )
        default_tariff = "fallback"
    return {
        "default_tariff": default_tariff,
        "default_currency": "rub",
        "tariffs": tariffs,
    }


def _settings(
    *,
    catalog: dict[str, Any] | None = None,
    devices_enabled: bool = True,
) -> Settings:
    tariffs_config = TariffsConfig.model_validate(catalog) if catalog is not None else None
    return cast(
        Settings,
        settings_stub(
            MY_DEVICES_SECTION_ENABLED=devices_enabled,
            tariffs_config=tariffs_config,
        ),
    )


class DeviceTopupAvailabilityTests(unittest.TestCase):
    def test_allows_default_currency_and_stars_packages(self) -> None:
        settings = _settings(
            catalog=_catalog(
                packages={
                    "rub": [{"count": 1, "price": 50}],
                    "stars": [{"count": 2, "price": 75}],
                }
            ),
        )
        result = resolve_device_topup_availability(
            settings,
            subscription_active=True,
            tariff_key="standard",
            max_devices=5,
        )

        self.assertTrue(result.allowed)
        self.assertIsNone(result.reason)
        self.assertEqual(result.package_counts, (1, 2))
        self.assertEqual(result.available_currencies, ("rub", "stars"))
        self.assertTrue(result.supports(1, "rub"))
        self.assertTrue(result.supports(2, "stars"))
        self.assertFalse(result.supports(2, "rub"))

    def test_allows_stars_only_package(self) -> None:
        settings = _settings(
            catalog=_catalog(
                packages={
                    "eur": [{"count": 1, "price": 50}],
                    "stars": [{"count": 3, "price": 75}],
                }
            ),
        )
        result = resolve_device_topup_availability(
            settings,
            subscription_active=True,
            tariff_key="standard",
            max_devices=5,
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.package_counts, (3,))
        self.assertEqual(result.available_currencies, ("stars",))

    def test_rejects_package_only_in_unavailable_currency(self) -> None:
        settings = _settings(
            catalog=_catalog(packages={"eur": [{"count": 1, "price": 50}]}),
        )
        result = resolve_device_topup_availability(
            settings,
            subscription_active=True,
            tariff_key="standard",
            max_devices=5,
        )

        self.assertFalse(result.allowed)
        self.assertEqual(
            result.reason,
            DeviceTopupUnavailableReason.NO_PURCHASABLE_PACKAGES,
        )

    def test_reports_each_primary_blocking_reason(self) -> None:
        cases: list[
            tuple[
                dict[str, Any],
                dict[str, Any],
                DeviceTopupUnavailableReason,
            ]
        ] = [
            (
                {"devices_enabled": False},
                {"subscription_active": True, "tariff_key": "standard", "max_devices": 5},
                DeviceTopupUnavailableReason.SECTION_DISABLED,
            ),
            (
                {"catalog": None},
                {"subscription_active": True, "tariff_key": "standard", "max_devices": 5},
                DeviceTopupUnavailableReason.TARIFFS_UNAVAILABLE,
            ),
            (
                {},
                {"subscription_active": False, "tariff_key": "standard", "max_devices": 5},
                DeviceTopupUnavailableReason.SUBSCRIPTION_INACTIVE,
            ),
            (
                {},
                {"subscription_active": True, "tariff_key": None, "max_devices": 5},
                DeviceTopupUnavailableReason.MISSING_TARIFF,
            ),
            (
                {},
                {"subscription_active": True, "tariff_key": "missing", "max_devices": 5},
                DeviceTopupUnavailableReason.TARIFF_NOT_FOUND,
            ),
            (
                {"catalog": _catalog(billing_model="traffic")},
                {"subscription_active": True, "tariff_key": "standard", "max_devices": 5},
                DeviceTopupUnavailableReason.UNSUPPORTED_BILLING_MODEL,
            ),
            (
                {},
                {"subscription_active": True, "tariff_key": "standard", "max_devices": 0},
                DeviceTopupUnavailableReason.UNLIMITED_DEVICES,
            ),
            (
                {"catalog": _catalog(packages=None)},
                {"subscription_active": True, "tariff_key": "standard", "max_devices": 5},
                DeviceTopupUnavailableReason.NO_PURCHASABLE_PACKAGES,
            ),
        ]

        for settings_overrides, arguments, expected in cases:
            with self.subTest(reason=expected):
                settings = _settings(
                    catalog=settings_overrides.get(
                        "catalog",
                        _catalog(packages={"rub": [{"count": 1, "price": 50}]}),
                    ),
                    devices_enabled=settings_overrides.get("devices_enabled", True),
                )
                result = resolve_device_topup_availability(settings, **arguments)
            self.assertFalse(result.allowed)
            self.assertEqual(result.reason, expected)

    def test_assigned_hidden_tariff_keeps_device_topups_available(self) -> None:
        settings = _settings(
            catalog=_catalog(
                enabled=False,
                packages={"rub": [{"count": 1, "price": 50}]},
            ),
        )

        result = resolve_device_topup_availability(
            settings,
            subscription_active=True,
            tariff_key="standard",
            max_devices=5,
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.tariff.key, "standard")

    def test_rejects_stale_tariff_callback(self) -> None:
        settings = _settings(
            catalog=_catalog(packages={"rub": [{"count": 1, "price": 50}]}),
        )
        result = resolve_device_topup_availability(
            settings,
            subscription_active=True,
            tariff_key="standard",
            max_devices=5,
            expected_tariff_key="other",
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, DeviceTopupUnavailableReason.TARIFF_MISMATCH)


if __name__ == "__main__":
    unittest.main()
