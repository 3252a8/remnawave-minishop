"""Charge carried-over traffic packs for what each counter period used.

A regular traffic pack (``topup_balance_bytes``) is a carried-over balance, not a
monthly grant: the panel resets the period counter, but the pack must not come back
with it. Whatever the user spent beyond the period's own allowance came out of the
pack, so that amount is deducted when the counter resets.

The panel's lifetime counter minus its period counter stays constant within a period
and moves forward by the period's whole usage at a reset. Comparing it with the value
stored at the previous reset gives the exact usage of the period that ended, even when
the worker notices the reset late.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.traffic_reset import traffic_periods_between
from db.dal import tariff_dal

logger = logging.getLogger(__name__)


class TopupLimitSource(Protocol):
    def _extract_lifetime_used_traffic(self, panel_user_data: dict[str, Any]) -> int | None: ...

    def _compute_main_traffic_limit_bytes(
        self,
        *,
        tier_baseline_bytes: int,
        topup_balance_bytes: int,
        regular_bonus_bytes: int,
        regular_unlimited_override: bool,
        traffic_used_bytes: int,
        hwid_device_bonus_bytes: int = 0,
    ) -> int: ...

    def _hwid_traffic_bonus_bytes_from_summary(self, summary: dict[str, Any]) -> int: ...


@dataclass(frozen=True)
class TopupSettlement:
    balance_bytes: int
    period_lifetime_start_bytes: int | None
    consumed_bytes: int = 0


def _period_lifetime_start(used_bytes: int | None, lifetime_used_bytes: int | None) -> int | None:
    if used_bytes is None or lifetime_used_bytes is None:
        return None
    return max(0, int(lifetime_used_bytes) - int(used_bytes))


def settle_topup_at_counter_reset(
    *,
    balance_bytes: int,
    period_lifetime_start_bytes: int | None,
    used_bytes: int | None,
    lifetime_used_bytes: int | None,
    allowance_bytes: int,
) -> TopupSettlement:
    """Deduct the ended period's usage beyond ``allowance_bytes`` from the pack."""
    balance = max(0, int(balance_bytes or 0))
    period_start = _period_lifetime_start(used_bytes, lifetime_used_bytes)
    if period_start is None:
        return TopupSettlement(balance, period_lifetime_start_bytes)
    previous_start = period_lifetime_start_bytes
    if previous_start is None or period_start <= previous_start:
        # First observation, an unchanged period, or a recreated panel user whose
        # counters started over: no ended period is known.
        return TopupSettlement(balance, period_start)
    allowance = int(allowance_bytes or 0)
    if balance <= 0 or allowance <= 0:
        return TopupSettlement(balance, period_start)
    ended_period_used = period_start - previous_start
    consumed = min(balance, max(0, ended_period_used - allowance))
    return TopupSettlement(balance - consumed, period_start, consumed)


async def settle_regular_topup(
    session: AsyncSession,
    sub: Any,
    tariff: Any,
    *,
    subscription_service: TopupLimitSource,
    used_bytes: int | None,
    panel_user_data: dict[str, Any],
    previous_period_start: datetime | None,
    period_start: datetime | None,
    traffic_strategy: str,
    now: datetime,
) -> int:
    """Settle the pack of a period subscription and return the bytes deducted."""
    lifetime_used = subscription_service._extract_lifetime_used_traffic(panel_user_data)
    balance = max(0, int(getattr(sub, "topup_balance_bytes", 0) or 0))
    stored_start = getattr(sub, "traffic_period_lifetime_start_bytes", None)
    current_start = _period_lifetime_start(used_bytes, lifetime_used)
    allowance = 0
    if (
        balance > 0
        and stored_start is not None
        and current_start is not None
        and current_start > stored_start
    ):
        summary = await tariff_dal.get_hwid_device_entitlement_summary(
            session,
            subscription_id=sub.subscription_id,
            at=now,
            include_future=False,
        )
        baseline = int(
            getattr(sub, "tier_baseline_bytes", 0)
            or (getattr(tariff, "monthly_bytes", 0) if tariff else 0)
            or 0
        )
        per_period = subscription_service._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline,
            topup_balance_bytes=0,
            regular_bonus_bytes=int(getattr(sub, "regular_bonus_bytes", 0) or 0),
            regular_unlimited_override=bool(getattr(sub, "regular_unlimited_override", False)),
            traffic_used_bytes=0,
            hwid_device_bonus_bytes=subscription_service._hwid_traffic_bonus_bytes_from_summary(
                summary
            ),
        )
        allowance = per_period * traffic_periods_between(
            previous_period_start, period_start, traffic_strategy
        )
    settlement = settle_topup_at_counter_reset(
        balance_bytes=balance,
        period_lifetime_start_bytes=stored_start,
        used_bytes=used_bytes,
        lifetime_used_bytes=lifetime_used,
        allowance_bytes=allowance,
    )
    if settlement.period_lifetime_start_bytes != stored_start:
        sub.traffic_period_lifetime_start_bytes = settlement.period_lifetime_start_bytes
    if settlement.consumed_bytes:
        sub.topup_balance_bytes = settlement.balance_bytes
        logger.info(
            "Charged %s bytes of carried-over traffic to subscription %s at the counter "
            "reset; %s bytes remain.",
            settlement.consumed_bytes,
            sub.subscription_id,
            settlement.balance_bytes,
        )
    return settlement.consumed_bytes
