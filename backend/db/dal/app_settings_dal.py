"""Persistent overrides for application settings.

Overrides take priority over `.env` values for keys exposed via the admin
manifest. Values are stored as JSON-encoded text to preserve typing across
strings, booleans, integers and floats.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AppSettingOverride

from ._sqlalchemy import rowcount

logger = logging.getLogger(__name__)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def get_all_overrides(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(AppSettingOverride))).scalars().all()
    return {row.key: _decode(row.value) for row in rows}


async def get_override_value(session: AsyncSession, key: str) -> tuple[bool, Any]:
    row = (
        await session.execute(
            select(AppSettingOverride).where(AppSettingOverride.key == key).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return False, None
    return True, _decode(row.value)


async def get_overrides_with_meta(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(AppSettingOverride))).scalars().all()
    return [
        {
            "key": row.key,
            "value": _decode(row.value),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by,
        }
        for row in rows
    ]


async def upsert_override(
    session: AsyncSession,
    *,
    key: str,
    value: Any,
    updated_by: int | None,
) -> None:
    encoded = _encode(value)
    now = datetime.now(UTC)
    stmt = (
        pg_insert(AppSettingOverride)
        .values(key=key, value=encoded, updated_at=now, updated_by=updated_by)
        .on_conflict_do_update(
            index_elements=[AppSettingOverride.key],
            set_={
                "value": encoded,
                "updated_at": now,
                "updated_by": updated_by,
            },
        )
    )
    await session.execute(stmt)


async def insert_override_if_missing(
    session: AsyncSession,
    *,
    key: str,
    value: Any,
    updated_by: int | None,
) -> bool:
    """Insert an override without replacing a value created by another process."""

    stmt = (
        pg_insert(AppSettingOverride)
        .values(
            key=key,
            value=_encode(value),
            updated_at=datetime.now(UTC),
            updated_by=updated_by,
        )
        .on_conflict_do_nothing(index_elements=[AppSettingOverride.key])
    )
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def delete_override(session: AsyncSession, key: str) -> bool:
    stmt = delete(AppSettingOverride).where(AppSettingOverride.key == key)
    result = await session.execute(stmt)
    return rowcount(result) > 0


async def bulk_apply(
    session: AsyncSession,
    *,
    updates: dict[str, tuple[bool, Any]],
    updated_by: int | None,
) -> None:
    """Apply a batch of changes. Each entry maps key -> (set_flag, value).

    When set_flag is False the override is deleted (revert to env). Otherwise
    the value is upserted.
    """
    for key, (set_flag, value) in updates.items():
        if set_flag:
            await upsert_override(session, key=key, value=value, updated_by=updated_by)
        else:
            await delete_override(session, key)
