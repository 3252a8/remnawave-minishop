"""Delivery history for individual subscription expiry periods and channels."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from db.base import Base


class SubscriptionLifecycleNotification(Base):
    __tablename__ = "subscription_lifecycle_notifications"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "notification_key",
            "period_end_date",
            name="uq_subscription_lifecycle_notification_period",
        ),
    )

    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer,
        ForeignKey("subscriptions.subscription_id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_key = Column(String(64), nullable=False)
    period_end_date = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
