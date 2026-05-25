from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import HwidDevicePurchase, TariffChange, TrafficTopup, TrafficWarning


async def create_traffic_topup(
    session: AsyncSession,
    *,
    subscription_id: int,
    payment_id: Optional[int],
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
    kinds: Optional[List[str]] = None,
    created_at_gte=None,
) -> int:
    conditions = [TrafficTopup.subscription_id == subscription_id]
    if kinds:
        conditions.append(TrafficTopup.kind.in_(list(kinds)))
    if created_at_gte is not None:
        conditions.append(TrafficTopup.created_at >= created_at_gte)
    result = await session.execute(
        select(func.coalesce(func.sum(TrafficTopup.purchased_bytes), 0)).where(
            and_(*conditions)
        )
    )
    return int(result.scalar() or 0)


async def create_hwid_device_purchase(
    session: AsyncSession,
    *,
    subscription_id: int,
    payment_id: Optional[int],
    purchased_devices: int,
) -> HwidDevicePurchase:
    record = HwidDevicePurchase(
        subscription_id=subscription_id,
        payment_id=payment_id,
        purchased_devices=purchased_devices,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def create_tariff_change(
    session: AsyncSession,
    change_data: Dict[str, Any],
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
    period_start_at,
    level: int,
    traffic_limit_bytes: Optional[int] = None,
) -> Optional[TrafficWarning]:
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


async def create_warning(
    session: AsyncSession,
    *,
    subscription_id: int,
    period_start_at,
    level: int,
    traffic_limit_bytes: Optional[int],
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
    return result.rowcount or 0


async def get_tariff_changes_for_subscription(
    session: AsyncSession, subscription_id: int
) -> List[TariffChange]:
    result = await session.execute(
        select(TariffChange)
        .where(TariffChange.subscription_id == subscription_id)
        .order_by(TariffChange.created_at.desc())
    )
    return list(result.scalars().all())
