"""Durable, independently retryable period accrual for each invitation participant."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from db.base import Base


class ReferralPeriodAccrual(Base):
    __tablename__ = "referral_period_accruals"
    __table_args__ = (
        UniqueConstraint("payment_id", "role", name="uq_referral_accrual_payment_role"),
        UniqueConstraint("one_time_referee_id", "role", name="uq_referral_accrual_first_role"),
    )

    accrual_id = Column(Integer, primary_key=True)
    payment_id = Column(
        Integer, ForeignKey("payments.payment_id", ondelete="CASCADE"), nullable=False
    )
    gift_id = Column(
        Integer, ForeignKey("subscription_gifts.gift_id", ondelete="SET NULL"), nullable=True
    )
    referee_user_id = Column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    one_time_referee_id = Column(BigInteger, nullable=True)
    role = Column(String(16), nullable=False)
    days = Column(Integer, nullable=False)
    tariff_key = Column(String(128), nullable=True)
    state = Column(String(16), nullable=False, default="pending", index=True)
    target_end_date = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    lease_token = Column(String(36), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(String(256), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
