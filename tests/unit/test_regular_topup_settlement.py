"""A carried-over traffic pack is charged at each counter reset, not re-granted."""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from bot.services.regular_topup_settlement import (
    RegularTopupPeriod,
    regular_accounting_traffic_limit,
    regular_topup_period,
    settle_regular_topup,
)
from bot.utils.traffic_reset import traffic_periods_between

GB = 1024**3


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
        _extract_lifetime_used_traffic=lambda data: data["userTraffic"].get(
            "lifetimeUsedTrafficBytes"
        ),
        _compute_main_traffic_limit_bytes=limit,
        _hwid_traffic_bonus_bytes_from_summary=lambda summary: summary.get(
            "traffic_bonus_bytes", device_bonus
        ),
    )


class SettleRegularTopupTests(unittest.IsolatedAsyncioTestCase):
    def _sub(self, **overrides: Any) -> SimpleNamespace:
        state_start = overrides.pop("state_start", datetime(2026, 9, 1, tzinfo=UTC))
        state_allowance = overrides.pop("state_allowance", 50 * GB)
        state_used = overrides.pop("state_used", 0)
        state_overflow = overrides.pop("state_overflow", 0)
        values: dict[str, Any] = {
            "subscription_id": 62,
            "panel_user_uuid": "panel-62",
            "topup_balance_bytes": 50 * GB,
            "traffic_period_lifetime_start_bytes": 480 * GB,
            "tier_baseline_bytes": 50 * GB,
            "regular_bonus_bytes": 0,
            "regular_unlimited_override": False,
        }
        values.update(overrides)
        state = RegularTopupPeriod(
            period_start_at=state_start,
            lifetime_start_bytes=values["traffic_period_lifetime_start_bytes"],
            allowance_bytes=0 if values["regular_unlimited_override"] else state_allowance,
            observed_used_bytes=state_used,
            observed_overflow_bytes=state_overflow,
            panel_user_uuid="panel-62",
            traffic_strategy="MONTH",
            tariff_baseline_bytes=50 * GB,
            regular_bonus_bytes=0,
            unlimited=bool(values["regular_unlimited_override"]),
        )
        values.setdefault("traffic_topup_accounting_state", state.model_dump_json())
        return SimpleNamespace(**values)

    async def _settle(
        self,
        sub: SimpleNamespace,
        *,
        used: int,
        lifetime: int | None,
        device_bonus: int = 0,
        previous: datetime = datetime(2026, 9, 1, tzinfo=UTC),
        current: datetime = datetime(2026, 10, 1, tzinfo=UTC),
        current_baseline: int | None = None,
        history: dict[str, Any] | None = None,
        strategy: str = "MONTH",
    ) -> tuple[int, AsyncMock]:
        summary = AsyncMock(
            side_effect=lambda _session, **kw: {
                "traffic_bonus_bytes": device_bonus if kw["at"] >= current else 0
            }
        )
        with (
            patch(
                "bot.services.regular_topup_settlement.tariff_dal."
                "get_hwid_device_entitlement_summary",
                summary,
            ),
            patch(
                "bot.services.regular_topup_settlement.resolve_main_traffic_baseline",
                AsyncMock(
                    return_value=(
                        sub.tier_baseline_bytes if current_baseline is None else current_baseline
                    )
                ),
            ),
            patch(
                "bot.services.regular_topup_settlement.historical_allowance_observations",
                AsyncMock(return_value=[previous]),
            ),
            patch(
                "bot.services.regular_topup_settlement.tariff_dal.get_active_flexible_traffic_limits",
                AsyncMock(return_value={}),
            ),
        ):
            consumed = await settle_regular_topup(
                AsyncMock(),
                sub,
                SimpleNamespace(monthly_bytes=50 * GB),
                subscription_service=_service(device_bonus),
                used_bytes=used,
                panel_user_data={"userTraffic": {"lifetimeUsedTrafficBytes": lifetime}},
                previous_period_start=previous,
                period_start=current,
                traffic_strategy=strategy,
                now=current + timedelta(minutes=5),
                usage_source=SimpleNamespace(
                    get_user_bandwidth_stats=AsyncMock(return_value=history)
                ),
            )
        return consumed, summary

    async def test_reset_charges_the_pack_beyond_base_and_device_bonus(self) -> None:
        # Allowance is 50 GB base plus 15 GB device bonus; the period used 80 GB.
        sub = self._sub(state_allowance=65 * GB)

        consumed, _ = await self._settle(sub, used=0, lifetime=560 * GB, device_bonus=15 * GB)

        self.assertEqual(consumed, 15 * GB)
        self.assertEqual(sub.topup_balance_bytes, 35 * GB)
        self.assertEqual(sub.traffic_period_lifetime_start_bytes, 560 * GB)

    async def test_spent_pack_leaves_only_the_base_limit(self) -> None:
        sub = self._sub()

        consumed, _ = await self._settle(sub, used=2 * GB, lifetime=592 * GB)

        self.assertEqual(consumed, 50 * GB)
        self.assertEqual(sub.topup_balance_bytes, 0)

    async def test_period_in_progress_keeps_the_balance_and_refreshes_quota(self) -> None:
        sub = self._sub()

        consumed, summary = await self._settle(sub, used=30 * GB, lifetime=510 * GB)

        self.assertEqual(consumed, 0)
        summary.assert_awaited_once()
        self.assertEqual(sub.topup_balance_bytes, 50 * GB)
        self.assertEqual(sub.traffic_period_lifetime_start_bytes, 480 * GB)

    async def test_missed_resets_use_one_allowance_per_period(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        sub = self._sub(state_start=start)

        consumed, _ = await self._settle(
            sub,
            used=0,
            lifetime=610 * GB,
            previous=start,
            history=_history(start, datetime(2026, 10, 1, tzinfo=UTC), {0: 80 * GB, 31: 50 * GB}),
        )

        self.assertEqual(consumed, 30 * GB)

    async def test_unlimited_override_keeps_the_pack(self) -> None:
        sub = self._sub(regular_unlimited_override=True)

        consumed, _ = await self._settle(sub, used=0, lifetime=900 * GB)

        self.assertEqual(consumed, 0)
        self.assertEqual(sub.topup_balance_bytes, 50 * GB)
        self.assertEqual(sub.traffic_period_lifetime_start_bytes, 900 * GB)

    async def test_expired_device_rights_do_not_reclassify_the_ended_period(self) -> None:
        sub = self._sub(state_allowance=65 * GB, state_used=60 * GB)
        consumed, _ = await self._settle(sub, used=0, lifetime=540 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (0, 50 * GB))

    async def test_new_device_rights_do_not_cover_the_previous_period(self) -> None:
        sub = self._sub()
        consumed, _ = await self._settle(sub, used=0, lifetime=540 * GB, device_bonus=15 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (10 * GB, 40 * GB))

    async def test_expired_flexible_quota_uses_its_saved_period_allowance(self) -> None:
        sub = self._sub(state_allowance=100 * GB, state_used=80 * GB, tier_baseline_bytes=100 * GB)
        consumed, _ = await self._settle(sub, used=0, lifetime=560 * GB, current_baseline=50 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (0, 50 * GB))
        state = regular_topup_period(sub)
        assert state is not None
        self.assertEqual(state.allowance_bytes, 50 * GB)

    async def test_unused_quota_of_another_period_does_not_restore_a_spent_pack(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        sub = self._sub(state_start=start)
        consumed, _ = await self._settle(
            sub,
            used=0,
            lifetime=580 * GB,
            previous=start,
            history=_history(start, datetime(2026, 10, 1, tzinfo=UTC), {0: 80 * GB, 31: 20 * GB}),
        )
        self.assertEqual((consumed, sub.topup_balance_bytes), (30 * GB, 20 * GB))

    async def test_missing_history_keeps_confirmed_consumption_without_guessing(self) -> None:
        sub = self._sub(
            state_start=datetime(2026, 8, 1, tzinfo=UTC),
            state_used=80 * GB,
            state_overflow=30 * GB,
        )
        consumed, _ = await self._settle(sub, used=0, lifetime=580 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (30 * GB, 20 * GB))

    async def test_lifetime_return_uses_the_date_of_its_own_anchor(self) -> None:
        sub = self._sub()
        snapshot = sub.traffic_topup_accounting_state
        await self._settle(sub, used=0, lifetime=None)
        self.assertEqual(sub.traffic_topup_accounting_state, snapshot)
        consumed, _ = await self._settle(
            sub,
            used=0,
            lifetime=580 * GB,
            previous=datetime(2026, 10, 1, tzinfo=UTC),
            current=datetime(2026, 11, 1, tzinfo=UTC),
        )
        self.assertEqual((consumed, sub.topup_balance_bytes), (0, 50 * GB))

    async def test_upgrade_without_a_paired_snapshot_does_not_rebill_old_usage(self) -> None:
        sub = self._sub(traffic_topup_accounting_state=None)
        consumed, _ = await self._settle(sub, used=2 * GB, lifetime=592 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (0, 50 * GB))
        self.assertEqual(sub.traffic_period_lifetime_start_bytes, 590 * GB)

    async def test_recreated_panel_identity_keeps_the_paid_balance(self) -> None:
        for overrides, lifetime in [({"panel_user_uuid": "new-panel"}, 900 * GB), ({}, 5 * GB)]:
            with self.subTest(overrides=overrides):
                sub = self._sub(**overrides)
                consumed, _ = await self._settle(sub, used=5 * GB, lifetime=lifetime)
                self.assertEqual((consumed, sub.topup_balance_bytes), (0, 50 * GB))

    async def test_served_device_quota_is_preserved_when_rights_expire_mid_period(self) -> None:
        sub = self._sub(state_allowance=65 * GB, state_used=60 * GB)
        consumed, _ = await self._settle(sub, used=60 * GB, lifetime=540 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (0, 50 * GB))
        self.assertEqual(regular_accounting_traffic_limit(sub, 100 * GB), 110 * GB)
        state = regular_topup_period(sub)
        assert state is not None
        self.assertEqual(state.allowance_bytes, 60 * GB)  # the unused 5 GB expired

    async def test_quota_increase_does_not_restore_confirmed_packet_consumption(self) -> None:
        sub = self._sub(state_used=80 * GB, state_overflow=30 * GB)
        await self._settle(sub, used=80 * GB, lifetime=560 * GB, current_baseline=100 * GB)
        consumed, _ = await self._settle(sub, used=0, lifetime=560 * GB, current_baseline=100 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (30 * GB, 20 * GB))

    async def test_expiry_does_not_charge_traffic_served_since_the_previous_poll(self) -> None:
        sub = self._sub(state_allowance=65 * GB, state_used=55 * GB)
        await self._settle(sub, used=64 * GB, lifetime=544 * GB)
        state = regular_topup_period(sub)
        assert state is not None
        self.assertEqual((state.allowance_bytes, state.observed_overflow_bytes), (64 * GB, 0))
        consumed, _ = await self._settle(sub, used=0, lifetime=544 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (0, 50 * GB))

    async def test_strategy_change_and_revert_cannot_fabricate_period_allowances(self) -> None:
        sub = self._sub(state_used=80 * GB, state_overflow=30 * GB)
        await self._settle(sub, used=80 * GB, lifetime=560 * GB, strategy="DAY")
        await self._settle(sub, used=80 * GB, lifetime=560 * GB, strategy="MONTH")
        consumed, _ = await self._settle(sub, used=0, lifetime=590 * GB)
        self.assertEqual((consumed, sub.topup_balance_bytes), (30 * GB, 20 * GB))

    async def test_duplicate_reset_observation_cannot_charge_twice(self) -> None:
        sub = self._sub()
        first, _ = await self._settle(sub, used=0, lifetime=560 * GB)
        second, _ = await self._settle(sub, used=0, lifetime=560 * GB)
        self.assertEqual((first, second, sub.topup_balance_bytes), (30 * GB, 0, 20 * GB))

    async def test_invalid_or_stale_counters_do_not_replace_the_snapshot(self) -> None:
        sub = self._sub(state_used=80 * GB, state_overflow=30 * GB)
        snapshot = sub.traffic_topup_accounting_state
        for used, lifetime in [(90 * GB, 80 * GB), (70 * GB, 550 * GB), (0, 500 * GB)]:
            with self.subTest(used=used, lifetime=lifetime):
                consumed, _ = await self._settle(sub, used=used, lifetime=lifetime)
                self.assertEqual((consumed, sub.traffic_topup_accounting_state), (0, snapshot))


def _history(start: datetime, end: datetime, usage: dict[int, int]) -> dict[str, Any]:
    days = (end - start).days
    return {
        "categories": [(start + timedelta(days=index)).date().isoformat() for index in range(days)],
        "sparklineData": [usage.get(index, 0) for index in range(days)],
        "topNodes": [{"total": 1}],  # leaderboard totals are intentionally irrelevant
    }


if __name__ == "__main__":
    unittest.main()
