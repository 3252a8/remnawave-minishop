from datetime import UTC, datetime
from typing import Any

import pytest

from config.subscription_periods import (
    add_period_days,
    days_to_legacy_months,
    duration_label_parts,
    legacy_months_to_days,
    multiplied_bonus_days,
    positive_period,
    resolve_period_days,
)
from config.tariff_period_migration import normalize_tariff_catalog


@pytest.mark.parametrize(
    ("months", "days"), [(1, 30), (3, 90), (6, 180), (12, 365), (13, 395), (18, 545), (24, 730)]
)
def test_legacy_period_round_trip(months: int, days: int) -> None:
    assert legacy_months_to_days(months) == days
    assert days_to_legacy_months(days) == months


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.5, "1.0", "1e3", "", 2**31])
def test_period_does_not_silently_coerce_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        positive_period(value)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (7, (7, "day")),
        (45, (45, "day")),
        (30, (1, "month")),
        (360, (12, "month")),
        (365, (1, "year")),
        (730, (2, "year")),
        (366, (366, "day")),
        (10950, (30, "year")),
    ],
)
def test_display_units_are_exact(days: int, expected: tuple[int, str]) -> None:
    assert duration_label_parts(days) == expected


def test_calendar_legacy_alias_cannot_represent_360_days() -> None:
    assert days_to_legacy_months(360) is None
    assert resolve_period_days(months=12) == 365
    with pytest.raises(ValueError, match="conflicting"):
        resolve_period_days(months=12, duration_days=360)


def test_fixed_days_preserve_time_and_ignore_calendar_month_length() -> None:
    assert add_period_days(datetime(2027, 1, 31, 12, 34, tzinfo=UTC), 30) == datetime(
        2027, 3, 2, 12, 34, tzinfo=UTC
    )
    assert add_period_days(datetime(2024, 2, 29, tzinfo=UTC), 365) == datetime(
        2025, 2, 28, tzinfo=UTC
    )
    assert multiplied_bonus_days(7, 1.5) == 4


def test_catalog_conversion_preserves_money_bonus_days_and_device_units() -> None:
    catalog: dict[str, Any] = {
        "default_tariff": "base",
        "tariffs": [
            {
                "key": "base",
                "billing_model": "period",
                "enabled_periods": [1, 12],
                "prices": {"eur": {"1": 10, "12": 90}},
                "referral_bonus_days_inviter": {"12": 7},
                "hwid_device_packages": {"rub": [{"count": 2, "price": 50}]},
                "tribute": {"period_ids": {"12": 123}},
            }
        ],
    }
    normalized = normalize_tariff_catalog(catalog)
    tariff = normalized["tariffs"][0]
    assert tariff["enabled_periods"] == [30, 365]
    assert tariff["prices"] == {"eur": {"30": 10, "365": 90}}
    assert tariff["referral_bonus_days_inviter"] == {"365": 7}
    assert tariff["tribute"]["period_ids"] == {"365": 123}
    assert tariff["hwid_device_packages"]["rub"][0]["count"] == 2
    assert tariff["hwid_device_packages"]["rub"][0]["prices"]["365"] == 600
    assert tariff["addon_period_factors"]["365"] == 12
    assert normalize_tariff_catalog(normalized) == normalized
    assert catalog["tariffs"][0]["enabled_periods"] == [1, 12]
