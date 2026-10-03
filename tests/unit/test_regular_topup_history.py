"""History must cover the lifetime delta before it can bill a paid balance."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bot.services.regular_topup_history import daily_traffic_bytes, regular_period_boundaries
from bot.utils.traffic_reset import traffic_periods_between

START = datetime(2026, 9, 1, tzinfo=UTC)
END = START + timedelta(days=2)
GB = 1024**3


@pytest.mark.parametrize(
    "payload",
    [
        {"categories": ["2026-09-01", "2026-09-02"], "sparklineData": [80 * GB, 20 * GB]},
        {
            "categories": ["2026-09-01", "2026-09-02"],
            "series": [
                {"data": [30 * GB, 10 * GB]},
                {"data": [50 * GB, 10 * GB]},
            ],
        },
    ],
)
def test_complete_all_node_history(payload: dict[str, Any]) -> None:
    assert daily_traffic_bytes(payload, START, END, 100 * GB) == {
        START: 80 * GB,
        START + timedelta(days=1): 20 * GB,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"categories": ["2026-09-02"], "sparklineData": [100 * GB]},
        {"categories": ["2026-09-01", "2026-09-02"], "sparklineData": [0, 20 * GB]},
        {"categories": ["2026-09-01", "2026-09-01"], "sparklineData": [80 * GB, 20 * GB]},
        {"categories": ["2026-09-01", "2026-09-03"], "sparklineData": [80 * GB, 20 * GB]},
        {"categories": ["2026-09-01", "2026-09-02"], "sparklineData": [True, 20 * GB]},
        {"categories": ["2026-09-01", "2026-09-02"], "sparklineData": [float("nan"), 20 * GB]},
        {"categories": ["2026-09-01", "2026-09-02"], "sparklineData": [80 * GB, -20 * GB]},
        {"categories": ["2026-09-01", "2026-09-02"], "series": [{"data": [100 * GB]}]},
    ],
)
def test_partial_or_malformed_history_cannot_bill(payload: dict[str, Any]) -> None:
    assert daily_traffic_bytes(payload, START, END, 100 * GB) is None


@pytest.mark.parametrize("strategy,days,expected", [("DAY", 40, 40), ("WEEK", 280, 40)])
def test_more_than_36_resets(strategy: str, days: int, expected: int) -> None:
    assert traffic_periods_between(START, START + timedelta(days=days), strategy) == expected


def test_scheduler_latency_does_not_create_an_extra_period() -> None:
    start = START + timedelta(seconds=4)
    end = datetime(2026, 10, 1, 0, 0, 7, tzinfo=UTC)
    assert traffic_periods_between(start, end, "MONTH") == 1
    assert regular_period_boundaries(start, end, "MONTH") == [START, end.replace(second=0)]


def test_rolling_months_keep_the_original_day_after_february() -> None:
    start = datetime(2026, 1, 31, tzinfo=UTC)
    end = datetime(2026, 3, 31, tzinfo=UTC)
    assert traffic_periods_between(start, end, "MONTH_ROLLING") == 2
    assert regular_period_boundaries(start, end, "MONTH_ROLLING") == [
        start,
        datetime(2026, 2, 28, tzinfo=UTC),
        end,
    ]
