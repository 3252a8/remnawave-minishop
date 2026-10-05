"""Preserve subscription rows when an existing panel account changes its reference."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Subscription


async def relink_panel_subscriptions(
    session: AsyncSession,
    *,
    user_id: int,
    old_panel_user_uuid: str,
    new_panel_user_uuid: str,
    panel_subscription_uuid: str | None,
) -> int:
    """Relink a verified existing account without replacing its subscription history."""
    if old_panel_user_uuid == new_panel_user_uuid:
        return 0
    identity_filter = (
        Subscription.user_id == user_id,
        Subscription.panel_user_uuid == old_panel_user_uuid,
    )
    result = await session.execute(
        select(Subscription.subscription_id)
        .where(*identity_filter)
        .order_by(Subscription.end_date.desc(), Subscription.subscription_id.desc())
        .with_for_update()
    )
    subscription_ids = list(result.scalars().all())
    if not subscription_ids:
        return 0

    current_subscription = None
    if panel_subscription_uuid:
        result = await session.execute(
            select(Subscription.user_id, Subscription.panel_user_uuid)
            .where(Subscription.panel_subscription_uuid == panel_subscription_uuid)
            .limit(1)
        )
        current_subscription = result.first()
        if current_subscription is not None and (
            current_subscription.user_id != user_id
            or current_subscription.panel_user_uuid
            not in {old_panel_user_uuid, new_panel_user_uuid}
        ):
            raise ValueError("Panel subscription reference belongs to another account")

    await session.execute(
        update(Subscription)
        .where(*identity_filter)
        .values(panel_user_uuid=new_panel_user_uuid)
        .execution_options(synchronize_session="fetch")
    )
    if panel_subscription_uuid and current_subscription is None:
        # Only the current row adopts the new link. Older rows keep their
        # subscription links, dates, consent, payments and notification markers.
        await session.execute(
            update(Subscription)
            .where(Subscription.subscription_id == subscription_ids[0])
            .values(panel_subscription_uuid=panel_subscription_uuid)
            .execution_options(synchronize_session="fetch")
        )
    await session.flush()
    return len(subscription_ids)
