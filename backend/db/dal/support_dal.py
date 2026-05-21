from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, desc, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..models import SupportTicket, SupportTicketMessage, User

ACTIVE_STATUSES = {"open", "awaiting_user", "awaiting_admin"}
CLOSED_STATUSES = {"resolved", "closed"}
_UNSET = object()


def _status_condition(status: Optional[str]):
    normalized = (status or "").strip().lower()
    if not normalized or normalized in {"all", "any"}:
        return None
    if normalized == "active":
        return SupportTicket.status.in_(ACTIVE_STATUSES)
    if normalized == "closed":
        return SupportTicket.status.in_(CLOSED_STATUSES)
    return SupportTicket.status == normalized


async def create_ticket(
    session: AsyncSession,
    user_id: int,
    subject: str,
    category: str,
    priority: str,
    first_message_body: str,
) -> SupportTicket:
    now = datetime.now(timezone.utc)
    ticket = SupportTicket(
        user_id=user_id,
        subject=subject,
        category=category,
        priority=priority,
        status="awaiting_admin",
        last_message_at=now,
        last_message_role="user",
        unread_admin_count=1,
        unread_user_count=0,
        admin_last_notified_at=now,
        admin_last_emailed_at=now,
    )
    session.add(ticket)
    await session.flush()
    message = SupportTicketMessage(
        ticket_id=ticket.ticket_id,
        author_role="user",
        author_user_id=user_id,
        body=first_message_body,
        is_internal_note=False,
        created_at=now,
    )
    session.add(message)
    await session.flush()
    await session.refresh(ticket)
    return ticket


async def add_message(
    session: AsyncSession,
    ticket_id: int,
    author_role: str,
    author_user_id: Optional[int],
    body: str,
    is_internal_note: bool = False,
) -> Optional[SupportTicketMessage]:
    stmt = select(SupportTicket).where(SupportTicket.ticket_id == ticket_id).with_for_update()
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        return None

    now = datetime.now(timezone.utc)
    message = SupportTicketMessage(
        ticket_id=ticket_id,
        author_role=author_role,
        author_user_id=author_user_id,
        body=body,
        is_internal_note=bool(is_internal_note),
        created_at=now,
    )
    session.add(message)

    ticket.last_message_at = now
    ticket.last_message_role = author_role
    ticket.updated_at = now
    if author_role == "user":
        ticket.unread_admin_count = int(ticket.unread_admin_count or 0) + 1
        if ticket.status not in CLOSED_STATUSES:
            ticket.status = "awaiting_admin"
    elif author_role == "admin" and not is_internal_note:
        ticket.unread_user_count = int(ticket.unread_user_count or 0) + 1
        if ticket.status not in CLOSED_STATUSES:
            ticket.status = "awaiting_user"

    await session.flush()
    await session.refresh(message)
    return message


async def record_admin_notification(
    session: AsyncSession,
    ticket_id: int,
    *,
    notified_at: Optional[datetime] = None,
    emailed_at: Optional[datetime] = None,
) -> None:
    values = {}
    if notified_at is not None:
        values["admin_last_notified_at"] = notified_at
    if emailed_at is not None:
        values["admin_last_emailed_at"] = emailed_at
    if not values:
        return
    await session.execute(
        update(SupportTicket).where(SupportTicket.ticket_id == ticket_id).values(**values)
    )
    await session.flush()


async def get_ticket(
    session: AsyncSession,
    ticket_id: int,
    *,
    include_internal: bool = False,
) -> tuple[Optional[SupportTicket], list[SupportTicketMessage]]:
    stmt = (
        select(SupportTicket)
        .where(SupportTicket.ticket_id == ticket_id)
        .options(selectinload(SupportTicket.user))
    )
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        return None, []

    msg_stmt = select(SupportTicketMessage).where(SupportTicketMessage.ticket_id == ticket_id)
    if not include_internal:
        msg_stmt = msg_stmt.where(SupportTicketMessage.is_internal_note.is_(False))
    msg_stmt = msg_stmt.order_by(
        SupportTicketMessage.created_at.asc(),
        SupportTicketMessage.message_id.asc(),
    )
    msg_result = await session.execute(msg_stmt)
    return ticket, list(msg_result.scalars().all())


async def list_user_tickets(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int,
    offset: int,
    status_filter: Optional[str] = None,
) -> list[SupportTicket]:
    stmt = select(SupportTicket).where(SupportTicket.user_id == user_id)
    status_cond = _status_condition(status_filter)
    if status_cond is not None:
        stmt = stmt.where(status_cond)
    stmt = (
        stmt.order_by(desc(SupportTicket.last_message_at), desc(SupportTicket.ticket_id))
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_admin_tickets(
    session: AsyncSession,
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    assigned_admin_id: Optional[int] = None,
    search: Optional[str] = None,
    sort: str = "updated_desc",
    limit: int,
    offset: int,
) -> list[SupportTicket]:
    stmt = select(SupportTicket).join(User, User.user_id == SupportTicket.user_id)
    status_cond = _status_condition(status)
    if status_cond is not None:
        stmt = stmt.where(status_cond)
    if priority:
        stmt = stmt.where(SupportTicket.priority == priority)
    if category:
        stmt = stmt.where(SupportTicket.category == category)
    if assigned_admin_id is not None:
        stmt = stmt.where(SupportTicket.assigned_admin_id == assigned_admin_id)
    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(SupportTicket.subject).like(pattern),
                func.lower(User.username).like(pattern),
                func.lower(User.first_name).like(pattern),
                func.lower(User.email).like(pattern),
            )
        )
    priority_rank = case(
        (SupportTicket.priority == "urgent", 4),
        (SupportTicket.priority == "high", 3),
        (SupportTicket.priority == "normal", 2),
        (SupportTicket.priority == "low", 1),
        else_=0,
    )
    sort_key = (sort or "updated_desc").strip().lower()
    sort_map = {
        "updated_desc": (SupportTicket.last_message_at.desc().nullslast(),),
        "updated_asc": (SupportTicket.last_message_at.asc().nullslast(),),
        "created_desc": (SupportTicket.created_at.desc().nullslast(),),
        "created_asc": (SupportTicket.created_at.asc().nullslast(),),
        "importance_desc": (
            priority_rank.desc(),
            SupportTicket.last_message_at.desc().nullslast(),
        ),
        "importance_asc": (
            priority_rank.asc(),
            SupportTicket.last_message_at.desc().nullslast(),
        ),
    }
    order_by = sort_map.get(sort_key, sort_map["updated_desc"])
    stmt = stmt.options(selectinload(SupportTicket.user)).order_by(
        *order_by,
        desc(SupportTicket.ticket_id),
    )
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def user_ticket_counts(session: AsyncSession, user_id: int) -> dict:
    stmt = (
        select(SupportTicket.status, func.count())
        .where(SupportTicket.user_id == user_id)
        .group_by(SupportTicket.status)
    )
    result = await session.execute(stmt)
    by_status = {str(status): int(count or 0) for status, count in result.all()}
    active = sum(by_status.get(status, 0) for status in ACTIVE_STATUSES)
    closed = sum(by_status.get(status, 0) for status in CLOSED_STATUSES)
    return {
        **by_status,
        "active": active,
        "closed": closed,
        "total": active + closed,
    }


async def mark_read(session: AsyncSession, ticket_id: int, role: str) -> None:
    now = datetime.now(timezone.utc)
    if role == "user":
        await session.execute(
            update(SupportTicket)
            .where(SupportTicket.ticket_id == ticket_id)
            .values(unread_user_count=0, updated_at=now)
        )
        await session.execute(
            update(SupportTicketMessage)
            .where(
                and_(
                    SupportTicketMessage.ticket_id == ticket_id,
                    SupportTicketMessage.author_role == "admin",
                    SupportTicketMessage.is_internal_note.is_(False),
                    SupportTicketMessage.read_by_user_at.is_(None),
                )
            )
            .values(read_by_user_at=now)
        )
    elif role == "admin":
        await session.execute(
            update(SupportTicket)
            .where(SupportTicket.ticket_id == ticket_id)
            .values(unread_admin_count=0, updated_at=now)
        )
        await session.execute(
            update(SupportTicketMessage)
            .where(
                and_(
                    SupportTicketMessage.ticket_id == ticket_id,
                    SupportTicketMessage.author_role == "user",
                    SupportTicketMessage.read_by_admin_at.is_(None),
                )
            )
            .values(read_by_admin_at=now)
        )
    await session.flush()


async def update_ticket(
    session: AsyncSession,
    ticket_id: int,
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    assigned_admin_id: object = _UNSET,
    closed_by_admin_id: Optional[int] = None,
) -> Optional[SupportTicket]:
    ticket = await session.get(SupportTicket, ticket_id)
    if not ticket:
        return None
    now = datetime.now(timezone.utc)
    if status is not None:
        ticket.status = status
        if status == "closed":
            ticket.closed_at = now
            ticket.closed_by_admin_id = closed_by_admin_id
        elif status != "closed":
            ticket.closed_at = None
            ticket.closed_by_admin_id = None
    if priority is not None:
        ticket.priority = priority
    if category is not None:
        ticket.category = category
    if assigned_admin_id is not _UNSET:
        ticket.assigned_admin_id = assigned_admin_id
    ticket.updated_at = now
    await session.flush()
    await session.refresh(ticket)
    return ticket


async def count_user_unread(session: AsyncSession, user_id: int) -> int:
    stmt = select(func.coalesce(func.sum(SupportTicket.unread_user_count), 0)).where(
        SupportTicket.user_id == user_id
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def admin_stats(session: AsyncSession) -> dict:
    status_result = await session.execute(
        select(SupportTicket.status, func.count()).group_by(SupportTicket.status)
    )
    by_status = {str(status): int(count or 0) for status, count in status_result.all()}
    unread_result = await session.execute(
        select(func.coalesce(func.sum(SupportTicket.unread_admin_count), 0))
    )
    active = sum(by_status.get(status, 0) for status in ACTIVE_STATUSES)
    closed = sum(by_status.get(status, 0) for status in CLOSED_STATUSES)
    return {
        **by_status,
        "active": active,
        "closed": closed,
        "total": active + closed,
        "open": by_status.get("open", 0),
        "awaiting_admin": by_status.get("awaiting_admin", 0),
        "awaiting_user": by_status.get("awaiting_user", 0),
        "total_unread_admin": int(unread_result.scalar_one() or 0),
    }


async def count_recent_tickets_for_user(
    session: AsyncSession,
    user_id: int,
    window_seconds: int,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, int(window_seconds)))
    stmt = (
        select(func.count())
        .select_from(SupportTicket)
        .where(SupportTicket.user_id == user_id, SupportTicket.created_at >= cutoff)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)
