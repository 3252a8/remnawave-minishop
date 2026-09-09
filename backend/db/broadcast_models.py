"""Persistent admin broadcast history and per-channel delivery progress."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


class AdminBroadcast(Base):
    __tablename__ = "admin_broadcasts"
    __table_args__ = (
        Index("ix_admin_broadcasts_status_scheduled", "status", "scheduled_at"),
        Index("ix_admin_broadcasts_visible_created", "deleted_at", "created_at"),
    )

    broadcast_id = Column(Integer, primary_key=True, autoincrement=True)
    created_by_admin_id = Column(BigInteger, nullable=True, index=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    is_visible = Column(Boolean, nullable=False, default=True, index=True)
    target = Column(String(128), nullable=False, default="all")
    channels = Column(JSON, nullable=False, default=list)
    exclude_blocked_telegram = Column(Boolean, nullable=False, default=False)
    texts = Column(JSON, nullable=False, default=dict)
    email_subjects = Column(JSON, nullable=False, default=dict)
    buttons = Column(JSON, nullable=False, default=list)
    image_id = Column(
        String(32),
        ForeignKey("message_images.image_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    recipient_count = Column(Integer, nullable=False, default=0)
    total_deliveries = Column(Integer, nullable=False, default=0)
    successful_deliveries = Column(Integer, nullable=False, default=0)
    failed_deliveries = Column(Integer, nullable=False, default=0)
    telegram_sent = Column(Integer, nullable=False, default=0)
    telegram_failed = Column(Integer, nullable=False, default=0)
    email_sent = Column(Integer, nullable=False, default=0)
    email_failed = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    deliveries = relationship(
        "AdminBroadcastDelivery",
        back_populates="broadcast",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AdminBroadcastDelivery(Base):
    __tablename__ = "admin_broadcast_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "broadcast_id",
            "user_id",
            "channel",
            name="uq_admin_broadcast_delivery_user_channel",
        ),
        Index("ix_admin_broadcast_deliveries_broadcast_status", "broadcast_id", "status"),
    )

    delivery_id = Column(Integer, primary_key=True, autoincrement=True)
    broadcast_id = Column(
        Integer,
        ForeignKey("admin_broadcasts.broadcast_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(BigInteger, nullable=False, index=True)
    channel = Column(String(16), nullable=False)
    destination = Column(Text, nullable=False)
    language_code = Column(String(16), nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    queued_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    broadcast = relationship("AdminBroadcast", back_populates="deliveries")
