"""Persistence model for provider-managed Wata subscriptions."""

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


class WataSubscription(Base):
    __tablename__ = "wata_subscriptions"
    __table_args__ = (Index("ix_wata_subscriptions_user_status", "user_id", "status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    wata_subscription_id = Column(String, nullable=False, unique=True, index=True)
    anchor_payment_id = Column(
        Integer, ForeignKey("payments.payment_id"), nullable=False, unique=True, index=True
    )
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    interval = Column(String(16), nullable=False)
    period = Column(Integer, nullable=False)
    max_periods = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    months = Column(Integer, nullable=False)
    duration_days = Column(Integer, nullable=True)
    subscription_terms_snapshot = Column(Text, nullable=True)
    checkout_bundle_snapshot = Column(Text, nullable=True)
    period_semantics = Column(String(32), nullable=True)
    sale_mode = Column(String, nullable=True)
    tariff_key = Column(String, nullable=True, index=True)
    charges_count = Column(Integer, nullable=False, default=0)
    first_provider_payment_id = Column(String, nullable=True, unique=True, index=True)
    last_charge_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User")
    anchor_payment = relationship("Payment")


__all__ = ["WataSubscription"]
