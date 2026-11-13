"""Administrator-managed exclusions from individual broadcast audiences."""

from sqlalchemy import delete, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from db.broadcast_models import BroadcastAudienceExclusion
from db.models import User

Exclusion = BroadcastAudienceExclusion


async def excluded_ids_by_target(
    session: AsyncSession, target: str | None = None
) -> dict[str, set[int]]:
    stmt = select(Exclusion.target, Exclusion.user_id)
    if target is not None:
        stmt = stmt.where(Exclusion.target == target)
    rows = await session.execute(stmt)
    result: dict[str, set[int]] = {}
    for name, user_id in rows:
        result.setdefault(str(name), set()).add(int(user_id))
    return result


async def user_exclusions(session: AsyncSession, user_id: int) -> set[str]:
    rows = await session.scalars(select(Exclusion.target).where(Exclusion.user_id == user_id))
    return {str(target) for target in rows}


async def set_user_exclusions(
    session: AsyncSession, user_id: int, old: set[str], new: set[str]
) -> None:
    removed = old - new
    if removed:
        await session.execute(
            delete(Exclusion).where(Exclusion.user_id == user_id, Exclusion.target.in_(removed))
        )
    session.add_all(Exclusion(user_id=user_id, target=target) for target in new - old)


async def merge_user_exclusions(session: AsyncSession, source_id: int, target_id: int) -> None:
    await session.execute(
        insert(Exclusion)
        .from_select(
            ["user_id", "target"],
            select(literal(target_id), Exclusion.target).where(Exclusion.user_id == source_id),
        )
        .on_conflict_do_nothing()
    )


def users_without_required_channel(
    channel_id: int, *, exclude_target: str | None = None
) -> Select[tuple[int]]:
    stmt = select(User.user_id).where(
        User.is_banned.is_(False),
        User.telegram_id.is_not(None),
        User.channel_subscription_verified_for == channel_id,
        User.channel_subscription_checked_at.is_not(None),
        User.channel_subscription_verified.is_(False),
    )
    if exclude_target is not None:
        stmt = stmt.where(
            ~select(Exclusion.user_id)
            .where(Exclusion.user_id == User.user_id, Exclusion.target == exclude_target)
            .exists()
        )
    return stmt
