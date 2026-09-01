from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True, unique=True, index=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    notification_email = Column(String(254), nullable=True)
    password_hash = Column(String, nullable=True)
    password_set_at = Column(DateTime(timezone=True), nullable=True)
    telegram_id = Column(BigInteger, nullable=True, unique=True, index=True)
    telegram_photo_url = Column(Text, nullable=True)
    telegram_notifications_status = Column(String(32), nullable=False, default="unknown")
    telegram_notifications_checked_at = Column(DateTime(timezone=True), nullable=True)
    telegram_notifications_enabled_at = Column(DateTime(timezone=True), nullable=True)
    telegram_notifications_blocked_at = Column(DateTime(timezone=True), nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    language_code = Column(String, default="ru")
    registration_date = Column(DateTime(timezone=True), server_default=func.now())
    is_banned = Column(Boolean, default=False)
    panel_user_uuid = Column(String, nullable=True, unique=True, index=True)
    referral_code = Column(String(64), nullable=True, unique=True, index=True)
    referred_by_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    lifetime_used_traffic_bytes = Column(BigInteger, nullable=True)
    lifetime_used_traffic_synced_at = Column(DateTime(timezone=True), nullable=True)
    trial_eligibility_reset_at = Column(DateTime(timezone=True), nullable=True)
    referral_welcome_bonus_claimed_at = Column(DateTime(timezone=True), nullable=True)
    channel_subscription_verified = Column(Boolean, nullable=True)
    channel_subscription_checked_at = Column(DateTime(timezone=True), nullable=True)
    channel_subscription_verified_for = Column(BigInteger, nullable=True)

    referrer = relationship("User", remote_side=[user_id], backref="referrals")
    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    promo_code_activations = relationship(
        "PromoCodeActivation", back_populates="user", cascade="all, delete-orphan"
    )
    message_logs_authored = relationship(
        "MessageLog",
        foreign_keys="MessageLog.user_id",
        back_populates="author_user",
        cascade="all, delete-orphan",
    )
    message_logs_targeted = relationship(
        "MessageLog",
        foreign_keys="MessageLog.target_user_id",
        back_populates="target_user",
        cascade="all, delete-orphan",
    )
    panel_squad_overrides = relationship(
        "UserPanelSquadOverride",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username='{self.username}')>"


class UserTelegramAvatar(Base):
    __tablename__ = "user_telegram_avatars"

    user_id = Column(
        BigInteger,
        ForeignKey("users.user_id"),
        primary_key=True,
        index=True,
    )
    file_unique_id = Column(String, nullable=True, index=True)
    content_type = Column(String(64), nullable=False, default="image/jpeg")
    image_bytes = Column(LargeBinary, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")


class UserPanelSquadOverride(Base):
    __tablename__ = "user_panel_squad_overrides"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "panel_user_uuid",
            "kind",
            "override_key",
            name="uq_user_panel_squad_override_key",
        ),
        Index("ix_user_panel_squad_overrides_user_active", "user_id", "is_active"),
        Index(
            "ix_user_panel_squad_overrides_panel_active",
            "panel_user_uuid",
            "is_active",
        ),
        Index("ix_user_panel_squad_overrides_kind_squad", "kind", "squad_uuid"),
    )

    override_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    panel_user_uuid = Column(String, nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    override_key = Column(String, nullable=False)
    squad_uuid = Column(String, nullable=True)
    mode = Column(String(16), nullable=False, default="set")
    source = Column(String(16), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by_admin_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)

    user = relationship("User", back_populates="panel_squad_overrides")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_is_active_end_date", "is_active", "end_date"),
        Index("ix_subscriptions_user_id_is_active", "user_id", "is_active"),
    )

    subscription_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    panel_user_uuid = Column(String, nullable=False, index=True)
    panel_subscription_uuid = Column(String, unique=True, index=True, nullable=True)
    install_share_token = Column(String(32), unique=True, index=True, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_months = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    status_from_panel = Column(String, nullable=True)
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
    auto_renew_enabled = Column(Boolean, default=True, index=True)
    auto_renew_consent_version = Column(Integer, nullable=False, default=0)
    tariff_key = Column(String, nullable=True, index=True)
    tariff_binding_source = Column(String(32), nullable=True, index=True)
    tariff_bound_at = Column(DateTime(timezone=True), nullable=True)
    tariff_binding_note = Column(String(255), nullable=True)
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
    is_throttled = Column(Boolean, nullable=False, default=False, index=True)
    effective_monthly_price_rub = Column(Numeric, nullable=True)
    hwid_device_limit = Column(Integer, nullable=True)
    hwid_device_limit_is_override = Column(Boolean, nullable=False, default=False)
    extra_hwid_devices = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription(id={self.subscription_id}, user_id={self.user_id}, panel_uuid='{self.panel_user_uuid}', ends='{self.end_date}')>"  # noqa: E501


class AutoRenewCycle(Base):
    """Durable coordinator for one subscription renewal billing cycle."""

    __tablename__ = "auto_renew_cycles"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "cycle_anchor",
            name="uq_auto_renew_cycles_subscription_anchor",
        ),
        Index("ix_auto_renew_cycles_state_next_attempt", "state", "next_attempt_at"),
        Index("ix_auto_renew_cycles_user_state", "user_id", "state"),
    )

    cycle_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer,
        ForeignKey("subscriptions.subscription_id"),
        nullable=False,
        index=True,
    )
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    cycle_anchor = Column(Date, nullable=False)
    renewal_cycle_end = Column(DateTime(timezone=True), nullable=False, index=True)
    state = Column(String(32), nullable=False, default="scheduled", index=True)
    base_idempotence_key = Column(String(64), nullable=False, unique=True)
    consent_version = Column(Integer, nullable=False, default=0)
    payment_method_id = Column(
        Integer,
        ForeignKey("user_payment_methods.method_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_method_provider_id = Column(String, nullable=False)
    financial_attempts = Column(Integer, nullable=False, default=0)
    transport_replays = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    current_payment_id = Column(Integer, nullable=True, index=True)
    request_snapshot = Column(Text, nullable=False)
    last_failure_kind = Column(String(64), nullable=True, index=True)
    last_http_status = Column(Integer, nullable=True)
    last_provider_code = Column(String(128), nullable=True)
    cancellation_party = Column(String(64), nullable=True)
    cancellation_reason = Column(String(128), nullable=True, index=True)
    stopped_reason = Column(String(128), nullable=True, index=True)
    retry_notified_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    subscription = relationship("Subscription")
    user = relationship("User")
    payment_method = relationship("UserPaymentMethod")


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    code_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, index=True)
    code_hash = Column(String, nullable=False)
    magic_token_hash = Column(String, nullable=True, index=True)
    purpose = Column(String, nullable=False, index=True)
    target_user_id = Column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
        index=True,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    target_user = relationship("User")


class SecurityThrottle(Base):
    __tablename__ = "security_throttles"

    throttle_id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(64), nullable=False, index=True)
    identifier = Column(String(512), nullable=False, index=True)
    failures = Column(Integer, nullable=False, default=0)
    window_started_at = Column(DateTime(timezone=True), nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True, index=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("scope", "identifier", name="uq_security_throttles_scope_identifier"),
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_user_id_status", "user_id", "status"),
        UniqueConstraint(
            "provider",
            "provider_payment_id",
            name="uq_payments_provider_payment_id",
        ),
        Index(
            "uq_payments_auto_renew_cycle_attempt",
            "auto_renew_cycle_id",
            "renewal_attempt_number",
            unique=True,
            postgresql_where=text(
                "auto_renew_cycle_id IS NOT NULL AND renewal_attempt_number IS NOT NULL"
            ),
            sqlite_where=text(
                "auto_renew_cycle_id IS NOT NULL AND renewal_attempt_number IS NOT NULL"
            ),
        ),
    )

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    yookassa_payment_id = Column(String, unique=True, index=True, nullable=True)
    provider_payment_id = Column(String, nullable=True)
    provider_payment_url = Column(String, nullable=True)
    checkout_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    provider_checked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    failure_notified_at = Column(DateTime(timezone=True), nullable=True, index=True)
    provider = Column(String, nullable=False, default="yookassa", index=True)
    funding_source = Column(String(48), nullable=False, default="external", index=True)
    idempotence_key = Column(String, unique=True, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    subscription_duration_months = Column(Integer, nullable=True)
    # Persistent attribution for merchant-initiated recurring charges. These
    # fields stay nullable for historic and ordinary one-off payments.
    is_auto_renew = Column(Boolean, nullable=False, default=False, index=True)
    renewal_subscription_id = Column(Integer, nullable=True, index=True)
    renewal_cycle_end = Column(DateTime(timezone=True), nullable=True)
    auto_renew_cycle_id = Column(
        Integer,
        ForeignKey("auto_renew_cycles.cycle_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    renewal_attempt_number = Column(Integer, nullable=True)
    renewal_consent_version = Column(Integer, nullable=True)
    renewal_payment_method_id = Column(Integer, nullable=True, index=True)
    provider_request_snapshot = Column(Text, nullable=True)
    failure_kind = Column(String(64), nullable=True, index=True)
    failure_http_status = Column(Integer, nullable=True)
    failure_provider_code = Column(String(128), nullable=True)
    provider_cancellation_party = Column(String(64), nullable=True)
    provider_cancellation_reason = Column(String(128), nullable=True, index=True)
    sale_mode = Column(String, nullable=True, index=True)
    tariff_key = Column(String, nullable=True, index=True)
    purchased_gb = Column(Float, nullable=True)
    purchased_hwid_devices = Column(Integer, nullable=True)
    hwid_valid_from = Column(DateTime(timezone=True), nullable=True)
    hwid_valid_until = Column(DateTime(timezone=True), nullable=True)
    hwid_pricing_period_months = Column(Integer, nullable=True)
    hwid_proration_ratio = Column(Float, nullable=True)
    hwid_full_price = Column(Float, nullable=True)
    hwid_traffic_bonus_bytes = Column(BigInteger, nullable=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.promo_code_id"), nullable=True)
    promo_effect_summary = Column(String, nullable=True)
    promo_bonus_days = Column(Integer, nullable=True)
    promo_regular_traffic_gb = Column(Numeric(12, 3), nullable=True)
    promo_premium_traffic_gb = Column(Numeric(12, 3), nullable=True)
    promo_discount_percent = Column(Numeric(5, 2), nullable=True)
    promo_duration_multiplier = Column(Numeric(6, 3), nullable=True)
    promo_traffic_multiplier = Column(Numeric(6, 3), nullable=True)
    promo_applies_to = Column(String(32), nullable=True)
    promo_min_subscription_months = Column(Integer, nullable=True)
    promo_min_traffic_gb = Column(Numeric(10, 2), nullable=True)
    checkout_base_amount = Column(Float, nullable=True)
    checkout_discount_amount = Column(Float, nullable=True)
    checkout_charged_months = Column(Integer, nullable=True)
    checkout_charged_gb = Column(Float, nullable=True)
    checkout_quoted_at = Column(DateTime(timezone=True), nullable=True)
    checkout_total_amount = Column(Float, nullable=True)
    user_balance_amount_minor = Column(BigInteger, nullable=True)
    user_balance_currency_scale = Column(Integer, nullable=True)
    partner_balance_amount_minor = Column(BigInteger, nullable=True)
    partner_balance_currency_scale = Column(Integer, nullable=True)
    tariff_change_quote_snapshot = Column(Text, nullable=True)
    entitlement_context_snapshot = Column(Text, nullable=True)
    checkout_bundle_snapshot = Column(Text, nullable=True)
    checkout_bundle_hash = Column(String(64), nullable=True, index=True)
    fulfillment_source = Column(String(16), nullable=True, index=True)
    fulfilled_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fulfilled_by_admin_id = Column(BigInteger, nullable=True)
    fulfillment_note = Column(String(500), nullable=True)
    fulfillment_before_snapshot = Column(Text, nullable=True)
    fulfillment_after_snapshot = Column(Text, nullable=True)
    promo_conflict_override = Column(Boolean, nullable=False, default=False)
    reversed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    reversed_by_admin_id = Column(BigInteger, nullable=True)
    reversal_note = Column(String(500), nullable=True)
    promo_usage_restored = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User", back_populates="payments")
    promo_code_used = relationship("PromoCode", back_populates="payments_where_used")
    auto_renew_cycle = relationship("AutoRenewCycle")


class TributeEntitlement(Base):
    """Provider-side subscription binding kept stable across tariff config edits."""

    __tablename__ = "tribute_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "tribute_subscription_id",
            "trb_user_id",
            name="uq_tribute_entitlements_subscription_user",
        ),
        Index(
            "ix_tribute_entitlements_telegram_subscription",
            "telegram_user_id",
            "tribute_subscription_id",
        ),
    )

    entitlement_id = Column(Integer, primary_key=True, autoincrement=True)
    tribute_subscription_id = Column(BigInteger, nullable=False, index=True)
    tribute_period_id = Column(BigInteger, nullable=False)
    trb_user_id = Column(String(128), nullable=False)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    tariff_key = Column(String, nullable=True, index=True)
    duration_months = Column(Integer, nullable=True)
    subscription_type = Column(String(16), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    active_until = Column(DateTime(timezone=True), nullable=False, index=True)
    last_event_name = Column(String(64), nullable=False)
    last_event_created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_event_fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")


class TributeWebhookEvent(Base):
    """Immutable, privacy-minimized receipt used for webhook idempotency."""

    __tablename__ = "tribute_webhook_events"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    event_name = Column(String(64), nullable=False, index=True)
    tribute_subscription_id = Column(BigInteger, nullable=False, index=True)
    tribute_period_id = Column(BigInteger, nullable=False)
    trb_user_id = Column(String(128), nullable=False)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    event_created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    event_sent_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    price = Column(BigInteger, nullable=False)
    amount = Column(BigInteger, nullable=False)
    currency = Column(String(16), nullable=False)
    status = Column(String(32), nullable=False, default="processing", index=True)
    status_reason = Column(String(128), nullable=True)
    payment_id = Column(
        Integer,
        ForeignKey("payments.payment_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    payment = relationship("Payment")


class TributeProductPurchase(Base):
    """Immutable SKU snapshot and lifecycle for one Tribute Digital Product purchase."""

    __tablename__ = "tribute_product_purchases"

    purchase_row_id = Column(Integer, primary_key=True, autoincrement=True)
    tribute_purchase_id = Column(BigInteger, nullable=False, unique=True, index=True)
    tribute_transaction_id = Column(BigInteger, nullable=False)
    tribute_product_id = Column(BigInteger, nullable=False, index=True)
    trb_user_id = Column(String(128), nullable=True)
    telegram_user_id = Column(BigInteger, nullable=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    tariff_key = Column(String, nullable=True, index=True)
    sale_mode = Column(String(64), nullable=True)
    units = Column(Float, nullable=True)
    amount = Column(BigInteger, nullable=False)
    currency = Column(String(16), nullable=False)
    status = Column(String(32), nullable=False, default="processing", index=True)
    status_reason = Column(String(128), nullable=True)
    payment_id = Column(
        Integer,
        ForeignKey("payments.payment_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    purchase_created_at = Column(DateTime(timezone=True), nullable=True)
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    refund_reason = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")
    payment = relationship("Payment")


class TributeShopWebhookEvent(Base):
    """Durable receipt for one semantic Tribute Shop webhook delivery."""

    __tablename__ = "tribute_shop_webhook_events"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    event_name = Column(String(64), nullable=False, index=True)
    order_uuid = Column(String(36), nullable=False, index=True)
    event_created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    event_sent_at = Column(DateTime(timezone=True), nullable=False)
    amount = Column(BigInteger, nullable=True)
    currency = Column(String(16), nullable=True)
    transaction_id = Column(BigInteger, nullable=True, index=True)
    status = Column(String(32), nullable=False, default="processing", index=True)
    status_reason = Column(String(128), nullable=True)
    payment_id = Column(
        Integer,
        ForeignKey("payments.payment_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    payment = relationship("Payment")


class TrafficTopup(Base):
    __tablename__ = "traffic_topups"

    topup_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.subscription_id"), nullable=False, index=True
    )
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=True, index=True)
    purchased_bytes = Column(BigInteger, nullable=False)
    kind = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subscription = relationship("Subscription")
    payment = relationship("Payment")


class FlexibleTrafficLimit(Base):
    """A resettable tariff quota override valid for an entitlement window.

    Unlike :class:`TrafficTopup`, this value replaces the tariff baseline for
    every accounting reset inside its window and is never a consumable balance.
    Multiple rows may overlap after an upgrade; the highest active limit wins,
    preserving already-paid entitlement while allowing future downgrades.
    """

    __tablename__ = "flexible_traffic_limits"
    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "kind",
            "valid_from",
            "valid_until",
            name="uq_flexible_traffic_limit_payment_window",
        ),
        Index(
            "ix_flexible_traffic_limits_subscription_window",
            "subscription_id",
            "kind",
            "valid_from",
            "valid_until",
        ),
    )

    limit_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.subscription_id"), nullable=False, index=True
    )
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=True, index=True)
    kind = Column(String(32), nullable=False, index=True)
    tariff_key = Column(String, nullable=False, index=True)
    limit_bytes = Column(BigInteger, nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    monthly_amount = Column(Float, nullable=False, default=0)
    monthly_stars_amount = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    subscription = relationship("Subscription")
    payment = relationship("Payment")


class HwidDevicePurchase(Base):
    __tablename__ = "hwid_device_purchases"
    __table_args__ = (
        Index(
            "ix_hwid_device_purchases_subscription_window",
            "subscription_id",
            "valid_from",
            "valid_until",
        ),
    )

    purchase_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.subscription_id"), nullable=False, index=True
    )
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=True, index=True)
    purchased_devices = Column(Integer, nullable=False)
    traffic_bonus_bytes = Column(BigInteger, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subscription = relationship("Subscription")
    payment = relationship("Payment")


class TrafficWarning(Base):
    __tablename__ = "traffic_warnings"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "period_start_at", "level", name="uq_traffic_warning_period_level"
        ),
    )

    warning_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.subscription_id"), nullable=False, index=True
    )
    period_start_at = Column(DateTime(timezone=True), nullable=True)
    level = Column(Integer, nullable=False)
    traffic_limit_bytes = Column(BigInteger, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())

    subscription = relationship("Subscription")


class SubscriptionNotification(Base):
    __tablename__ = "subscription_notifications"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "notification_key",
            name="uq_subscription_notification_key",
        ),
    )

    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.subscription_id"), nullable=False, index=True
    )
    notification_key = Column(String(64), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())

    subscription = relationship("Subscription")


class TariffChange(Base):
    __tablename__ = "tariff_changes"

    change_id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.subscription_id"), nullable=False, index=True
    )
    from_tariff_key = Column(String, nullable=True)
    to_tariff_key = Column(String, nullable=False)
    mode = Column(String, nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=True, index=True)
    days_before = Column(Integer, nullable=True)
    days_after = Column(Integer, nullable=True)
    converted_bytes = Column(BigInteger, nullable=True)
    converted_hwid_value_rub = Column(Numeric, nullable=True)
    converted_hwid_days = Column(Integer, nullable=True)
    eff_price_before = Column(Numeric, nullable=True)
    eff_price_after = Column(Numeric, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subscription = relationship("Subscription")
    payment = relationship("Payment")


class UserBilling(Base):
    __tablename__ = "user_billing"

    user_id = Column(BigInteger, ForeignKey("users.user_id"), primary_key=True)
    # Saved payment method for off-session recurring charges (YooKassa)
    yookassa_payment_method_id = Column(String, nullable=True, unique=True)
    card_last4 = Column(String, nullable=True)
    card_network = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User")


class UserPaymentMethod(Base):
    __tablename__ = "user_payment_methods"

    method_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    provider = Column(String, nullable=False, default="yookassa", index=True)
    provider_payment_method_id = Column(String, nullable=False, unique=True, index=True)
    card_last4 = Column(String, nullable=True)
    card_network = Column(String, nullable=True)
    is_default = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User")
    __table_args__ = (
        UniqueConstraint("user_id", "provider_payment_method_id", name="uq_user_provider_method"),
    )


class PlategaSubscription(Base):
    """One Platega SBP subscription mandate (provider-managed recurrence).

    Platega owns the schedule: it charges the payer every ``interval_code``
    period and reports each attempt on the shared Platega webhook. This row is
    the local mirror of that mandate — it is what lets a renewal charge be
    attributed to a customer and an entitlement long after the original
    checkout, and what the customer's "turn auto-renew off" action cancels.
    Rows are created by the webhook (never by checkout), so a mandate the payer
    abandoned never appears here.
    """

    __tablename__ = "platega_subscriptions"
    __table_args__ = (Index("ix_platega_subscriptions_user_status", "user_id", "status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    platega_subscription_id = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    # Local lifecycle: active | past_due | cancelled | failed.
    status = Column(String(32), nullable=False, default="active", index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    # Platega SubscriptionInterval (1=day, 2=week, 3=month, 4=year).
    interval_code = Column(Integer, nullable=False)
    months = Column(Integer, nullable=False)
    sale_mode = Column(String, nullable=True)
    tariff_key = Column(String, nullable=True, index=True)
    next_charge_at = Column(DateTime(timezone=True), nullable=True)
    last_charge_at = Column(DateTime(timezone=True), nullable=True)
    charges_count = Column(Integer, nullable=False, default=0)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")


class RollyPaySubscription(Base):
    """Local mirror of a provider-managed RollyPay recurring SBP mandate."""

    __tablename__ = "rollypay_subscriptions"
    __table_args__ = (
        Index(
            "ix_rollypay_subscriptions_user_billing_status",
            "user_id",
            "billing_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    rollypay_subscription_id = Column(String, nullable=False, unique=True, index=True)
    anchor_payment_id = Column(
        Integer,
        ForeignKey("payments.payment_id"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    provider_state = Column(String(32), nullable=False, default="new", index=True)
    billing_status = Column(String(32), nullable=False, default="consent_pending", index=True)
    plan_id = Column(String, nullable=False)
    plan_code = Column(String, nullable=False)
    plan_version = Column(Integer, nullable=False)
    interval = Column(String(16), nullable=False)
    max_cycles = Column(Integer, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="RUB")
    months = Column(Integer, nullable=False)
    sale_mode = Column(String, nullable=True)
    tariff_key = Column(String, nullable=True, index=True)
    next_charge_at = Column(DateTime(timezone=True), nullable=True)
    last_charge_at = Column(DateTime(timezone=True), nullable=True)
    charges_count = Column(Integer, nullable=False, default=0)
    first_provider_payment_id = Column(String, nullable=True, unique=True, index=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")
    anchor_payment = relationship("Payment")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    promo_code_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False, index=True)
    bonus_days = Column(Integer, nullable=False)
    regular_traffic_gb = Column(Numeric(12, 3), nullable=True)
    premium_traffic_gb = Column(Numeric(12, 3), nullable=True)
    discount_percent = Column(Numeric(5, 2), nullable=True)
    duration_multiplier = Column(Numeric(6, 3), nullable=True)
    traffic_multiplier = Column(Numeric(6, 3), nullable=True)
    bonus_requires_payment = Column(Boolean, nullable=False, default=False)
    applies_to = Column(String(32), nullable=False, default="all")
    min_subscription_months = Column(Integer, nullable=True)
    min_traffic_gb = Column(Numeric(10, 2), nullable=True)
    origin = Column(String(32), nullable=False, default="admin")
    # Set only for a code minted for one customer; NULL means a shared code.
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    max_activations = Column(Integer, nullable=False)
    current_activations = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_by_admin_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_code = Column(String, nullable=True)

    activations = relationship(
        "PromoCodeActivation", back_populates="promo_code", cascade="all, delete-orphan"
    )
    payments_where_used = relationship("Payment", back_populates="promo_code_used")


class PromoCodeActivation(Base):
    __tablename__ = "promo_code_activations"

    activation_id = Column(Integer, primary_key=True, autoincrement=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.promo_code_id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    activated_at = Column(DateTime(timezone=True), server_default=func.now())
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=True)
    effect_summary = Column(String, nullable=True)
    bonus_days = Column(Integer, nullable=True)
    regular_traffic_gb = Column(Numeric(12, 3), nullable=True)
    premium_traffic_gb = Column(Numeric(12, 3), nullable=True)
    discount_percent = Column(Numeric(5, 2), nullable=True)
    duration_multiplier = Column(Numeric(6, 3), nullable=True)
    traffic_multiplier = Column(Numeric(6, 3), nullable=True)
    applies_to = Column(String(32), nullable=True)
    base_amount = Column(Float, nullable=True)
    discount_amount = Column(Float, nullable=True)
    charged_months = Column(Integer, nullable=True)
    charged_gb = Column(Float, nullable=True)
    granted_days = Column(Integer, nullable=True)
    granted_gb = Column(Float, nullable=True)
    granted_regular_traffic_gb = Column(Numeric(12, 3), nullable=True)
    granted_premium_traffic_gb = Column(Numeric(12, 3), nullable=True)
    is_manual_override = Column(Boolean, nullable=False, default=False)

    promo_code = relationship("PromoCode", back_populates="activations")
    user = relationship("User", back_populates="promo_code_activations")
    payment = relationship("Payment")

    __table_args__ = (
        Index(
            "uq_promo_user_activation_standard",
            "promo_code_id",
            "user_id",
            unique=True,
            postgresql_where=is_manual_override.is_(False),
            sqlite_where=is_manual_override.is_(False),
        ),
    )


class LegacyReferralCode(Base):
    __tablename__ = "legacy_referral_codes"

    legacy_code_id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, default="remnashop", index=True)
    code = Column(String(128), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User")

    __table_args__ = (UniqueConstraint("source", "code", name="uq_legacy_referral_source_code"),)


class LegacyImportMapping(Base):
    __tablename__ = "legacy_import_mappings"

    source = Column(String(64), primary_key=True)
    entity_type = Column(String(64), primary_key=True)
    source_id = Column(String(128), primary_key=True)
    target_table = Column(String(128), nullable=False)
    target_id = Column(String(128), nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


# Register decomposed domain tables in the same metadata used by create_all,
# backup/restore and migration tests.  Domain code imports the classes from
# ``db.partner_models`` directly; this import exists only for registration.
from db import activity_models as activity_models  # noqa: E402
from db import auth_models as auth_models  # noqa: E402
from db import balance_models as balance_models  # noqa: E402
from db import broadcast_models as broadcast_models  # noqa: E402
from db import message_image_models as message_image_models  # noqa: E402
from db import partner_models as partner_models  # noqa: E402

AdAttribution = activity_models.AdAttribution
AdCampaign = activity_models.AdCampaign
AppSettingOverride = activity_models.AppSettingOverride
LocaleOverride = activity_models.LocaleOverride
MessageLog = activity_models.MessageLog
PanelSyncStatus = activity_models.PanelSyncStatus
SupportTicket = activity_models.SupportTicket
SupportTicketMessage = activity_models.SupportTicketMessage
UserExternalIdentity = auth_models.UserExternalIdentity
UserEmailAddress = auth_models.UserEmailAddress
UserPasskeyCredential = auth_models.UserPasskeyCredential
WebAuthnChallenge = auth_models.WebAuthnChallenge
AdminBroadcast = broadcast_models.AdminBroadcast
AdminBroadcastDelivery = broadcast_models.AdminBroadcastDelivery
MessageImage = message_image_models.MessageImage
UserBalanceLedgerEntry = balance_models.UserBalanceLedgerEntry
