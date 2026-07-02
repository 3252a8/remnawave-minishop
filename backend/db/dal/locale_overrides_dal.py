"""Persistent overrides for localization strings."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LocaleOverride

from ._sqlalchemy import rowcount


async def get_all_overrides(session: AsyncSession) -> dict[str, dict[str, str]]:
    rows = (await session.execute(select(LocaleOverride))).scalars().all()
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        result.setdefault(row.lang, {})[row.key] = row.value
    return result


async def get_overrides_with_meta(session: AsyncSession) -> list[dict[str, object]]:
    rows = (await session.execute(select(LocaleOverride))).scalars().all()
    items: list[dict[str, object]] = []
    for row in rows:
        items.append(
            {
                "lang": row.lang,
                "key": row.key,
                "value": row.value,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "updated_by": row.updated_by,
            }
        )
    return items


async def upsert_override(
    session: AsyncSession,
    *,
    lang: str,
    key: str,
    value: str,
    updated_by: int | None,
) -> None:
    now = datetime.now(UTC)
    stmt = (
        pg_insert(LocaleOverride)
        .values(lang=lang, key=key, value=value, updated_at=now, updated_by=updated_by)
        .on_conflict_do_update(
            index_elements=[LocaleOverride.lang, LocaleOverride.key],
            set_={
                "value": value,
                "updated_at": now,
                "updated_by": updated_by,
            },
        )
    )
    await session.execute(stmt)


async def delete_override(session: AsyncSession, *, lang: str, key: str) -> bool:
    stmt = delete(LocaleOverride).where(
        LocaleOverride.lang == lang,
        LocaleOverride.key == key,
    )
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def bulk_apply(
    session: AsyncSession,
    *,
    updates: dict[tuple[str, str], tuple[bool, str]],
    updated_by: int | None,
) -> None:
    for (lang, key), (set_flag, value) in updates.items():
        if set_flag:
            await upsert_override(
                session,
                lang=lang,
                key=key,
                value=value,
                updated_by=updated_by,
            )
        else:
            await delete_override(session, lang=lang, key=key)
