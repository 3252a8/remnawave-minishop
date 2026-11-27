"""Typed mappings of plugin-owned tables."""

from datetime import datetime
from typing import TypedDict
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .settings import EventName


class Base(DeclarativeBase):
    pass


class StoredReason(TypedDict):
    text: str
    links: list[str]


class Configuration(Base):
    __tablename__ = "ext_minishop_blacklist_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    refresh_hours: Mapped[int]
    refresh_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    users_visible: Mapped[bool]
    user_card_visible: Mapped[bool]
    ticket_visible: Mapped[bool]
    users_table_visible: Mapped[bool]
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    topic_id: Mapped[int | None]
    events: Mapped[list[EventName]] = mapped_column(JSONB)


class Source(Base):
    __tablename__ = "ext_minishop_blacklist_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    url: Mapped[str] = mapped_column(String(2048))
    position: Mapped[int]
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    digest_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(48))
    count: Mapped[int] = mapped_column(default=0)
    invalid_lines: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Entry(Base):
    __tablename__ = "ext_minishop_blacklist_entries"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey(Source.id, ondelete="CASCADE"), primary_key=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reasons: Mapped[list[StoredReason]] = mapped_column(JSONB)
