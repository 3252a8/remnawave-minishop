from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class PartnerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PartnerApplicationOut(PartnerModel):
    application_id: int
    user_id: int | None = None
    display_label: str
    message: str | None = None
    status: str
    submitted_at: datetime
    decided_at: datetime | None = None
    decision_message: str | None = None
    approved_commission_bps: int | None = None
    welcome_message: str | None = None
    reapply_allowed_at: datetime | None = None


class AdminPartnerApplicationOut(PartnerApplicationOut):
    username: str | None = None
    avatar_url: str | None = None


class PartnerProfileOut(PartnerModel):
    partner_id: int
    user_id: int | None = None
    display_label: str
    username: str | None = None
    avatar_url: str | None = None
    status: str
    commission_bps: int
    welcome_message: str | None = None
    pause_reason: str | None = None
    activated_at: datetime
    created_at: datetime


class PartnerBalanceOut(PartnerModel):
    currency: str
    currency_scale: int
    available_minor: int
    pending_minor: int
    reserved_minor: int
    lifetime_earned_minor: int


class PartnerLinksOut(PartnerModel):
    telegram: str | None = None
    web: str | None = None
    telegram_enabled: bool
    web_enabled: bool


class PartnerWithdrawalMethodOut(PartnerModel):
    id: str
    type: str
    enabled: bool
    label: str
    debit_currency: str
    currency_scale: int
    min_amount_minor: int
    max_amount_minor: int | None = None
    fields: list[dict[str, Any]]
    settlement_asset: str | None = None
    networks: list[dict[str, str]]
    sort_order: int
    help_text: str


class PartnerOverviewOut(PartnerModel):
    program_enabled: bool
    withdrawals_enabled: bool
    balance_payment_enabled: bool
    encryption_available: bool
    application_message_max_length: int
    application: PartnerApplicationOut | None = None
    profile: PartnerProfileOut | None = None
    balances: list[PartnerBalanceOut]
    links: PartnerLinksOut | None = None
    withdrawal_methods: list[PartnerWithdrawalMethodOut]


class PartnerClientOut(PartnerModel):
    partner_client_id: int
    public_client_id: str
    label: str
    source: str
    attributed_at: datetime
    eligible_from: datetime
    payments_count: int
    gross_minor: int
    currency: str | None = None
    currency_scale: int


class PartnerCommissionOut(PartnerModel):
    commission_id: int
    payment_id: int | None = None
    client_public_id: str
    client_label: str
    gross_amount_minor: int
    commission_amount_minor: int
    currency: str
    currency_scale: int
    commission_bps: int
    sale_mode: str | None = None
    provider: str | None = None
    status: str
    exclusion_reason: str | None = None
    source_paid_at: datetime
    available_at: datetime
    created_at: datetime
    reversed_at: datetime | None = None


class PartnerWithdrawalOut(PartnerModel):
    withdrawal_id: int
    partner_id: int
    method_id: str
    method_type: str
    method_snapshot: dict[str, Any]
    amount_minor: int
    currency: str
    currency_scale: int
    settlement_asset: str | None = None
    network: str | None = None
    status: str
    status_version: int
    status_message: str | None = None
    external_reference: str | None = None
    settlement_amount: str | None = None
    masked_requisites: str
    requested_at: datetime
    processing_at: datetime | None = None
    paid_at: datetime | None = None
    decided_at: datetime | None = None


class AdminPartnerWithdrawalOut(PartnerWithdrawalOut):
    user_id: int | None = None
    display_label: str | None = None
    username: str | None = None
    avatar_url: str | None = None


class PartnerApplicationCreateIn(PartnerModel):
    message: str = Field(min_length=10, max_length=10000)


class PartnerWithdrawalCreateIn(PartnerModel):
    method_id: str = Field(min_length=1, max_length=64)
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=2, max_length=16)
    requisites: dict[str, str]
    network: str | None = Field(default=None, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)


class PartnerBalanceRenewIn(PartnerModel):
    tariff_key: str = Field(min_length=1, max_length=128)
    months: int | None = Field(default=None, ge=1, le=60)
    duration_days: int | None = Field(default=None, gt=0, le=2147483647, strict=True)
    promo_code: str | None = Field(default=None, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)


class AdminPartnerCreateIn(PartnerModel):
    user_id: int
    commission_bps: int | None = Field(default=None, ge=0, le=10000)
    welcome_message: str | None = Field(default=None, max_length=2000)


class AdminPartnerApplicationDecisionIn(PartnerModel):
    decision_message: str | None = Field(default=None, max_length=2000)
    commission_bps: int | None = Field(default=None, ge=0, le=10000)
    welcome_message: str | None = Field(default=None, max_length=2000)


class AdminPartnerRateIn(PartnerModel):
    commission_bps: int = Field(ge=0, le=10000)
    reason: str = Field(min_length=1, max_length=2000)


class AdminPartnerBalanceAdjustmentIn(PartnerModel):
    currency: str = Field(min_length=2, max_length=16)
    currency_scale: int = Field(ge=0, le=8)
    mode: Literal["add", "subtract", "set"]
    amount_minor: int
    reason: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    allow_negative: bool = False
    internal_reference: str | None = Field(default=None, max_length=128)


class AdminPartnerStatusIn(PartnerModel):
    reason: str | None = Field(default=None, max_length=2000)


class AdminPartnerReferralImportIn(PartnerModel):
    confirm_without_retroactive_commission: bool


class AdminPartnerReferralImportPreviewOut(PartnerModel):
    found: int
    importable: int
    already_this_partner: int
    other_partner: int
    self_conflict: int
    historical_payments: int


class AdminPartnerReferralImportResultOut(PartnerModel):
    imported: int
    existing: int
    conflicts: int


class AdminPartnerBulkReferralImportPreviewOut(AdminPartnerReferralImportPreviewOut):
    partners: int


class AdminPartnerBulkReferralImportResultOut(AdminPartnerReferralImportResultOut):
    partners_updated: int


class AdminPartnerRequisitesOut(RootModel[dict[str, str]]):
    pass


class AdminPartnerWithdrawalTransitionIn(PartnerModel):
    status_version: int = Field(ge=1)
    message: str | None = Field(default=None, max_length=2000)
    external_reference: str | None = Field(default=None, max_length=255)
    settlement_amount: str | None = Field(default=None, max_length=64)


class AdminPartnerOverviewMetricsOut(PartnerModel):
    active_partners: int
    paused_partners: int
    clients: int
    gross_minor: int
    commissions_minor: int
    pending_minor: int
    available_minor: int
    paid_minor: int
    requested_minor: int


class AdminPartnerOverviewPointOut(PartnerModel):
    date: str
    gross_minor: int
    commission_minor: int
    paid_minor: int
