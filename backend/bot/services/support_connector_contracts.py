"""Neutral, owner-scoped snapshots for support integrations."""

from dataclasses import dataclass
from datetime import datetime


class SupportConnectorConflict(RuntimeError):
    """The conversation changed or is no longer available for an external reply."""


@dataclass(frozen=True)
class SupportContextMessage:
    message_id: int
    author_role: str
    body: str
    body_format: str
    has_image: bool
    created_at: datetime | None


@dataclass(frozen=True)
class SupportTicketContext:
    ticket_id: int
    user_id: int
    revision: int
    change_cursor: int
    status: str
    category: str
    last_message_role: str | None
    assigned_admin_id: int | None
    last_message_id: int
    messages: tuple[SupportContextMessage, ...]
    facts: dict[str, object]
    observed_at: datetime


@dataclass(frozen=True)
class SupportConnectorReply:
    ticket_id: int
    message_id: int
    revision: int
    duplicate: bool
