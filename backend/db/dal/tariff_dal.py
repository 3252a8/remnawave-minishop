import inspect
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import HwidDevicePurchase, Payment, TariffChange, TrafficTopup, TrafficWarning

from ._sqlalchemy import rowcount


async def create_traffic_topup(
    session: AsyncSession,
    *,
    subscription_id: int,
    payment_id: int | None,
    purchased_bytes: int,
    kind: str,
) -> TrafficTopup:
    record = TrafficTopup(
        subscription_id=subscription_id,
        payment_id=payment_id,
        purchased_bytes=purchased_bytes,
        kind=kind,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def sum_traffic_topups(
    session: AsyncSession,
    *,
    subscription_id: int,
    kinds: list[str] | None = None,
    created_at_gte: datetime | None = None,
) -> int:
    conditions = [TrafficTopup.subscription_id == subscription_id]
    if kinds:
        conditions.append(TrafficTopup.kind.in_(list(kinds)))
    if created_at_gte is not None:
        conditions.append(TrafficTopup.created_at >= created_at_gte)
    result = await session.execute(
        select(func.coalesce(func.sum(TrafficTopup.purchased_bytes), 0)).where(and_(*conditions))
    )
    return int(result.scalar() or 0)


async def create_hwid_device_purchase(
    session: AsyncSession,
    *,
    subscription_id: int,
    payment_id: int | None,
    purchased_devices: int,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> HwidDevicePurchase:
    record = HwidDevicePurchase(
        subscription_id=subscription_id,
        payment_id=payment_id,
        purchased_devices=purchased_devices,
        valid_from=valid_from or datetime.now(UTC),
        valid_until=valid_until,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


def _hwid_active_conditions(subscription_id: int, at: datetime) -> list[Any]:
    return [
        HwidDevicePurchase.subscription_id == subscription_id,
        HwidDevicePurchase.purchased_devices > 0,
        or_(HwidDevicePurchase.valid_from.is_(None), HwidDevicePurchase.valid_from <= at),
        or_(HwidDevicePurchase.valid_until.is_(None), HwidDevicePurchase.valid_until > at),
    ]


async def _resolve_result_value(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def sum_active_hwid_devices(
    session: AsyncSession,
    *,
    subscription_id: int,
    at: datetime | None = None,
) -> int:
    at = at or datetime.now(UTC)
    result = await session.execute(
        select(func.coalesce(func.sum(HwidDevicePurchase.purchased_devices), 0)).where(
            and_(*_hwid_active_conditions(subscription_id, at))
        )
    )
    return int(await _resolve_result_value(result.scalar()) or 0)


async def get_hwid_device_entitlement_summary(
    session: AsyncSession,
    *,
    subscription_id: int,
    at: datetime | None = None,
) -> dict[str, Any]:
    at = at or datetime.now(UTC)
    active_result = await session.execute(
        select(
            func.coalesce(func.sum(HwidDevicePurchase.purchased_devices), 0),
            func.max(HwidDevicePurchase.valid_until),
        ).where(and_(*_hwid_active_conditions(subscription_id, at)))
    )
    active_devices, active_until = await _resolve_result_value(active_result.one())
    future_result = await session.execute(
        select(func.min(HwidDevicePurchase.valid_from)).where(
            and_(
                HwidDevicePurchase.subscription_id == subscription_id,
                HwidDevicePurchase.purchased_devices > 0,
                HwidDevicePurchase.valid_from > at,
            )
        )
    )
    return {
        "active_devices": int(active_devices or 0),
        "active_until": active_until,
        "next_valid_from": await _resolve_result_value(future_result.scalar_one_or_none()),
    }


async def get_hwid_device_value_entries(
    session: AsyncSession,
    *,
    subscription_id: int,
    at: datetime | None = None,
) -> list[dict[str, Any]]:
    at = at or datetime.now(UTC)
    result = await session.execute(
        select(
            HwidDevicePurchase.purchase_id,
            HwidDevicePurchase.purchased_devices,
            HwidDevicePurchase.valid_from,
            HwidDevicePurchase.valid_until,
            HwidDevicePurchase.created_at,
            Payment.amount,
            Payment.currency,
        )
        .outerjoin(Payment, Payment.payment_id == HwidDevicePurchase.payment_id)
        .where(
            and_(
                HwidDevicePurchase.subscription_id == subscription_id,
                HwidDevicePurchase.purchased_devices > 0,
                or_(HwidDevicePurchase.valid_until.is_(None), HwidDevicePurchase.valid_until > at),
            )
        )
    )
    entries = []
    rows = await _resolve_result_value(result.all())
    for row in rows:
        entries.append(
            {
                "purchase_id": row[0],
                "purchased_devices": row[1],
                "valid_from": row[2],
                "valid_until": row[3],
                "created_at": row[4],
                "amount": row[5],
                "currency": row[6],
            }
        )
    return entries


async def expire_hwid_device_purchases(
    session: AsyncSession,
    *,
    purchase_ids: list[int],
    at: datetime | None = None,
) -> int:
    ids = [int(item) for item in purchase_ids if item is not None]
    if not ids:
        return 0
    at = at or datetime.now(UTC)
    result = await session.execute(
        update(HwidDevicePurchase)
        .where(HwidDevicePurchase.purchase_id.in_(ids))
        .values(valid_until=at)
    )
    return rowcount(result)


def _normalize_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def extend_hwid_device_purchases_for_subscription_bonus(
    session: AsyncSession,
    *,
    subscription_id: int,
    at: datetime | None = None,
    subscription_end_before: datetime | None = None,
    delta: timedelta,
) -> int:
    if delta.total_seconds() <= 0:
        return 0
    at = _normalize_aware_utc(at or datetime.now(UTC))
    end_before = _normalize_aware_utc(subscription_end_before) if subscription_end_before else None

    target_records: list[HwidDevicePurchase] = []
    if end_before:
        tail_result = await session.execute(
            select(HwidDevicePurchase).where(
                and_(
                    HwidDevicePurchase.subscription_id == subscription_id,
                    HwidDevicePurchase.purchased_devices > 0,
                    HwidDevicePurchase.valid_until.is_not(None),
                    HwidDevicePurchase.valid_until >= end_before,
                    HwidDevicePurchase.valid_until > at,
                    or_(
                        HwidDevicePurchase.valid_from.is_(None),
                        HwidDevicePurchase.valid_from < end_before,
                    ),
                )
            )
        )
        target_records = list(tail_result.scalars().all())

    if not target_records:
        active_result = await session.execute(
            select(HwidDevicePurchase).where(
                and_(
                    *_hwid_active_conditions(subscription_id, at),
                    HwidDevicePurchase.valid_until.is_not(None),
                )
            )
        )
        target_records = list(active_result.scalars().all())

    for record in target_records:
        if record.valid_until is not None:
            record.valid_until = _normalize_aware_utc(record.valid_until) + delta
    if target_records:
        await session.flush()
    return len(target_records)


async def create_tariff_change(
    session: AsyncSession,
    change_data: dict[str, Any],
) -> TariffChange:
    record = TariffChange(**change_data)
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def get_warning(
    session: AsyncSession,
    *,
    subscription_id: int,
    period_start_at: datetime | None,
    level: int,
    traffic_limit_bytes: int | None = None,
) -> TrafficWarning | None:
    """Return an existing traffic warning row if one was already recorded.

    For traffic-style billing ``period_start_at`` is NULL. Do **not** match on
    ``traffic_limit_bytes`` in that case: the effective limit can change between
    worker ticks (panel sync, top-ups, admin adjustments). Matching on the exact
    bytes caused duplicate Telegram alerts after restarts or the next poll.
    The ``traffic_limit_bytes`` argument is kept for call-site compatibility
    but is ignored when ``period_start_at`` is None.
    """
    conditions = [
        TrafficWarning.subscription_id == subscription_id,
        TrafficWarning.level == level,
    ]
    if period_start_at is None:
        conditions.append(TrafficWarning.period_start_at.is_(None))
    else:
        conditions.append(TrafficWarning.period_start_at == period_start_at)
    result = await session.execute(select(TrafficWarning).where(and_(*conditions)).limit(1))
    return result.scalar_one_or_none()


async def has_warning_level_between(
    session: AsyncSession,
    *,
    subscription_id: int,
    period_start_at: datetime | None,
    min_level: int,
    max_level: int,
) -> bool:
    conditions = [
        TrafficWarning.subscription_id == subscription_id,
        TrafficWarning.level >= min_level,
        TrafficWarning.level <= max_level,
    ]
    if period_start_at is None:
        conditions.append(TrafficWarning.period_start_at.is_(None))
    else:
        conditions.append(TrafficWarning.period_start_at == period_start_at)
    result = await session.execute(
        select(TrafficWarning.warning_id).where(and_(*conditions)).limit(1)
    )
    warning_id = await _resolve_result_value(result.scalar_one_or_none())
    return warning_id is not None


async def create_warning(
    session: AsyncSession,
    *,
    subscription_id: int,
    period_start_at: datetime | None,
    level: int,
    traffic_limit_bytes: int | None,
) -> TrafficWarning:
    record = TrafficWarning(
        subscription_id=subscription_id,
        period_start_at=period_start_at,
        level=level,
        traffic_limit_bytes=traffic_limit_bytes,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def clear_period_warnings(session: AsyncSession, subscription_id: int) -> int:
    result = await session.execute(
        delete(TrafficWarning).where(TrafficWarning.subscription_id == subscription_id)
    )
    return rowcount(result)


async def get_tariff_changes_for_subscription(
    session: AsyncSession, subscription_id: int
) -> list[TariffChange]:
    result = await session.execute(
        select(TariffChange)
        .where(TariffChange.subscription_id == subscription_id)
        .order_by(TariffChange.created_at.desc())
    )
    return list(result.scalars().all())
