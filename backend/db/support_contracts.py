"""Scalar reconciliation records without detached ORM objects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SupportTicketChange:
    cursor: int
    ticket_id: int
    user_id: int
    revision: int
    last_message_id: int
    status: str
