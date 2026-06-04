from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
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
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True, unique=True, index=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
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

    def __repr__(self):
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
    last_notification_sent = Column(DateTime(timezone=True), nullable=True)
    provider = Column(String, nullable=True)
    skip_notifications = Column(Boolean, default=False)
    # Trial and registration/referral-bonus subscriptions are only a few days
    # long, so the multi-day "ending soon" reminders would fire almost as soon
    # as they are granted. While this is set the worker keeps only the
    # hours-before reminder plus the expiry/after-expiry notices; a real payment
    # clears it so the full reminder spectrum resumes.
    suppress_early_expiry_notifications = Column(Boolean, nullable=False, default=False)
    auto_renew_enabled = Column(Boolean, default=True, index=True)
    tariff_key = Column(String, nullable=True, index=True)
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
    extra_hwid_devices = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="subscriptions")

    def __repr__(self):
        return f"<Subscription(id={self.subscription_id}, user_id={self.user_id}, panel_uuid='{self.panel_user_uuid}', ends='{self.end_date}')>"  # noqa: E501


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
    __table_args__ = (Index("ix_payments_user_id_status", "user_id", "status"),)

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    yookassa_payment_id = Column(String, unique=True, index=True, nullable=True)
    provider_payment_id = Column(String, unique=True, nullable=True)
    provider = Column(String, nullable=False, default="yookassa", index=True)
    idempotence_key = Column(String, unique=True, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    subscription_duration_months = Column(Integer, nullable=True)
    sale_mode = Column(String, nullable=True, index=True)
    tariff_key = Column(String, nullable=True, index=True)
    purchased_gb = Column(Float, nullable=True)
    purchased_hwid_devices = Column(Integer, nullable=True)
    hwid_valid_from = Column(DateTime(timezone=True), nullable=True)
    hwid_valid_until = Column(DateTime(timezone=True), nullable=True)
    hwid_pricing_period_months = Column(Integer, nullable=True)
    hwid_proration_ratio = Column(Float, nullable=True)
    hwid_full_price = Column(Float, nullable=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.promo_code_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User", back_populates="payments")
    promo_code_used = relationship("PromoCode", back_populates="payments_where_used")


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


class PromoCode(Base):
    __tablename__ = "promo_codes"

    promo_code_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False, index=True)
    bonus_days = Column(Integer, nullable=False)
    max_activations = Column(Integer, nullable=False)
    current_activations = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_by_admin_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)

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

    promo_code = relationship("PromoCode", back_populates="activations")
    user = relationship("User", back_populates="promo_code_activations")
    payment = relationship("Payment")

    __table_args__ = (
        UniqueConstraint("promo_code_id", "user_id", name="uq_promo_user_activation"),
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


class MessageLog(Base):
    __tablename__ = "message_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    telegram_username = Column(String, nullable=True)
    telegram_first_name = Column(String, nullable=True)
    event_type = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=True)
    raw_update_preview = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_admin_event = Column(Boolean, default=False)
    target_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)

    author_user = relationship(
        "User", foreign_keys=[user_id], back_populates="message_logs_authored"
    )
    target_user = relationship(
        "User", foreign_keys=[target_user_id], back_populates="message_logs_targeted"
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    subject = Column(String(160), nullable=False)
    category = Column(String(32), nullable=False, default="other", index=True)
    priority = Column(String(16), nullable=False, default="normal", index=True)
    status = Column(String(24), nullable=False, default="open", index=True)
    assigned_admin_id = Column(BigInteger, nullable=True, index=True)
    last_message_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_message_role = Column(String(16), nullable=True)
    unread_user_count = Column(Integer, nullable=False, default=0)
    unread_admin_count = Column(Integer, nullable=False, default=0)
    admin_last_notified_at = Column(DateTime(timezone=True), nullable=True)
    admin_last_emailed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_admin_id = Column(BigInteger, nullable=True)

    user = relationship("User")
    messages = relationship(
        "SupportTicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_support_tickets_status_last_msg", "status", "last_message_at"),)


class SupportTicketMessage(Base):
    __tablename__ = "support_ticket_messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(
        Integer,
        ForeignKey("support_tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_role = Column(String(16), nullable=False)
    author_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    body = Column(Text, nullable=False)
    is_internal_note = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    read_by_user_at = Column(DateTime(timezone=True), nullable=True)
    read_by_admin_at = Column(DateTime(timezone=True), nullable=True)

    ticket = relationship("SupportTicket", back_populates="messages")
    author_user = relationship("User")


class PanelSyncStatus(Base):
    __tablename__ = "panel_sync_status"

    id = Column(Integer, primary_key=True, default=1, autoincrement=False)
    last_sync_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    users_processed_from_panel = Column(Integer, default=0)
    subscriptions_synced = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint("id"),)


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"

    ad_campaign_id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False, index=True)
    start_param = Column(String, nullable=False, unique=True, index=True)
    cost = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    attributions = relationship(
        "AdAttribution",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<AdCampaign(id={self.ad_campaign_id}, source='{self.source}', start_param='{self.start_param}', cost={self.cost})>"  # noqa: E501


class AdAttribution(Base):
    __tablename__ = "ad_attributions"

    user_id = Column(BigInteger, ForeignKey("users.user_id"), primary_key=True, index=True)
    ad_campaign_id = Column(
        Integer, ForeignKey("ad_campaigns.ad_campaign_id"), nullable=False, index=True
    )
    first_start_at = Column(DateTime(timezone=True), server_default=func.now())
    trial_activated_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    campaign = relationship("AdCampaign", back_populates="attributions")


class AppSettingOverride(Base):
    __tablename__ = "app_setting_overrides"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by = Column(BigInteger, nullable=True)


class LocaleOverride(Base):
    __tablename__ = "locale_overrides"

    lang = Column(String(16), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by = Column(BigInteger, nullable=True)
