from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from db.base import Base

BALANCE_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class UserBalanceLedgerEntry(Base):
    """Append-only source of truth for a user's spendable balance."""

    __tablename__ = "user_balance_ledger_entries"
    __table_args__ = (
        CheckConstraint("state IN ('posted', 'void')", name="ck_user_balance_ledger_state"),
        CheckConstraint(
            "kind IN ('payment_topup', 'payment_topup_reversal', 'admin_adjustment', "
            "'checkout_spend', 'checkout_spend_release', 'partner_conversion_in', "
            "'partner_conversion_out')",
            name="ck_user_balance_ledger_kind",
        ),
        Index("ix_user_balance_ledger_user_currency", "user_id", "currency", "created_at"),
        Index("ix_user_balance_ledger_reference", "reference_type", "reference_id"),
    )

    entry_id = Column(BALANCE_ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency = Column(String(16), nullable=False, index=True)
    currency_scale = Column(Integer, nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    kind = Column(String(32), nullable=False, index=True)
    state = Column(String(16), nullable=False, default="posted", index=True)
    reference_type = Column(String(32), nullable=False)
    reference_id = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    actor_admin_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    reason = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    posted_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
