"""Durable, owner-scoped extension work and immutable commercial snapshots."""

from sqlalchemy import (
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

from db.base import Base


class ExtensionPresentation(Base):
    __tablename__ = "extension_presentation"
    owner = Column(String(64), primary_key=True)
    target = Column(String(140), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    position = Column(Integer, nullable=False, default=100)


class ExtensionOperation(Base):
    __tablename__ = "extension_operations"
    __table_args__ = (
        UniqueConstraint("owner", "kind", "idempotency_key", name="uq_extension_operation_key"),
        Index("ix_extension_operations_due", "state", "not_before"),
    )

    id = Column(String(32), primary_key=True)
    owner = Column(String(64), nullable=False)
    kind = Column(String(80), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    payload_json = Column(Text, nullable=False)
    state = Column(String(16), nullable=False, default="queued")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=10)
    not_before = Column(DateTime(timezone=True), nullable=False)
    lease_token = Column(String(32), nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    result_json = Column(Text, nullable=True)
    error_code = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class ExtensionOrder(Base):
    __tablename__ = "extension_orders"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_extension_order_key"),
    )

    id = Column(String(32), primary_key=True)
    owner = Column(String(64), nullable=False, index=True)
    product = Column(String(64), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_json = Column(Text, nullable=False)
    quote_json = Column(Text, nullable=False)
    payment_id = Column(
        Integer, ForeignKey("payments.payment_id", ondelete="RESTRICT"), unique=True
    )
    payment_state = Column(String(24), nullable=False, default="pending")
    fulfillment_state = Column(String(24), nullable=False, default="pending")
    reference = Column(String(256), nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
