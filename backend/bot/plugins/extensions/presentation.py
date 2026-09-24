"""Administrator presentation choices never substitute for operation authorization."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.extension_models import ExtensionPresentation


async def preferences(session: AsyncSession, owner: str) -> dict[str, tuple[bool, int]]:
    rows = (
        await session.scalars(
            select(ExtensionPresentation).where(ExtensionPresentation.owner == owner)
        )
    ).all()
    return {str(row.target): (bool(row.enabled), int(row.position)) for row in rows}
