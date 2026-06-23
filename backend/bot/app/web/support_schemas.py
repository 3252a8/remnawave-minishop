"""Typed response contracts for support ticket endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict

from bot.app.web.http_contracts import HttpResponseModel


class SupportCountsOut(HttpResponseModel):
    """Ticket counters keyed by known statuses, with room for future status keys."""

    model_config = ConfigDict(extra="allow")

    active: int
    closed: int
    total: int


class AdminSupportStatsOut(SupportCountsOut):
    open: int
    awaiting_user: int
    awaiting_admin: int
    total_unread_admin: int


class EmptyObjectOut(HttpResponseModel):
    model_config = ConfigDict(extra="forbid")


class SupportTicketOut(HttpResponseModel):
    ticket_id: int
    user_id: int
    subject: str
    category: str
    priority: str
    status: str
    assigned_admin_id: int | None = None
    last_message_at: datetime | None = None
    last_message_role: str | None = None
    unread_user_count: int
    unread_admin_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None

    @classmethod
    def from_orm_ticket(cls, ticket: Any) -> "SupportTicketOut":
        return cls(
            ticket_id=int(ticket.ticket_id),
            user_id=int(ticket.user_id),
            subject=str(ticket.subject),
            category=str(ticket.category),
            priority=str(ticket.priority),
            status=str(ticket.status),
            assigned_admin_id=(
                int(ticket.assigned_admin_id) if ticket.assigned_admin_id is not None else None
            ),
            last_message_at=ticket.last_message_at,
            last_message_role=ticket.last_message_role,
            unread_user_count=int(ticket.unread_user_count or 0),
            unread_admin_count=int(ticket.unread_admin_count or 0),
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            closed_at=ticket.closed_at,
        )


class AdminSupportUserOut(HttpResponseModel):
    user_id: int | None = None
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    telegram_photo_url: str | None = None
    is_banned: bool | None = None
    registration_date: datetime | None = None

    @classmethod
    def from_orm_user(cls, user: Any) -> "AdminSupportUserOut":
        return cls(
            user_id=int(user.user_id),
            telegram_id=int(user.telegram_id) if user.telegram_id is not None else None,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            telegram_photo_url=user.telegram_photo_url,
            is_banned=bool(user.is_banned),
            registration_date=user.registration_date,
        )


class AdminSupportTicketOut(SupportTicketOut):
    user: AdminSupportUserOut | EmptyObjectOut


class SupportMessageOut(HttpResponseModel):
    message_id: int
    ticket_id: int
    author_role: str
    author_user_id: int | None = None
    body: str
    is_internal_note: bool
    created_at: datetime | None = None
    read_by_user_at: datetime | None = None
    read_by_admin_at: datetime | None = None

    @classmethod
    def from_orm_message(cls, message: Any) -> "SupportMessageOut":
        return cls(
            message_id=int(message.message_id),
            ticket_id=int(message.ticket_id),
            author_role=str(message.author_role),
            author_user_id=(
                int(message.author_user_id) if message.author_user_id is not None else None
            ),
            body=str(message.body),
            is_internal_note=bool(message.is_internal_note),
            created_at=message.created_at,
            read_by_user_at=message.read_by_user_at,
            read_by_admin_at=message.read_by_admin_at,
        )


class AdminSupportMessageOut(SupportMessageOut):
    author_name: str | None = None

    @classmethod
    def from_orm_message(
        cls,
        message: Any,
        *,
        author_name: str | None = None,
    ) -> "AdminSupportMessageOut":
        payload = SupportMessageOut.from_orm_message(message).model_dump()
        payload["author_name"] = author_name
        return cls.model_validate(payload)


class SupportTrafficSnapshotOut(HttpResponseModel):
    used_bytes: int = 0
    limit_bytes: int = 0
    percent: float = 0.0
    left_bytes: int = 0


class AdminSupportUserSnapshotOut(HttpResponseModel):
    user_id: int | None = None
    name: str | None = None
    username: str | None = None
    email: str | None = None
    telegram_id: int | None = None
    language: str | None = None
    registration_date: str | None = None
    email_login: bool | None = None
    subscription_active: bool | None = None
    panel_status: str | None = None
    end_date: str | None = None
    remaining: str | None = None
    tariff: str | None = None
    traffic_regular: SupportTrafficSnapshotOut | None = None
    traffic_premium: SupportTrafficSnapshotOut | None = None
    is_throttled: bool | None = None
    topup_balance_bytes: int | None = None
    premium_topup_balance_bytes: int | None = None
    lifetime_used_traffic_bytes: int | None = None
