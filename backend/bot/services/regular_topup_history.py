"""Recover separate regular counter periods from complete panel daily history.

Daily statistics are accepted only when they reconcile with the lifetime
delta. Truncated retention, missing nodes, and malformed results must never
turn into invented usage or retrospective charges against a paid balance.
"""

import logging
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.date_utils import add_months
from bot.utils.traffic_reset import aware_utc, normalize_traffic_limit_strategy
from db.dal import tariff_dal
from db.dal.tariff_read_batch import current_tariff_read_batch
from db.models import HwidDevicePurchase

logger = logging.getLogger(__name__)


class RegularUsageSource(Protocol):
    async def get_user_bandwidth_stats(
        self,
        user_uuid: str,
        *,
        start: str | None = None,
        end: str | None = None,
        top_nodes_limit: int = 20,
    ) -> dict[str, Any] | None: ...


def regular_period_boundaries(
    start: datetime, end: datetime, strategy: str
) -> list[datetime] | None:
    """Calendar boundaries ignore scheduler latency, while retaining rolling dates."""
    first = datetime.combine(start.date(), datetime.min.time(), UTC)
    last = datetime.combine(end.date(), datetime.min.time(), UTC)
    normalized = normalize_traffic_limit_strategy(strategy, default="MONTH")
    if last <= first or normalized == "NO_RESET":
        return None
    boundaries = [first]
    index = 1
    while boundaries[-1] < last:
        if normalized == "DAY":
            candidate = first + timedelta(days=index)
        elif normalized == "WEEK":
            candidate = first + timedelta(days=7 * index)
        else:
            candidate = add_months(first, index)
        if candidate > last:
            return None
        boundaries.append(candidate)
        index += 1
    return boundaries


def daily_traffic_bytes(
    payload: dict[str, Any], start: datetime, end: datetime, expected_bytes: int
) -> dict[datetime, int] | None:
    """Read all-node bytes, never the truncated topNodes leaderboard."""
    categories = payload.get("categories")
    values = payload.get("sparklineData")
    if not isinstance(categories, list):
        return None
    if values is None:
        series = payload.get("series")
        if not isinstance(series, list) or not series:
            return None
        vectors: list[list[Any]] = []
        for row in series:
            vector = row.get("data") if isinstance(row, dict) else None
            if not isinstance(vector, list) or len(vector) != len(categories):
                return None
            vectors.append(vector)
        values = []
        for index in range(len(categories)):
            entries = [vector[index] for vector in vectors]
            if any(not _valid_bytes(value) for value in entries):
                return None
            values.append(sum(int(value) for value in entries))
    if not isinstance(values, list) or len(values) != len(categories):
        return None
    result: dict[datetime, int] = {}
    for category, value in zip(categories, values, strict=True):
        if not isinstance(category, str) or not _valid_bytes(value):
            return None
        try:
            day = datetime.strptime(category, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return None
        if day in result or day < start or day >= end:
            return None
        result[day] = int(value)
    expected_days = (end - start).days
    if len(result) != expected_days or sum(result.values()) != expected_bytes:
        return None
    return result


def _valid_bytes(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 2**53 - 1
        and int(value) == value
    )


async def read_regular_period_usage(
    source: RegularUsageSource | None,
    panel_user_uuid: str,
    boundaries: list[datetime],
    expected_bytes: int,
) -> list[int] | None:
    if source is None:
        return None
    try:
        payload = await source.get_user_bandwidth_stats(
            panel_user_uuid,
            start=boundaries[0].date().isoformat(),
            end=(boundaries[-1] - timedelta(days=1)).date().isoformat(),
        )
    except Exception:
        logger.warning("Regular traffic history lookup failed; keeping unconfirmed traffic.")
        return None
    if not isinstance(payload, dict):
        return None
    daily = daily_traffic_bytes(payload, boundaries[0], boundaries[-1], expected_bytes)
    if daily is None:
        return None
    return [
        sum(value for day, value in daily.items() if start <= day < end)
        for start, end in pairwise(boundaries)
    ]


async def historical_allowance_observations(
    session: AsyncSession,
    subscription_id: int,
    start: datetime,
    end: datetime,
) -> list[datetime]:
    """Observe every entitlement change, including rights expiring before reset.

    Daily history cannot tell which side of an intraday entitlement change served
    traffic. The maximum historical allowance is therefore a conservative bound:
    usage is charged only when it exceeds every allowance available in that period.
    """
    batch = current_tariff_read_batch(session)
    if batch is not None and subscription_id in batch.subscription_ids:
        records = [*batch.flexible.get(subscription_id, []), *batch.hwid.get(subscription_id, [])]
    else:
        flexible = await tariff_dal.list_flexible_traffic_limit_records_in_window(
            session, subscription_id=subscription_id, valid_from=start, valid_until=end
        )
        result = await session.scalars(
            select(HwidDevicePurchase).where(
                HwidDevicePurchase.subscription_id == subscription_id,
                or_(HwidDevicePurchase.valid_from.is_(None), HwidDevicePurchase.valid_from < end),
                or_(
                    HwidDevicePurchase.valid_until.is_(None), HwidDevicePurchase.valid_until > start
                ),
            )
        )
        records = [*flexible, *result.all()]
    moments = {start, end - timedelta(microseconds=1)}
    for record in records:
        for value in (record.valid_from, record.valid_until):
            moment = aware_utc(value)
            if moment is not None and start < moment < end:
                moments.update((moment, moment - timedelta(microseconds=1)))
    return sorted(moments)
