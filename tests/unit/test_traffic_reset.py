import unittest
from datetime import UTC, datetime

from bot.utils.traffic_reset import (
    next_traffic_reset_after,
    panel_next_traffic_reset_at,
    traffic_accounting_period_start,
)


class TrafficResetTests(unittest.TestCase):
    def test_calendar_strategies_start_at_utc_boundaries(self):
        now = datetime(2026, 7, 8, 13, 45, tzinfo=UTC)

        self.assertEqual(
            traffic_accounting_period_start("DAY", now),
            datetime(2026, 7, 8, tzinfo=UTC),
        )
        self.assertEqual(
            traffic_accounting_period_start("WEEK", now),
            datetime(2026, 7, 6, tzinfo=UTC),
        )
        self.assertEqual(
            traffic_accounting_period_start("MONTH", now),
            datetime(2026, 7, 1, tzinfo=UTC),
        )

    def test_month_rolling_advances_from_panel_last_reset(self):
        now = datetime(2026, 8, 20, 9, tzinfo=UTC)
        panel_user = {
            "trafficLimitStrategy": "MONTH_ROLLING",
            "lastTrafficResetAt": "2026-06-15T12:30:00Z",
        }

        self.assertEqual(
            traffic_accounting_period_start(
                "MONTH_ROLLING",
                now,
                subscription_start_at=datetime(2026, 5, 3, tzinfo=UTC),
                panel_user_data=panel_user,
            ),
            datetime(2026, 8, 15, 12, 30, tzinfo=UTC),
        )
        self.assertEqual(
            panel_next_traffic_reset_at(
                panel_user,
                fallback_strategy="MONTH_ROLLING",
                now=now,
            ),
            datetime(2026, 9, 15, 12, 30, tzinfo=UTC),
        )

    def test_previous_period_start_is_anchor_when_panel_payload_omits_reset(self):
        previous_period_start = datetime(2026, 6, 15, 12, 30, tzinfo=UTC)

        self.assertEqual(
            traffic_accounting_period_start(
                "MONTH",
                datetime(2026, 7, 4, 9, tzinfo=UTC),
                previous_period_start_at=previous_period_start,
            ),
            previous_period_start,
        )
        self.assertEqual(
            traffic_accounting_period_start(
                "MONTH",
                datetime(2026, 7, 16, 9, tzinfo=UTC),
                previous_period_start_at=previous_period_start,
            ),
            datetime(2026, 7, 15, 12, 30, tzinfo=UTC),
        )

    def test_next_reset_is_empty_for_no_reset(self):
        self.assertIsNone(
            next_traffic_reset_after(
                datetime(2026, 7, 1, tzinfo=UTC),
                "NO_RESET",
                now=datetime(2026, 7, 2, tzinfo=UTC),
            )
        )


if __name__ == "__main__":
    unittest.main()
