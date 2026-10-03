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
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.regular_topup_history import (
    RegularUsageSource,
    historical_allowance_observations,
    read_regular_period_usage,
    regular_period_boundaries,
)
from bot.services.subscription_service_impl.traffic import resolve_main_traffic_baseline
from bot.services.traffic_topup_accounting import consume_topup_overflow
from bot.utils.traffic_reset import (
    aware_utc,
    normalize_traffic_limit_strategy,
    traffic_periods_between,
)
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


def _period_lifetime_start(used_bytes: int | None, lifetime_used_bytes: int | None) -> int | None:
    if used_bytes is None or lifetime_used_bytes is None:
        return None
    if used_bytes < 0 or lifetime_used_bytes < used_bytes:
        return None
    return int(lifetime_used_bytes) - int(used_bytes)


class RegularTopupPeriod(BaseModel):
    """The lifetime anchor and the quota it belongs to form one persisted snapshot."""

    model_config = ConfigDict(extra="forbid", strict=True)

    period_start_at: datetime
    lifetime_start_bytes: int = Field(ge=0)
    allowance_bytes: int = Field(ge=0)
    observed_used_bytes: int = Field(ge=0)
    observed_overflow_bytes: int = Field(ge=0)
    panel_user_uuid: str
    traffic_strategy: str
    tariff_baseline_bytes: int = Field(ge=0)
    regular_bonus_bytes: int = Field(ge=0)
    unlimited: bool
    legacy_device_quota_bytes: int = Field(default=0, ge=0)
    strategy_changed: bool = False


def regular_topup_period(sub: Any) -> RegularTopupPeriod | None:
    value = getattr(sub, "traffic_topup_accounting_state", None)
    if not isinstance(value, str) or not value:
        return None
    try:
        state = RegularTopupPeriod.model_validate_json(value)
        return state.model_copy(
            update={"period_start_at": aware_utc(state.period_start_at) or state.period_start_at}
        )
    except ValidationError:
        logger.warning("Invalid regular traffic accounting snapshot; starting a new observation.")
        return None


def _save_period(sub: Any, state: RegularTopupPeriod) -> None:
    sub.traffic_topup_accounting_state = state.model_dump_json()
    sub.traffic_period_lifetime_start_bytes = state.lifetime_start_bytes


def regular_accounting_traffic_limit(sub: Any, calculated_limit: int) -> int:
    """Keep already served quota when a device/flexible entitlement expires."""
    state = regular_topup_period(sub)
    if state is None or calculated_limit <= 0 or state.allowance_bytes <= 0:
        return calculated_limit
    # The worker has already refreshed this snapshot for the observed counter.
    return max(calculated_limit, state.allowance_bytes + max(0, int(sub.topup_balance_bytes or 0)))


async def _current_period(
    session: AsyncSession,
    sub: Any,
    tariff: Any,
    source: TopupLimitSource,
    period_start: datetime,
    lifetime_start: int,
    used: int,
    strategy: str,
    now: datetime,
    previous: RegularTopupPeriod | None = None,
) -> RegularTopupPeriod:
    summary = await tariff_dal.get_hwid_device_entitlement_summary(
        session, subscription_id=sub.subscription_id, at=now, include_future=False
    )
    baseline = await resolve_main_traffic_baseline(session, sub, tariff, at=now)
    regular_bonus = max(0, int(getattr(sub, "regular_bonus_bytes", 0) or 0))
    allowance = source._compute_main_traffic_limit_bytes(
        tier_baseline_bytes=baseline,
        topup_balance_bytes=0,
        regular_bonus_bytes=regular_bonus,
        regular_unlimited_override=bool(getattr(sub, "regular_unlimited_override", False)),
        traffic_used_bytes=0,
        hwid_device_bonus_bytes=source._hwid_traffic_bonus_bytes_from_summary(summary),
    )
    observed_overflow = previous.observed_overflow_bytes if previous else 0
    if previous is not None and allowance > 0:
        # A quota reduction cannot retroactively charge traffic served under a
        # larger (or unlimited) quota, including traffic since the last poll.
        # Only the served part survives; unused expired quota is not retained.
        possibly_served = max(0, used - observed_overflow)
        if previous.allowance_bytes > 0:
            possibly_served = min(previous.allowance_bytes, possibly_served)
        allowance = max(
            allowance, possibly_served, previous.observed_used_bytes - observed_overflow
        )
    if allowance > 0:
        observed_overflow = max(
            observed_overflow,
            min(max(0, int(sub.topup_balance_bytes or 0)), max(0, used - allowance)),
        )
    return RegularTopupPeriod(
        period_start_at=period_start,
        lifetime_start_bytes=lifetime_start,
        allowance_bytes=max(0, allowance),
        observed_used_bytes=max(used, previous.observed_used_bytes if previous else 0),
        observed_overflow_bytes=observed_overflow,
        panel_user_uuid=str(getattr(sub, "panel_user_uuid", "") or ""),
        traffic_strategy=strategy,
        tariff_baseline_bytes=max(0, int(getattr(tariff, "monthly_bytes", 0) or 0)),
        regular_bonus_bytes=regular_bonus,
        unlimited=allowance <= 0,
        legacy_device_quota_bytes=max(
            0, source._hwid_traffic_bonus_bytes_from_summary({"legacy_active_devices": 1})
        ),
        strategy_changed=bool(
            previous and (previous.strategy_changed or previous.traffic_strategy != strategy)
        ),
    )


async def _historical_allowance(
    session: AsyncSession,
    sub: Any,
    tariff: Any,
    source: TopupLimitSource,
    state: RegularTopupPeriod,
    start: datetime,
    end: datetime,
    moments: list[datetime],
) -> int:
    allowances = [state.allowance_bytes] if start == state.period_start_at else []
    for moment in sorted({start, *moments}):
        if not start <= moment < end:
            continue
        limits = await tariff_dal.get_active_flexible_traffic_limits(
            session, subscription_id=sub.subscription_id, at=moment
        )
        summary = await tariff_dal.get_hwid_device_entitlement_summary(
            session, subscription_id=sub.subscription_id, at=moment, include_future=False
        )
        allowances.append(
            source._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=limits.get(
                    "traffic",
                    max(state.tariff_baseline_bytes, int(getattr(tariff, "monthly_bytes", 0) or 0)),
                ),
                topup_balance_bytes=0,
                regular_bonus_bytes=max(
                    state.regular_bonus_bytes, int(getattr(sub, "regular_bonus_bytes", 0) or 0)
                ),
                regular_unlimited_override=(
                    state.unlimited or bool(getattr(sub, "regular_unlimited_override", False))
                ),
                traffic_used_bytes=0,
                hwid_device_bonus_bytes=max(
                    source._hwid_traffic_bonus_bytes_from_summary(summary),
                    int(summary.get("traffic_bonus_bytes") or 0)
                    + int(summary.get("legacy_active_devices") or 0)
                    * state.legacy_device_quota_bytes,
                ),
            )
        )
    return 0 if 0 in allowances else max(allowances, default=state.allowance_bytes)


async def _history_consumption(
    session: AsyncSession,
    sub: Any,
    tariff: Any,
    source: TopupLimitSource,
    usage_source: RegularUsageSource | None,
    state: RegularTopupPeriod,
    current_period_start: datetime,
    ended_used: int,
    balance: int,
) -> int | None:
    boundaries = regular_period_boundaries(
        state.period_start_at, current_period_start, state.traffic_strategy
    )
    if boundaries is None or any(
        (value.hour, value.minute, value.second, value.microsecond) != (0, 0, 0, 0)
        for value in (state.period_start_at, current_period_start)
    ):
        # Daily statistics cannot locate traffic across a reset inside a UTC day.
        return None
    usage = await read_regular_period_usage(
        usage_source, state.panel_user_uuid, boundaries, ended_used
    )
    if usage is None:
        return None
    moments = await historical_allowance_observations(
        session, sub.subscription_id, boundaries[0], boundaries[-1]
    )
    remaining = balance
    for index, (start, end, used) in enumerate(
        zip(boundaries[:-1], boundaries[1:], usage, strict=True)
    ):
        allowance = await _historical_allowance(
            session, sub, tariff, source, state, start, end, moments
        )
        known_overflow = state.observed_overflow_bytes if index == 0 else 0
        overflow = max(known_overflow, max(0, used - allowance) if allowance > 0 else 0)
        result = consume_topup_overflow(
            balance_bytes=remaining, traffic_used_bytes=overflow, allowance_bytes=0
        )
        remaining = result.balance_bytes
    return balance - remaining


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
    usage_source: RegularUsageSource | None = None,
) -> int:
    """Close regular periods using their own quotas; keep unconfirmed history safe."""
    lifetime_used = subscription_service._extract_lifetime_used_traffic(panel_user_data)
    balance = max(0, int(getattr(sub, "topup_balance_bytes", 0) or 0))
    current_start = _period_lifetime_start(used_bytes, lifetime_used)
    if current_start is None or used_bytes is None:
        return 0
    current_date = aware_utc(period_start) or aware_utc(previous_period_start) or now
    strategy = normalize_traffic_limit_strategy(traffic_strategy, default="MONTH")
    state = regular_topup_period(sub)
    if state is not None and (
        state.panel_user_uuid != str(getattr(sub, "panel_user_uuid", "") or "")
        or current_start < state.lifetime_start_bytes
    ):
        state = None
    if state is None:
        # Upgrades and new panel identities start from an actual observation.
        # The legacy lifetime-only anchor has no associated historical quota/date.
        _save_period(
            sub,
            await _current_period(
                session,
                sub,
                tariff,
                subscription_service,
                current_date,
                current_start,
                used_bytes,
                strategy,
                now,
            ),
        )
        return 0
    if current_start == state.lifetime_start_bytes:
        if used_bytes < state.observed_used_bytes:
            return 0  # stale/out-of-order panel statistics must not restore usage
        zero_period_ended = used_bytes == 0 and current_date > state.period_start_at
        _save_period(
            sub,
            await _current_period(
                session,
                sub,
                tariff,
                subscription_service,
                current_date if zero_period_ended else state.period_start_at,
                current_start,
                used_bytes,
                strategy,
                now,
                previous=None if zero_period_ended else state,
            ),
        )
        return 0
    ended_used = current_start - state.lifetime_start_bytes
    if ended_used < state.observed_used_bytes:
        return 0  # an incoherent reset snapshot is not evidence of a closed period
    periods = traffic_periods_between(state.period_start_at, current_date, state.traffic_strategy)
    consumed: int | None = None
    same_strategy = strategy == state.traffic_strategy and not state.strategy_changed
    if same_strategy and periods == 1:
        allowance = state.allowance_bytes
        if current_date > state.period_start_at and balance > 0:
            # A grant can begin and expire while the worker is offline. Its DB
            # history still protects served traffic at a single counter reset.
            moments = await historical_allowance_observations(
                session, sub.subscription_id, state.period_start_at, current_date
            )
            allowance = await _historical_allowance(
                session,
                sub,
                tariff,
                subscription_service,
                state,
                state.period_start_at,
                current_date,
                moments,
            )
        overflow = max(
            state.observed_overflow_bytes,
            max(0, ended_used - allowance) if allowance > 0 else 0,
        )
        consumed = consume_topup_overflow(
            balance_bytes=balance, traffic_used_bytes=overflow, allowance_bytes=0
        ).consumed_bytes
    elif same_strategy and balance > 0:
        consumed = await _history_consumption(
            session,
            sub,
            tariff,
            subscription_service,
            usage_source,
            state,
            current_date,
            ended_used,
            balance,
        )
    if consumed is None:
        # No fabricated aggregate quota: only previously observed overflow is
        # provable when the panel has discarded history or changed strategy.
        consumed = consume_topup_overflow(
            balance_bytes=balance,
            traffic_used_bytes=state.observed_overflow_bytes,
            allowance_bytes=0,
        ).consumed_bytes
        if balance > consumed:
            logger.warning(
                "Incomplete regular traffic history for subscription %s across %s periods; "
                "charging only %s confirmed bytes.",
                sub.subscription_id,
                periods,
                consumed,
            )
    sub.topup_balance_bytes = balance - consumed
    _save_period(
        sub,
        await _current_period(
            session,
            sub,
            tariff,
            subscription_service,
            current_date,
            current_start,
            used_bytes,
            strategy,
            now,
        ),
    )
    if consumed:
        logger.info(
            "Charged %s bytes of carried-over traffic to subscription %s at the counter "
            "reset; %s bytes remain.",
            consumed,
            sub.subscription_id,
            sub.topup_balance_bytes,
        )
    return consumed
