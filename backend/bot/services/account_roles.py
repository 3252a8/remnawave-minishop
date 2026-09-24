"""Account-owned authorization, independent of the login transport."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.auth_models import AccountRole, AccountRoleEvent
from db.models import User

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ADMIN_ROLES = (ROLE_OWNER, ROLE_ADMIN)
_ROLE_LOCK_ID = 68533712981372


async def has_role(session: AsyncSession, user_id: int, role: str) -> bool:
    result = await session.execute(
        select(AccountRole.user_id).where(
            AccountRole.user_id == user_id,
            AccountRole.role == role,
            AccountRole.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None


async def is_admin(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        select(AccountRole.user_id)
        .where(
            AccountRole.user_id == user_id,
            AccountRole.role.in_(ADMIN_ROLES),
            AccountRole.revoked_at.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def active_admin_user_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(
        select(AccountRole.user_id)
        .where(AccountRole.role.in_(ADMIN_ROLES), AccountRole.revoked_at.is_(None))
        .distinct()
    )
    return list(result.scalars().all())


async def bootstrap_owner(session: AsyncSession, email: str) -> int:
    """Grant the first owner only to an existing verified email account.

    This command runs from a trusted local shell after email verification. It
    never grants the role to the first account merely because it registered.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": _ROLE_LOCK_ID})
    owner_count = await session.scalar(
        select(func.count())
        .select_from(AccountRole)
        .where(AccountRole.role == ROLE_OWNER, AccountRole.revoked_at.is_(None))
    )
    if owner_count:
        raise ValueError("Owner already exists")
    normalized = email.strip().lower()
    user = await session.scalar(
        select(User).where(User.email == normalized, User.email_verified_at.is_not(None))
    )
    if user is None:
        raise ValueError("A verified email account is required")
    await grant_role(session, int(user.user_id), ROLE_OWNER, source="bootstrap")
    return int(user.user_id)


async def migrate_legacy_admin_ids(session: AsyncSession, admin_ids: list[int]) -> tuple[int, int]:
    """Import explicit Telegram identities once, never by matching numeric PKs."""
    if not admin_ids:
        return (0, 0)
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": _ROLE_LOCK_ID})
    done = await session.scalar(
        text("SELECT 1 FROM account_role_legacy_migrations WHERE source = 'admin_ids'")
    )
    if done:
        return (0, 0)
    linked = (
        (await session.execute(select(User).where(User.telegram_id.in_(admin_ids)))).scalars().all()
    )
    for user in linked:
        await grant_role(session, int(user.user_id), ROLE_ADMIN, source="legacy_admin_ids")
    unresolved = len(set(admin_ids)) - len(linked)
    await session.execute(
        text("""
            INSERT INTO account_role_legacy_migrations (source, unresolved_count)
            VALUES ('admin_ids', :unresolved)
        """),
        {"unresolved": unresolved},
    )
    return (len(linked), unresolved)


async def grant_role(
    session: AsyncSession,
    user_id: int,
    role: str,
    *,
    actor_user_id: int | None = None,
    source: str = "admin_api",
) -> None:
    if role not in ADMIN_ROLES:
        raise ValueError("Unsupported role")
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError("Account does not exist")
    assignment = await session.get(AccountRole, (user_id, role), with_for_update=True)
    if assignment is not None and assignment.revoked_at is None:
        return
    now = datetime.now(UTC)
    if assignment is None:
        session.add(
            AccountRole(user_id=user_id, role=role, granted_by=actor_user_id, granted_at=now)
        )
    else:
        assignment.granted_at = now
        assignment.granted_by = actor_user_id
        assignment.revoked_at = None
        assignment.revoked_by = None
    session.add(
        AccountRoleEvent(
            user_id=user_id, role=role, action="grant", actor_user_id=actor_user_id, source=source
        )
    )
    await session.flush()


async def revoke_role(
    session: AsyncSession,
    user_id: int,
    role: str,
    *,
    actor_user_id: int,
) -> None:
    if role not in ADMIN_ROLES:
        raise ValueError("Unsupported role")
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": _ROLE_LOCK_ID})
    assignment = await session.get(AccountRole, (user_id, role), with_for_update=True)
    if assignment is None or assignment.revoked_at is not None:
        return
    if role == ROLE_OWNER:
        owner_count = await session.scalar(
            select(func.count())
            .select_from(AccountRole)
            .where(AccountRole.role == ROLE_OWNER, AccountRole.revoked_at.is_(None))
        )
        if not owner_count or owner_count <= 1:
            raise ValueError("Cannot revoke the last owner")
    assignment.revoked_at = datetime.now(UTC)
    assignment.revoked_by = actor_user_id
    session.add(
        AccountRoleEvent(
            user_id=user_id,
            role=role,
            action="revoke",
            actor_user_id=actor_user_id,
            source="admin_api",
        )
    )
    await session.flush()
