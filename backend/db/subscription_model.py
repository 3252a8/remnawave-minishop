"""Subscription entitlement, panel state and administrative suspension."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from db.base import Base
from db.subscription_renewal_columns import SubscriptionRenewalColumns


class Subscription(SubscriptionRenewalColumns, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "uq_subscriptions_suspended_user",
            "user_id",
            unique=True,
            postgresql_where=text("suspended_at IS NOT NULL"),
            sqlite_where=text("suspended_at IS NOT NULL"),
        ),
        Index("ix_subscriptions_is_active_end_date", "is_active", "end_date"),
        Index("ix_subscriptions_user_id_is_active", "user_id", "is_active"),
    )

    subscription_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    panel_user_uuid = Column(String, nullable=False, index=True)
    panel_subscription_uuid = Column(String, unique=True, index=True, nullable=True)
    install_share_token = Column(String(32), unique=True, index=True, nullable=True)
    install_share_panel_short_uuid = Column(String(64), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_months = Column(Integer, nullable=True)
    duration_days = Column(Integer, nullable=True)
    period_semantics = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    status_from_panel = Column(String, nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspension_end_date = Column(DateTime(timezone=True), nullable=True)
    traffic_limit_bytes = Column(BigInteger, nullable=True)
    traffic_used_bytes = Column(BigInteger, nullable=True)
    last_connected_at = Column(DateTime(timezone=True), nullable=True)
    last_notification_sent = Column(DateTime(timezone=True), nullable=True)
    provider = Column(String, nullable=True)
    skip_notifications = Column(Boolean, default=False)
    # Trial and registration/referral-bonus subscriptions can be only a few
    # days long, so multi-day "ending soon" reminders would fire almost as soon
    # as they are granted. The notification worker treats this as a guard for
    # genuinely short grants only; long or later extended rows still receive
    # the local fallback reminder spectrum.
    suppress_early_expiry_notifications = Column(Boolean, nullable=False, default=False)
    tariff_key = Column(String, nullable=True, index=True)
    tariff_binding_source = Column(String(32), nullable=True, index=True)
    tariff_bound_at = Column(DateTime(timezone=True), nullable=True)
    tariff_binding_note = Column(String(255), nullable=True)
    gift_terms_snapshot = Column(Text, nullable=True)
    tier_baseline_bytes = Column(BigInteger, nullable=True)
    topup_balance_bytes = Column(BigInteger, nullable=False, default=0)
    premium_baseline_bytes = Column(BigInteger, nullable=False, default=0)
    premium_topup_balance_bytes = Column(BigInteger, nullable=False, default=0)
    premium_topup_used_bytes = Column(BigInteger, nullable=False, default=0)
    premium_used_bytes = Column(BigInteger, nullable=False, default=0)
    premium_is_limited = Column(Boolean, nullable=False, default=False, index=True)
    premium_period_start_at = Column(DateTime(timezone=True), nullable=True)
    premium_unlimited_override = Column(Boolean, nullable=False, default=False, index=True)
    premium_bonus_bytes = Column(BigInteger, nullable=False, default=0)
    regular_bonus_bytes = Column(BigInteger, nullable=False, default=0)
    regular_unlimited_override = Column(Boolean, nullable=False, default=False, index=True)
    period_start_at = Column(DateTime(timezone=True), nullable=True)
    traffic_period_lifetime_start_bytes = Column(BigInteger, nullable=True)
    traffic_topup_accounting_state = Column(Text, nullable=True)
    is_throttled = Column(Boolean, nullable=False, default=False, index=True)
    effective_monthly_price_rub = Column(Numeric, nullable=True)
    hwid_device_limit = Column(Integer, nullable=True)
    hwid_device_limit_is_override = Column(Boolean, nullable=False, default=False)
    extra_hwid_devices = Column(Integer, nullable=False, default=0)
    tariff_managed_squad_uuids = Column(Text, nullable=True)

    user = relationship("User", back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription(id={self.subscription_id}, user_id={self.user_id}, panel_uuid='{self.panel_user_uuid}', ends='{self.end_date}')>"  # noqa: E501
