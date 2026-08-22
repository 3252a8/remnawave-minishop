from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
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


class MessageLog(Base):
    __tablename__ = "message_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    telegram_username = Column(String, nullable=True)
    telegram_first_name = Column(String, nullable=True)
    event_type = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=True)
    raw_update_preview = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_admin_event = Column(Boolean, default=False)
    target_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)

    author_user = relationship(
        "User", foreign_keys=[user_id], back_populates="message_logs_authored"
    )
    target_user = relationship(
        "User", foreign_keys=[target_user_id], back_populates="message_logs_targeted"
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    subject = Column(String(160), nullable=False)
    category = Column(String(32), nullable=False, default="other", index=True)
    priority = Column(String(16), nullable=False, default="normal", index=True)
    status = Column(String(24), nullable=False, default="open", index=True)
    assigned_admin_id = Column(BigInteger, nullable=True, index=True)
    last_message_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_message_role = Column(String(16), nullable=True)
    unread_user_count = Column(Integer, nullable=False, default=0)
    unread_admin_count = Column(Integer, nullable=False, default=0)
    admin_last_notified_at = Column(DateTime(timezone=True), nullable=True)
    admin_last_emailed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_admin_id = Column(BigInteger, nullable=True)

    user = relationship("User")
    messages = relationship(
        "SupportTicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_support_tickets_status_last_msg", "status", "last_message_at"),)


class SupportTicketMessage(Base):
    __tablename__ = "support_ticket_messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(
        Integer,
        ForeignKey("support_tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_role = Column(String(16), nullable=False)
    author_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    body = Column(Text, nullable=False)
    # "text" for everything written before the rich composer; "html" for the
    # Telegram-subset markup it produces. Stored rather than guessed so an old
    # body containing literal tag characters keeps reading as literal text.
    body_format = Column(String(8), nullable=False, default="text", server_default="text")
    # Resolved buttons attached by an admin, as a JSON array of objects: the
    # caption plus the link every channel opens. Resolved at send time so the
    # chat, Telegram and e-mail agree even after the promo code is edited.
    buttons = Column(Text, nullable=True)
    image_id = Column(
        String(32),
        ForeignKey("message_images.image_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_internal_note = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    read_by_user_at = Column(DateTime(timezone=True), nullable=True)
    read_by_admin_at = Column(DateTime(timezone=True), nullable=True)

    ticket = relationship("SupportTicket", back_populates="messages")
    author_user = relationship("User")


class PanelSyncStatus(Base):
    __tablename__ = "panel_sync_status"

    id = Column(Integer, primary_key=True, default=1, autoincrement=False)
    last_sync_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    users_processed_from_panel = Column(Integer, default=0)
    subscriptions_synced = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint("id"),)


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"

    ad_campaign_id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False, index=True)
    start_param = Column(String, nullable=False, unique=True, index=True)
    cost = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    attributions = relationship(
        "AdAttribution",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AdCampaign(id={self.ad_campaign_id}, source='{self.source}', start_param='{self.start_param}', cost={self.cost})>"  # noqa: E501


class AdAttribution(Base):
    __tablename__ = "ad_attributions"

    user_id = Column(BigInteger, ForeignKey("users.user_id"), primary_key=True, index=True)
    ad_campaign_id = Column(
        Integer, ForeignKey("ad_campaigns.ad_campaign_id"), nullable=False, index=True
    )
    first_start_at = Column(DateTime(timezone=True), server_default=func.now())
    trial_activated_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    campaign = relationship("AdCampaign", back_populates="attributions")


class AppSettingOverride(Base):
    __tablename__ = "app_setting_overrides"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by = Column(BigInteger, nullable=True)


class LocaleOverride(Base):
    __tablename__ = "locale_overrides"

    lang = Column(String(16), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by = Column(BigInteger, nullable=True)
