"""Persistent overrides for application settings.

Overrides take priority over `.env` values for keys exposed via the admin
manifest. Values are stored as JSON-encoded text to preserve typing across
strings, booleans, integers and floats.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AppSettingOverride

logger = logging.getLogger(__name__)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(raw: Optional[str]) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def get_all_overrides(session: AsyncSession) -> Dict[str, Any]:
    rows = (await session.execute(select(AppSettingOverride))).scalars().all()
    return {row.key: _decode(row.value) for row in rows}


async def get_override_value(session: AsyncSession, key: str) -> Tuple[bool, Any]:
    row = (
        await session.execute(
            select(AppSettingOverride).where(AppSettingOverride.key == key).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return False, None
    return True, _decode(row.value)


async def get_overrides_with_meta(session: AsyncSession) -> List[Dict[str, Any]]:
    rows = (await session.execute(select(AppSettingOverride))).scalars().all()
    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "key": row.key,
                "value": _decode(row.value),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "updated_by": row.updated_by,
            }
        )
    return items


async def upsert_override(
    session: AsyncSession,
    *,
    key: str,
    value: Any,
    updated_by: Optional[int],
) -> None:
    encoded = _encode(value)
    now = datetime.now(timezone.utc)
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


async def delete_override(session: AsyncSession, key: str) -> bool:
    stmt = delete(AppSettingOverride).where(AppSettingOverride.key == key)
    result = await session.execute(stmt)
    return bool(result.rowcount or 0)


async def bulk_apply(
    session: AsyncSession,
    *,
    updates: Dict[str, Tuple[bool, Any]],
    updated_by: Optional[int],
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
