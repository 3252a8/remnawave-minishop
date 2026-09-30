"""Recoverable rotation intent, shared across backend processes and entry points."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String

from db.base import Base


class SubscriptionAccessRotation(Base):
    __tablename__ = "subscription_access_rotations"

    panel_user_uuid = Column(String(64), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    old_short_uuid = Column(String(64), nullable=False)
    new_short_uuid = Column(String(64), nullable=True)
    state = Column(String(16), nullable=False, default="pending")
    lease_token = Column(String(36), nullable=False)
    lease_until = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
