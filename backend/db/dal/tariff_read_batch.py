"""Transaction-scoped entitlement reads for bounded subscription worker batches."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from itertools import chain
from typing import Any

from sqlalchemy import Integer, Select, bindparam, event, false, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction
from sqlalchemy.orm import Session, aliased

from db.models import (
    FlexibleTrafficLimit,
    HwidDevicePurchase,
    Subscription,
    TrafficTopup,
    UserPanelSquadOverride,
)

_KEY = "tariff_read_batch"
_ENTITLEMENTS = (FlexibleTrafficLimit, HwidDevicePurchase, TrafficTopup)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass
class TariffReadBatch:
    transaction: AsyncSessionTransaction | None
    subscription_ids: set[int]
    user_ids: set[int]
    panel_ids: set[str]
    flexible: dict[int, list[FlexibleTrafficLimit]] = field(default_factory=dict)
    hwid: dict[int, list[HwidDevicePurchase]] = field(default_factory=dict)
    topups: dict[int, list[TrafficTopup]] = field(default_factory=dict)
    overrides: list[UserPanelSquadOverride] = field(default_factory=list)

    def active_limits(self, subscription_id: int, at: datetime) -> dict[str, int]:
        limits: dict[str, int] = {}
        for row in self.flexible.get(subscription_id, []):
            if utc(row.valid_from) <= utc(at) < utc(row.valid_until):
                limits[row.kind] = max(limits.get(row.kind, 0), int(row.limit_bytes or 0))
        return limits

    def hwid_summary(self, subscription_id: int, at: datetime, future: bool) -> dict[str, Any]:
        rows = self.hwid.get(subscription_id, [])
        active = [
            row
            for row in rows
            if row.purchased_devices > 0
            and (row.valid_from is None or utc(row.valid_from) <= utc(at))
            and (row.valid_until is None or utc(row.valid_until) > utc(at))
        ]
        ends = [row.valid_until for row in active if row.valid_until is not None]
        starts = [
            row.valid_from
            for row in rows
            if future
            and row.purchased_devices > 0
            and row.valid_from is not None
            and utc(row.valid_from) > utc(at)
        ]
        return {
            "active_devices": sum(row.purchased_devices for row in active),
            "active_until": max(ends, key=utc) if ends else None,
            "traffic_bonus_bytes": sum(int(row.traffic_bonus_bytes or 0) for row in active),
            "legacy_active_devices": sum(
                row.purchased_devices for row in active if row.traffic_bonus_bytes is None
            ),
            "next_valid_from": min(starts, key=utc) if starts else None,
        }


def current_tariff_read_batch(session: AsyncSession) -> TariffReadBatch | None:
    if not isinstance(session, AsyncSession):
        return None
    batch = _invalidate_pending_writes(session)
    if isinstance(batch, TariffReadBatch) and batch.transaction is session.get_transaction():
        return batch
    session.info.pop(_KEY, None)
    return None


def clear_tariff_read_batch(session: AsyncSession) -> None:
    if isinstance(session, AsyncSession):
        session.info.pop(_KEY, None)


def invalidate_user_overrides(session: AsyncSession, user_id: int) -> None:
    if isinstance(session, AsyncSession):
        batch = session.info.get(_KEY)
        if isinstance(batch, TariffReadBatch):
            batch.user_ids.discard(user_id)


def _invalidate_pending_writes(session: Session | AsyncSession) -> TariffReadBatch | None:
    batch = session.info.get(_KEY)
    if not isinstance(batch, TariffReadBatch):
        return None
    for row in chain(session.new, session.dirty, session.deleted):
        if isinstance(row, _ENTITLEMENTS):
            session.info.pop(_KEY, None)
            return None
        if isinstance(row, UserPanelSquadOverride):
            if row not in session.new and inspect(row).attrs.user_id.history.has_changes():
                batch.user_ids.clear()
            else:
                batch.user_ids.discard(row.user_id)
    return batch


@event.listens_for(Session, "before_flush")
def _invalidate_changed_entitlements(session: Session, context: Any, instances: Any) -> None:
    _invalidate_pending_writes(session)


@cache
def _entitlement_rows() -> Select[
    tuple[FlexibleTrafficLimit, HwidDevicePurchase, TrafficTopup, UserPanelSquadOverride]
]:
    ids = bindparam("subscription_ids", type_=Integer, expanding=True)
    limits = aliased(
        FlexibleTrafficLimit,
        select(FlexibleTrafficLimit)
        .where(FlexibleTrafficLimit.subscription_id.in_(ids))
        .subquery(),
    )
    devices = aliased(
        HwidDevicePurchase,
        select(HwidDevicePurchase).where(HwidDevicePurchase.subscription_id.in_(ids)).subquery(),
    )
    topups = aliased(
        TrafficTopup, select(TrafficTopup).where(TrafficTopup.subscription_id.in_(ids)).subquery()
    )
    overrides = aliased(
        UserPanelSquadOverride,
        select(UserPanelSquadOverride)
        .where(UserPanelSquadOverride.user_id.in_(bindparam("user_ids", expanding=True)))
        .subquery(),
    )
    # Each source contributes independent ORM rows to the same result. ON FALSE
    # keeps every row exactly once, even when several purchases share a subscription.
    return (
        select(limits, devices, topups, overrides)
        .select_from(limits)
        .join_from(limits, devices, false(), full=True)
        .join_from(limits, topups, false(), full=True)
        .join_from(limits, overrides, false(), full=True)
    )


async def prefetch_tariff_read_batch(session: AsyncSession, subs: list[Subscription]) -> None:
    if not isinstance(session, AsyncSession) or not subs:
        return
    clear_tariff_read_batch(session)
    ids = {int(sub.subscription_id) for sub in subs}
    batch = TariffReadBatch(
        session.get_transaction(),
        ids,
        {int(sub.user_id) for sub in subs},
        {str(sub.panel_user_uuid) for sub in subs},
    )
    rows = await session.execute(
        _entitlement_rows(), {"subscription_ids": sorted(ids), "user_ids": sorted(batch.user_ids)}
    )
    for limit, purchase, topup, override in rows:
        if limit is not None:
            batch.flexible.setdefault(limit.subscription_id, []).append(limit)
        elif purchase is not None:
            batch.hwid.setdefault(purchase.subscription_id, []).append(purchase)
        elif topup is not None:
            batch.topups.setdefault(topup.subscription_id, []).append(topup)
        elif override is not None:
            batch.overrides.append(override)
    batch.overrides.sort(key=lambda row: int(row.override_id))
    batch.transaction = session.get_transaction()
    session.info[_KEY] = batch
