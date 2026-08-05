from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserPanelSquadOverride

from ._sqlalchemy import rowcount

INTERNAL_KIND = "internal"
EXTERNAL_KIND = "external"
EXTERNAL_OVERRIDE_KEY = "external"
OVERRIDE_MODE_SET = "set"
OVERRIDE_MODE_CLEARED = "cleared"
OVERRIDE_SOURCE_ADMIN = "admin"
OVERRIDE_SOURCE_PANEL = "panel"


def _now() -> datetime:
    return datetime.now(UTC)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


async def _get_override(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
    kind: str,
    override_key: str,
) -> UserPanelSquadOverride | None:
    stmt = select(UserPanelSquadOverride).where(
        UserPanelSquadOverride.user_id == user_id,
        UserPanelSquadOverride.panel_user_uuid == panel_user_uuid,
        UserPanelSquadOverride.kind == kind,
        UserPanelSquadOverride.override_key == override_key,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_overrides(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    panel_user_uuid: str | None = None,
    kind: str | None = None,
) -> list[UserPanelSquadOverride]:
    conditions = [UserPanelSquadOverride.is_active == True]
    if user_id is not None:
        conditions.append(UserPanelSquadOverride.user_id == user_id)
    if panel_user_uuid:
        conditions.append(UserPanelSquadOverride.panel_user_uuid == panel_user_uuid)
    if kind:
        conditions.append(UserPanelSquadOverride.kind == kind)
    if len(conditions) == 1:
        raise ValueError("user_id, panel_user_uuid or kind is required")
    stmt = (
        select(UserPanelSquadOverride)
        .where(and_(*conditions))
        .order_by(UserPanelSquadOverride.override_id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_active_internal_squad_uuids(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
) -> list[str]:
    overrides = await get_active_overrides(
        session,
        user_id=user_id,
        panel_user_uuid=panel_user_uuid,
        kind=INTERNAL_KIND,
    )
    uuids: list[str] = []
    seen: set[str] = set()
    for override in overrides:
        squad_uuid = _clean_text(getattr(override, "squad_uuid", None))
        if squad_uuid and squad_uuid not in seen:
            uuids.append(squad_uuid)
            seen.add(squad_uuid)
    return uuids


async def get_active_external_override(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
) -> UserPanelSquadOverride | None:
    stmt = select(UserPanelSquadOverride).where(
        UserPanelSquadOverride.user_id == user_id,
        UserPanelSquadOverride.panel_user_uuid == panel_user_uuid,
        UserPanelSquadOverride.kind == EXTERNAL_KIND,
        UserPanelSquadOverride.override_key == EXTERNAL_OVERRIDE_KEY,
        UserPanelSquadOverride.is_active == True,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_internal_override(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
    squad_uuid: str,
    source: str,
    created_by_admin_id: int | None = None,
    note: str | None = None,
    last_seen_at: datetime | None = None,
) -> UserPanelSquadOverride:
    cleaned_squad_uuid = _clean_text(squad_uuid)
    if not cleaned_squad_uuid:
        raise ValueError("squad_uuid is required")
    record = await _get_override(
        session,
        user_id=user_id,
        panel_user_uuid=panel_user_uuid,
        kind=INTERNAL_KIND,
        override_key=cleaned_squad_uuid,
    )
    now = _now()
    if record is None:
        record = UserPanelSquadOverride(
            user_id=user_id,
            panel_user_uuid=panel_user_uuid,
            kind=INTERNAL_KIND,
            override_key=cleaned_squad_uuid,
            squad_uuid=cleaned_squad_uuid,
            mode=OVERRIDE_MODE_SET,
            source=source,
            is_active=True,
            created_by_admin_id=created_by_admin_id,
            last_seen_at=last_seen_at,
            note=note,
        )
        session.add(record)
    else:
        record.squad_uuid = cleaned_squad_uuid
        record.mode = OVERRIDE_MODE_SET
        record.source = source
        record.is_active = True
        record.deactivated_at = None
        record.updated_at = now
        if created_by_admin_id is not None:
            record.created_by_admin_id = created_by_admin_id
        if last_seen_at is not None:
            record.last_seen_at = last_seen_at
        if note is not None:
            record.note = note
    await session.flush()
    await session.refresh(record)
    return record


async def deactivate_internal_override(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
    squad_uuid: str,
) -> int:
    cleaned_squad_uuid = _clean_text(squad_uuid)
    if not cleaned_squad_uuid:
        return 0
    result = await session.execute(
        update(UserPanelSquadOverride)
        .where(
            UserPanelSquadOverride.user_id == user_id,
            UserPanelSquadOverride.panel_user_uuid == panel_user_uuid,
            UserPanelSquadOverride.kind == INTERNAL_KIND,
            UserPanelSquadOverride.override_key == cleaned_squad_uuid,
            UserPanelSquadOverride.is_active == True,
        )
        .values(is_active=False, updated_at=_now(), deactivated_at=_now())
    )
    await session.flush()
    return rowcount(result)


async def set_external_override(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
    mode: str,
    squad_uuid: str | None = None,
    source: str,
    created_by_admin_id: int | None = None,
    last_seen_at: datetime | None = None,
) -> UserPanelSquadOverride | None:
    cleaned_mode = _clean_text(mode).lower()
    if cleaned_mode == "inherit":
        await deactivate_external_override(
            session,
            user_id=user_id,
            panel_user_uuid=panel_user_uuid,
        )
        return None
    if cleaned_mode not in {OVERRIDE_MODE_SET, OVERRIDE_MODE_CLEARED}:
        raise ValueError("external mode must be inherit, set or cleared")
    cleaned_squad_uuid = _clean_text(squad_uuid) or None
    if cleaned_mode == OVERRIDE_MODE_SET and not cleaned_squad_uuid:
        raise ValueError("external squad_uuid is required for set mode")

    record = await _get_override(
        session,
        user_id=user_id,
        panel_user_uuid=panel_user_uuid,
        kind=EXTERNAL_KIND,
        override_key=EXTERNAL_OVERRIDE_KEY,
    )
    now = _now()
    if record is None:
        record = UserPanelSquadOverride(
            user_id=user_id,
            panel_user_uuid=panel_user_uuid,
            kind=EXTERNAL_KIND,
            override_key=EXTERNAL_OVERRIDE_KEY,
            squad_uuid=cleaned_squad_uuid,
            mode=cleaned_mode,
            source=source,
            is_active=True,
            created_by_admin_id=created_by_admin_id,
            last_seen_at=last_seen_at,
        )
        session.add(record)
    else:
        record.squad_uuid = cleaned_squad_uuid
        record.mode = cleaned_mode
        record.source = source
        record.is_active = True
        record.deactivated_at = None
        record.updated_at = now
        if created_by_admin_id is not None:
            record.created_by_admin_id = created_by_admin_id
        if last_seen_at is not None:
            record.last_seen_at = last_seen_at
    await session.flush()
    await session.refresh(record)
    return record


async def deactivate_external_override(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
) -> int:
    result = await session.execute(
        update(UserPanelSquadOverride)
        .where(
            UserPanelSquadOverride.user_id == user_id,
            UserPanelSquadOverride.panel_user_uuid == panel_user_uuid,
            UserPanelSquadOverride.kind == EXTERNAL_KIND,
            UserPanelSquadOverride.override_key == EXTERNAL_OVERRIDE_KEY,
            UserPanelSquadOverride.is_active == True,
        )
        .values(is_active=False, updated_at=_now(), deactivated_at=_now())
    )
    await session.flush()
    return rowcount(result)


async def merge_panel_user_uuid(
    session: AsyncSession,
    *,
    user_id: int,
    old_panel_user_uuid: str,
    new_panel_user_uuid: str,
) -> int:
    old_uuid = _clean_text(old_panel_user_uuid)
    new_uuid = _clean_text(new_panel_user_uuid)
    if not old_uuid or not new_uuid or old_uuid == new_uuid:
        return 0

    stmt = select(UserPanelSquadOverride).where(
        UserPanelSquadOverride.user_id == user_id,
        UserPanelSquadOverride.panel_user_uuid == old_uuid,
    )
    rows = list((await session.execute(stmt)).scalars().all())
    moved = 0
    now = _now()
    for row in rows:
        existing = await _get_override(
            session,
            user_id=user_id,
            panel_user_uuid=new_uuid,
            kind=str(getattr(row, "kind", "")),
            override_key=str(getattr(row, "override_key", "")),
        )
        if existing is None:
            row.panel_user_uuid = new_uuid
            row.updated_at = now
        else:
            existing.squad_uuid = getattr(row, "squad_uuid", None)
            existing.mode = getattr(row, "mode", OVERRIDE_MODE_SET)
            existing.source = getattr(row, "source", OVERRIDE_SOURCE_ADMIN)
            existing_active = bool(getattr(existing, "is_active", False))
            row_active = bool(getattr(row, "is_active", False))
            existing.is_active = existing_active or row_active
            existing.updated_at = now
            if getattr(row, "last_seen_at", None) is not None:
                existing.last_seen_at = getattr(row, "last_seen_at", None)
            row.is_active = False
            row.updated_at = now
            row.deactivated_at = now
        moved += 1
    if moved:
        await session.flush()
    return moved
