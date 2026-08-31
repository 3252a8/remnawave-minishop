from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.sql import func

from db.base import Base

PARTNER_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class PartnerProfile(Base):
    __tablename__ = "partner_profiles"
    __table_args__ = (
        CheckConstraint(
            "commission_bps >= 0 AND commission_bps <= 10000",
            name="ck_partner_profiles_commission_bps",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'closed')", name="ck_partner_profiles_status"
        ),
        Index("ix_partner_profiles_status_created", "status", "created_at"),
    )

    partner_id = Column(PARTNER_ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    status = Column(String(16), nullable=False, default="active", index=True)
    commission_bps = Column(Integer, nullable=False, default=3000)
    partner_code = Column(String(64), nullable=False, unique=True, index=True)
    display_label_snapshot = Column(String(255), nullable=False)
    welcome_message = Column(Text, nullable=True)
    pause_reason = Column(Text, nullable=True)
    reapply_allowed_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    paused_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PartnerApplication(Base):
    __tablename__ = "partner_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'canceled')",
            name="ck_partner_applications_status",
        ),
        Index("ix_partner_applications_status_submitted", "status", "submitted_at"),
        Index("ix_partner_applications_user_submitted", "user_id", "submitted_at"),
        Index(
            "uq_partner_applications_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND user_id IS NOT NULL"),
            sqlite_where=text("status = 'pending' AND user_id IS NOT NULL"),
        ),
    )

    application_id = Column(PARTNER_ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_label_snapshot = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by_admin_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_message = Column(Text, nullable=True)
    approved_commission_bps = Column(Integer, nullable=True)
    welcome_message = Column(Text, nullable=True)
    reapply_allowed_at = Column(DateTime(timezone=True), nullable=True)


class PartnerClient(Base):
    __tablename__ = "partner_clients"
    __table_args__ = (
        CheckConstraint(
            "source IN ('partner_telegram_link', 'partner_web_link', "
            "'referral_import', 'admin_manual')",
            name="ck_partner_clients_source",
        ),
        Index("ix_partner_clients_partner_attributed", "partner_id", "attributed_at"),
    )

    partner_client_id = Column(PARTNER_ID_TYPE, primary_key=True, autoincrement=True)
    partner_id = Column(
        BigInteger,
        ForeignKey("partner_profiles.partner_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_user_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    public_client_id = Column(String(32), nullable=False, unique=True, index=True)
    public_label_snapshot = Column(String(255), nullable=False)
    source = Column(String(32), nullable=False)
    attributed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    eligible_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    welcome_bonus_eligible_at = Column(DateTime(timezone=True), nullable=True)
    attributed_by_admin_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )


class PartnerCommission(Base):
    __tablename__ = "partner_commissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'available', 'reversed', 'excluded')",
            name="ck_partner_commissions_status",
        ),
        CheckConstraint("gross_amount_minor >= 0", name="ck_partner_commissions_gross"),
        CheckConstraint("commission_amount_minor >= 0", name="ck_partner_commissions_amount"),
        Index("ix_partner_commissions_partner_created", "partner_id", "created_at"),
        Index("ix_partner_commissions_status_available", "status", "available_at"),
    )

    commission_id = Column(PARTNER_ID_TYPE, primary_key=True, autoincrement=True)
    partner_id = Column(
        BigInteger,
        ForeignKey("partner_profiles.partner_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    partner_client_id = Column(
        BigInteger,
        ForeignKey("partner_clients.partner_client_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payment_id = Column(
        Integer,
        ForeignKey("payments.payment_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    gross_amount_minor = Column(BigInteger, nullable=False)
    commission_amount_minor = Column(BigInteger, nullable=False)
    currency = Column(String(16), nullable=False, index=True)
    currency_scale = Column(Integer, nullable=False)
    commission_bps_snapshot = Column(Integer, nullable=False)
    sale_mode_snapshot = Column(String(64), nullable=True)
    provider_snapshot = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, index=True)
    exclusion_reason = Column(String(64), nullable=True)
    source_paid_at = Column(DateTime(timezone=True), nullable=False)
    available_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reversed_at = Column(DateTime(timezone=True), nullable=True)


class PartnerLedgerEntry(Base):
    __tablename__ = "partner_ledger_entries"
    __table_args__ = (
        CheckConstraint("state IN ('pending', 'posted', 'void')", name="ck_partner_ledger_state"),
        CheckConstraint(
            "kind IN ('commission_credit', 'manual_adjustment', 'withdrawal_reserve', "
            "'withdrawal_release', 'subscription_spend', 'subscription_spend_release', "
            "'checkout_spend', 'checkout_spend_release', 'commission_reversal', "
            "'balance_conversion_in', 'balance_conversion_out')",
            name="ck_partner_ledger_kind",
        ),
        Index("ix_partner_ledger_partner_currency", "partner_id", "currency", "created_at"),
        Index("ix_partner_ledger_reference", "reference_type", "reference_id"),
    )

    entry_id = Column(PARTNER_ID_TYPE, primary_key=True, autoincrement=True)
    partner_id = Column(
        BigInteger,
        ForeignKey("partner_profiles.partner_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    currency = Column(String(16), nullable=False, index=True)
    currency_scale = Column(Integer, nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    withdrawable_amount_minor = Column(BigInteger, nullable=False, default=0)
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
    posted_at = Column(DateTime(timezone=True), nullable=True)


class PartnerWithdrawal(Base):
    __tablename__ = "partner_withdrawals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'processing', 'paid', 'rejected', 'canceled', 'failed')",
            name="ck_partner_withdrawals_status",
        ),
        CheckConstraint("debit_amount_minor > 0", name="ck_partner_withdrawals_amount"),
        Index("ix_partner_withdrawals_status_requested", "status", "requested_at"),
        Index("ix_partner_withdrawals_partner_requested", "partner_id", "requested_at"),
    )

    withdrawal_id = Column(PARTNER_ID_TYPE, primary_key=True, autoincrement=True)
    partner_id = Column(
        BigInteger,
        ForeignKey("partner_profiles.partner_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    method_id_snapshot = Column(String(64), nullable=False)
    method_type_snapshot = Column(String(32), nullable=False)
    method_snapshot_json = Column(Text, nullable=False)
    debit_amount_minor = Column(BigInteger, nullable=False)
    debit_currency = Column(String(16), nullable=False, index=True)
    currency_scale = Column(Integer, nullable=False)
    settlement_asset = Column(String(16), nullable=True)
    network = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="requested", index=True)
    status_version = Column(Integer, nullable=False, default=1)
    status_message = Column(Text, nullable=True)
    external_reference = Column(String(255), nullable=True)
    settlement_amount = Column(String(64), nullable=True)
    requisites_ciphertext = Column(LargeBinary, nullable=True)
    requisites_key_id = Column(String(32), nullable=False)
    masked_requisites = Column(String(255), nullable=False)
    client_idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processing_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    handled_by_admin_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )


class PartnerAuditEvent(Base):
    __tablename__ = "partner_audit_events"
    __table_args__ = (
        Index("ix_partner_audit_partner_created", "partner_id", "created_at"),
        Index("ix_partner_audit_event_created", "event_type", "created_at"),
    )

    audit_event_id = Column(PARTNER_ID_TYPE, primary_key=True, autoincrement=True)
    partner_id = Column(
        BigInteger,
        ForeignKey("partner_profiles.partner_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    application_id = Column(
        BigInteger,
        ForeignKey("partner_applications.application_id", ondelete="SET NULL"),
        nullable=True,
    )
    withdrawal_id = Column(
        BigInteger,
        ForeignKey("partner_withdrawals.withdrawal_id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type = Column(String(64), nullable=False, index=True)
    actor_type = Column(String(16), nullable=False)
    actor_user_id = Column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    old_values_json = Column(Text, nullable=True)
    new_values_json = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


__all__ = [
    "PartnerApplication",
    "PartnerAuditEvent",
    "PartnerClient",
    "PartnerCommission",
    "PartnerLedgerEntry",
    "PartnerProfile",
    "PartnerWithdrawal",
]
