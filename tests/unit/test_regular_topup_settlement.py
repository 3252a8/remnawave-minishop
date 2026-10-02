"""A carried-over traffic pack is charged at each counter reset, not re-granted."""

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from bot.services.regular_topup_settlement import (
    settle_regular_topup,
    settle_topup_at_counter_reset,
)
from bot.utils.traffic_reset import traffic_periods_between

GB = 1024**3


def _settle(**overrides: Any) -> tuple[int, int | None, int]:
    values: dict[str, Any] = {
        "balance_bytes": 50 * GB,
        "period_lifetime_start_bytes": 480 * GB,
        "used_bytes": 0,
        "lifetime_used_bytes": 480 * GB,
        "allowance_bytes": 50 * GB,
    }
    values.update(overrides)
    result = settle_topup_at_counter_reset(**values)
    return result.balance_bytes, result.period_lifetime_start_bytes, result.consumed_bytes


class SettleTopupAtCounterResetTests(unittest.TestCase):
    def test_first_observation_only_records_the_period_start(self) -> None:
        self.assertEqual(
            _settle(
                period_lifetime_start_bytes=None, used_bytes=20 * GB, lifetime_used_bytes=500 * GB
            ),
            (50 * GB, 480 * GB, 0),
        )

    def test_usage_within_the_period_changes_nothing(self) -> None:
        self.assertEqual(
            _settle(used_bytes=70 * GB, lifetime_used_bytes=550 * GB), (50 * GB, 480 * GB, 0)
        )

    def test_reset_charges_usage_beyond_the_allowance(self) -> None:
        # The ended period used 70 GB: 50 GB allowance plus 20 GB of the pack.
        self.assertEqual(_settle(lifetime_used_bytes=550 * GB), (30 * GB, 550 * GB, 20 * GB))

    def test_unused_pack_carries_over_in_full(self) -> None:
        self.assertEqual(_settle(lifetime_used_bytes=515 * GB), (50 * GB, 515 * GB, 0))

    def test_pack_is_never_charged_below_zero(self) -> None:
        self.assertEqual(
            _settle(balance_bytes=10 * GB, lifetime_used_bytes=680 * GB), (0, 680 * GB, 10 * GB)
        )

    def test_restarted_panel_counters_do_not_charge(self) -> None:
        self.assertEqual(_settle(used_bytes=5 * GB, lifetime_used_bytes=5 * GB), (50 * GB, 0, 0))

    def test_unlimited_allowance_never_charges(self) -> None:
        self.assertEqual(
            _settle(lifetime_used_bytes=900 * GB, allowance_bytes=0), (50 * GB, 900 * GB, 0)
        )

    def test_missing_lifetime_counter_leaves_the_state_untouched(self) -> None:
        self.assertEqual(_settle(lifetime_used_bytes=None), (50 * GB, 480 * GB, 0))


class TrafficPeriodsBetweenTests(unittest.TestCase):
    def test_counts_every_monthly_reset(self) -> None:
        aug, oct_ = datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
        self.assertEqual(traffic_periods_between(aug, oct_, "MONTH"), 2)

    def test_counts_daily_resets(self) -> None:
        start, end = datetime(2026, 9, 30, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)
        self.assertEqual(traffic_periods_between(start, end, "DAY"), 2)

    def test_reports_at_least_one_period(self) -> None:
        oct_ = datetime(2026, 10, 1, tzinfo=UTC)
        self.assertEqual(traffic_periods_between(oct_, oct_, "MONTH"), 1)
        self.assertEqual(traffic_periods_between(None, oct_, "MONTH"), 1)
        self.assertEqual(
            traffic_periods_between(datetime(2026, 1, 1, tzinfo=UTC), oct_, "NO_RESET"), 1
        )


def _service(device_bonus: int = 0) -> Any:
    def limit(**kwargs: Any) -> int:
        if kwargs["regular_unlimited_override"]:
            return 0
        return int(
            kwargs["tier_baseline_bytes"]
            + kwargs["topup_balance_bytes"]
            + kwargs["regular_bonus_bytes"]
            + kwargs["hwid_device_bonus_bytes"]
        )

    return SimpleNamespace(
        _extract_lifetime_used_traffic=lambda data: data["userTraffic"]["lifetimeUsedTrafficBytes"],
        _compute_main_traffic_limit_bytes=limit,
        _hwid_traffic_bonus_bytes_from_summary=lambda _summary: device_bonus,
    )


class SettleRegularTopupTests(unittest.IsolatedAsyncioTestCase):
    def _sub(self, **overrides: Any) -> SimpleNamespace:
        values: dict[str, Any] = {
            "subscription_id": 62,
            "topup_balance_bytes": 50 * GB,
            "traffic_period_lifetime_start_bytes": 480 * GB,
            "tier_baseline_bytes": 50 * GB,
            "regular_bonus_bytes": 0,
            "regular_unlimited_override": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    async def _settle(
        self,
        sub: SimpleNamespace,
        *,
        used: int,
        lifetime: int,
        device_bonus: int = 0,
        previous: datetime = datetime(2026, 9, 1, tzinfo=UTC),
    ) -> tuple[int, AsyncMock]:
        summary = AsyncMock(return_value={})
        with patch(
            "bot.services.regular_topup_settlement.tariff_dal.get_hwid_device_entitlement_summary",
            summary,
        ):
            consumed = await settle_regular_topup(
                AsyncMock(),
                sub,
                SimpleNamespace(monthly_bytes=50 * GB),
                subscription_service=_service(device_bonus),
                used_bytes=used,
                panel_user_data={"userTraffic": {"lifetimeUsedTrafficBytes": lifetime}},
                previous_period_start=previous,
                period_start=datetime(2026, 10, 1, tzinfo=UTC),
                traffic_strategy="MONTH",
                now=datetime(2026, 10, 1, 0, 5, tzinfo=UTC),
            )
        return consumed, summary

    async def test_reset_charges_the_pack_beyond_base_and_device_bonus(self) -> None:
        # Allowance is 50 GB base plus 15 GB device bonus; the period used 80 GB.
        sub = self._sub()

        consumed, _ = await self._settle(sub, used=0, lifetime=560 * GB, device_bonus=15 * GB)

        self.assertEqual(consumed, 15 * GB)
        self.assertEqual(sub.topup_balance_bytes, 35 * GB)
        self.assertEqual(sub.traffic_period_lifetime_start_bytes, 560 * GB)

    async def test_spent_pack_leaves_only_the_base_limit(self) -> None:
        sub = self._sub()

        consumed, _ = await self._settle(sub, used=2 * GB, lifetime=592 * GB)

        self.assertEqual(consumed, 50 * GB)
        self.assertEqual(sub.topup_balance_bytes, 0)

    async def test_period_in_progress_skips_the_entitlement_lookup(self) -> None:
        sub = self._sub()

        consumed, summary = await self._settle(sub, used=30 * GB, lifetime=510 * GB)

        self.assertEqual(consumed, 0)
        summary.assert_not_awaited()
        self.assertEqual(sub.topup_balance_bytes, 50 * GB)
        self.assertEqual(sub.traffic_period_lifetime_start_bytes, 480 * GB)

    async def test_missed_resets_use_one_allowance_per_period(self) -> None:
        sub = self._sub()

        consumed, _ = await self._settle(
            sub, used=0, lifetime=610 * GB, previous=datetime(2026, 8, 1, tzinfo=UTC)
        )

        self.assertEqual(consumed, 30 * GB)

    async def test_unlimited_override_keeps_the_pack(self) -> None:
        sub = self._sub(regular_unlimited_override=True)

        consumed, _ = await self._settle(sub, used=0, lifetime=900 * GB)

        self.assertEqual(consumed, 0)
        self.assertEqual(sub.topup_balance_bytes, 50 * GB)
        self.assertEqual(sub.traffic_period_lifetime_start_bytes, 900 * GB)


if __name__ == "__main__":
    unittest.main()
