"""Transaction-scoped entitlement reads for bounded subscription worker batches."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction
from sqlalchemy.orm import Session

from db.models import (
    FlexibleTrafficLimit,
    HwidDevicePurchase,
    Subscription,
    TrafficTopup,
    UserPanelSquadOverride,
)

_KEY = "tariff_read_batch"
_MODELS = (FlexibleTrafficLimit, HwidDevicePurchase, TrafficTopup, UserPanelSquadOverride)


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
    batch = session.info.get(_KEY)
    if any(isinstance(row, _MODELS) for row in session.new | session.dirty | session.deleted):
        clear_tariff_read_batch(session)
        return None
    if isinstance(batch, TariffReadBatch) and batch.transaction is session.get_transaction():
        return batch
    session.info.pop(_KEY, None)
    return None


def clear_tariff_read_batch(session: AsyncSession) -> None:
    if isinstance(session, AsyncSession):
        session.info.pop(_KEY, None)


@event.listens_for(Session, "before_flush")
def _invalidate_changed_entitlements(session: Session, context: Any, instances: Any) -> None:
    if _KEY in session.info and any(
        isinstance(row, _MODELS) for row in session.new | session.dirty | session.deleted
    ):
        session.info.pop(_KEY, None)


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
    flexible = await session.scalars(
        select(FlexibleTrafficLimit).where(FlexibleTrafficLimit.subscription_id.in_(ids))
    )
    for row in flexible:
        batch.flexible.setdefault(row.subscription_id, []).append(row)
    hwid = await session.scalars(
        select(HwidDevicePurchase).where(HwidDevicePurchase.subscription_id.in_(ids))
    )
    for purchase in hwid:
        batch.hwid.setdefault(purchase.subscription_id, []).append(purchase)
    topups = await session.scalars(
        select(TrafficTopup).where(TrafficTopup.subscription_id.in_(ids))
    )
    for topup in topups:
        batch.topups.setdefault(topup.subscription_id, []).append(topup)
    overrides = await session.scalars(
        select(UserPanelSquadOverride)
        .where(UserPanelSquadOverride.user_id.in_(batch.user_ids))
        .order_by(UserPanelSquadOverride.override_id)
    )
    batch.overrides = list(overrides)
    batch.transaction = session.get_transaction()
    session.info[_KEY] = batch
