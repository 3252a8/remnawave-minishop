from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.provider_mandate_models import ProviderMandate

LIVE_STATUSES = ("pending", "active", "paused", "past_due")


async def get_by_anchor(
    session: AsyncSession, *, provider: str, anchor_payment_id: int
) -> ProviderMandate | None:
    statement = select(ProviderMandate).where(
        ProviderMandate.provider == provider, ProviderMandate.anchor_payment_id == anchor_payment_id
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def get_mandate(
    session: AsyncSession, *, provider: str, remote_id: str, for_update: bool = False
) -> ProviderMandate | None:
    statement = select(ProviderMandate).where(
        ProviderMandate.provider == provider, ProviderMandate.remote_id == remote_id
    )
    if for_update:
        statement = statement.execution_options(populate_existing=True).with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def list_mandates(
    session: AsyncSession,
    *,
    providers: Collection[str],
    user_id: int | None = None,
    limit: int = 100,
    after_id: int = 0,
) -> list[ProviderMandate]:
    statement = (
        select(ProviderMandate)
        .where(ProviderMandate.provider.in_(providers), ProviderMandate.status.in_(LIVE_STATUSES))
        .order_by(ProviderMandate.mandate_id)
        .limit(limit)
    )
    statement = statement.where(ProviderMandate.mandate_id > after_id)
    if user_id is not None:
        statement = statement.where(ProviderMandate.user_id == user_id)
    return list((await session.execute(statement)).scalars())
