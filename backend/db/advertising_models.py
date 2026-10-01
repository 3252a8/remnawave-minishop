"""Durable advertising evidence; no entitlement or money mutation belongs here."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AdLink(Base):
    __tablename__ = "ad_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.ad_campaign_id"), index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(160), default="")
    destination: Mapped[str] = mapped_column(String(16), default="web")
    utm_json: Mapped[str] = mapped_column(Text, default="{}")
    landing_path: Mapped[str] = mapped_column(String(512), default="/")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdVisit(Base):
    __tablename__ = "ad_visits"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.user_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AdTouchpoint(Base):
    __tablename__ = "ad_touchpoints"
    __table_args__ = (
        Index("ix_ad_touch_user_time", "user_id", "occurred_at", "id"),
        Index("ix_ad_touch_campaign_time", "campaign_id", "occurred_at", "id"),
        Index("ix_ad_touch_bot_time", "bot_id", "occurred_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(160), unique=True)
    visit_id: Mapped[str | None] = mapped_column(ForeignKey("ad_visits.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.user_id"), index=True)
    original_user_id: Mapped[int | None] = mapped_column(BigInteger)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_campaigns.ad_campaign_id"), index=True
    )
    link_id: Mapped[int | None] = mapped_column(ForeignKey("ad_links.id"))
    channel: Mapped[str] = mapped_column(String(24))
    evidence: Mapped[str] = mapped_column(String(32), default="tagged_link")
    observed_utm_json: Mapped[str] = mapped_column(Text, default="{}")
    utm_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_new_user: Mapped[bool | None] = mapped_column(Boolean)
    bot_id: Mapped[str | None] = mapped_column(String(64))


class AdPurchaseAttribution(Base):
    __tablename__ = "ad_purchase_attributions"
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.payment_id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), index=True)
    original_user_id: Mapped[int] = mapped_column(BigInteger)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_campaigns.ad_campaign_id"), index=True
    )
    link_id: Mapped[int | None] = mapped_column(ForeignKey("ad_links.id"))
    touchpoint_id: Mapped[int | None] = mapped_column(ForeignKey("ad_touchpoints.id"))
    binding_id: Mapped[int | None] = mapped_column(ForeignKey("ad_promo_bindings.id"))
    evidence: Mapped[str] = mapped_column(String(32))
    policy_version: Mapped[str] = mapped_column(String(32), default="last_tagged_checkout_v1")
    window_days: Mapped[int] = mapped_column(Integer, default=30)
    checkout_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_product_purchase: Mapped[bool | None] = mapped_column(Boolean)
    amount_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    product_amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    product_order: Mapped[bool | None] = mapped_column(Boolean)
    cash_amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    funding_source: Mapped[str | None] = mapped_column(String(48))
    sale_mode: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8))
    currency_scale: Mapped[int] = mapped_column(Integer, default=2)


class AdPromoBinding(Base):
    __tablename__ = "ad_promo_bindings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.ad_campaign_id"), index=True)
    link_id: Mapped[int | None] = mapped_column(ForeignKey("ad_links.id"))
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.promo_code_id"), index=True)
    code_snapshot: Mapped[str] = mapped_column(String(256), default="")
    effects_json: Mapped[str] = mapped_column(Text, default="{}")
    purpose: Mapped[str] = mapped_column(String(24), default="offer")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)


class AdSpendEntry(Base):
    __tablename__ = "ad_spend_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.ad_campaign_id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8))
    currency_scale: Mapped[int] = mapped_column(Integer, default=2)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(24), default="manual")
    note: Mapped[str] = mapped_column(String(256), default="")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdImportBatch(Base):
    __tablename__ = "ad_import_batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.ad_campaign_id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    file_hash: Mapped[str] = mapped_column(String(64))
    account: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64))
    adapter_version: Mapped[str] = mapped_column(String(32), default="mapped_aggregate_v1")
    status: Mapped[str] = mapped_column(String(24), default="preview")
    rows_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdExternalMetric(Base):
    __tablename__ = "ad_external_metrics"
    __table_args__ = (
        Index(
            "uq_ad_external_current",
            "logical_key",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("ad_import_batches.id"), index=True)
    logical_key: Mapped[str] = mapped_column(String(64), index=True)
    account: Mapped[str] = mapped_column(String(128))
    advertisement: Mapped[str] = mapped_column(String(128))
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    granularity: Mapped[str] = mapped_column(String(16))
    impressions: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    starts: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(8))
    currency_scale: Mapped[int] = mapped_column(Integer, default=2)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AdMatchCandidate(Base):
    __tablename__ = "ad_match_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("ad_import_batches.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(160))
    touchpoint_id: Mapped[int | None] = mapped_column(ForeignKey("ad_touchpoints.id"))
    status: Mapped[str] = mapped_column(String(24), default="unmatched")
    delta_seconds: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(256))
    method_version: Mapped[str] = mapped_column(String(32), default="operator_time_v1")
    window_seconds: Mapped[int] = mapped_column(Integer, default=30)
    bot_id: Mapped[str] = mapped_column(String(64), default="")
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdUtmRule(Base):
    __tablename__ = "ad_utm_rules"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.ad_campaign_id"), index=True)
    utm_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdAudit(Base):
    __tablename__ = "ad_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_campaigns.ad_campaign_id"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[int] = mapped_column(BigInteger)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdAuthContext(Base):
    __tablename__ = "ad_auth_contexts"
    operation_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    visit_id: Mapped[str] = mapped_column(ForeignKey("ad_visits.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AdOfferActivation(Base):
    __tablename__ = "ad_offer_activations"
    activation_id: Mapped[int] = mapped_column(
        ForeignKey("promo_code_activations.activation_id"), primary_key=True
    )
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.ad_campaign_id"), index=True)
    binding_id: Mapped[int] = mapped_column(ForeignKey("ad_promo_bindings.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), index=True)
    original_user_id: Mapped[int] = mapped_column(BigInteger)
    evidence: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
