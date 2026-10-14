"""Transfer promo history without erasing redemptions or creating new benefits."""

from sqlalchemy import inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PromoCodeActivation, User


async def merge_promo_activation_history(session: AsyncSession, source: User, target: User) -> None:
    """Caller holds both user locks, also used by normal promo consumption.

    Keep the target's canonical redemption and retain a conflicting source
    redemption as historical evidence. Counts, payment links, snapshots and
    explicit manual-override flags remain unchanged. Previously merged history
    keeps its original provenance across further merges.
    """
    source_user_id = int(source.user_id)
    target_user_id = int(target.user_id)
    target_standard_promos = select(PromoCodeActivation.promo_code_id).where(
        PromoCodeActivation.user_id == target_user_id,
        PromoCodeActivation.is_manual_override.is_(False),
        PromoCodeActivation.merged_from_user_id.is_(None),
    )
    await session.execute(
        update(PromoCodeActivation)
        .where(
            PromoCodeActivation.user_id == source_user_id,
            PromoCodeActivation.is_manual_override.is_(False),
            PromoCodeActivation.merged_from_user_id.is_(None),
            PromoCodeActivation.promo_code_id.in_(target_standard_promos),
        )
        .values(merged_from_user_id=source_user_id)
    )
    await session.execute(
        update(PromoCodeActivation)
        .where(PromoCodeActivation.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    source_state = inspect(source, raiseerr=False)
    if source_state is not None and source_state.persistent:
        # A loaded collection would otherwise be traversed by delete-orphan
        # cascade when the source is deleted, despite the ownership update.
        session.expire(source, ["promo_code_activations"])
