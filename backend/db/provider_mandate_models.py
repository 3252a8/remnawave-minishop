"""Immutable ownership of hosted, provider-scheduled payment mandates."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from db.base import Base


class ProviderMandate(Base):
    __tablename__ = "provider_mandates"
    __table_args__ = (UniqueConstraint("provider", "remote_id", name="uq_provider_mandate_remote"),)

    mandate_id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(64), nullable=False, index=True)
    remote_id = Column(String(128), nullable=False)
    anchor_payment_id = Column(
        Integer, ForeignKey("payments.payment_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    provider_customer_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    period_days = Column(Integer, nullable=False)
    initial_charge_id = Column(String(192), nullable=True)
    last_charge_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
