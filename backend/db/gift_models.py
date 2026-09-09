"""Paid transferable subscriptions; tokens are bearer credentials."""

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from db.base import Base


class SubscriptionGift(Base):
    __tablename__ = "subscription_gifts"

    gift_id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(
        Integer, ForeignKey("payments.payment_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    purchaser_id = Column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True
    )
    token = Column(String(64), nullable=False, unique=True)
    status = Column(String(20), nullable=False, default="ready")
    recipient_id = Column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True
    )
    activation_end_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    activation_attempted_at = Column(DateTime(timezone=True), nullable=True)
    bonus_days = Column(Integer, nullable=False, default=0)
    regular_bonus_gb = Column(Float, nullable=False, default=0)
    premium_bonus_gb = Column(Float, nullable=False, default=0)
    recipient_email = Column(String(254), nullable=True)
    delivery_status = Column(String(20), nullable=False, default="not_requested")
    delivery_attempts = Column(Integer, nullable=False, default=0)
    delivery_attempted_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
