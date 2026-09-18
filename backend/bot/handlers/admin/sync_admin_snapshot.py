"""Compact PostgreSQL versions fence a full panel snapshot against new purchases."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import String, cast, literal_column, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Subscription


@dataclass
class SubscriptionSnapshot:
    versions: dict[int, str] = field(default_factory=dict)
    active_by_panel: dict[str, list[int]] = field(default_factory=dict)

    def siblings_filter(self, panel_uuid: str) -> Any:
        candidates = self.active_by_panel.get(panel_uuid, [])
        return tuple_(Subscription.subscription_id, cast(literal_column("xmin"), String)).in_(
            [(sub_id, self.versions[sub_id]) for sub_id in candidates]
        )


async def capture_subscription_snapshot(session: AsyncSession) -> SubscriptionSnapshot | None:
    if not isinstance(session, AsyncSession):
        return None
    rows = await session.execute(
        select(
            Subscription.subscription_id,
            Subscription.panel_user_uuid,
            Subscription.is_active,
            cast(literal_column("xmin"), String),
        )
    )
    snapshot = SubscriptionSnapshot()
    for sub_id, panel_id, active, version in rows:
        snapshot.versions[sub_id] = version
        if active:
            snapshot.active_by_panel.setdefault(panel_id, []).append(sub_id)
    # No open DB transaction while streaming the remote panel.
    await session.commit()
    return snapshot
