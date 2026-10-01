"""Typed advertising management and reporting contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BeforeValidator,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.services.advertising.validation import landing_path, money, normalize_utm

from .activity_schemas import AdOut

MinorAmount = Annotated[str, BeforeValidator(str), Field(pattern=r"^-?[0-9]+$")]


class AdReportQuery(HttpBodyModel):
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    period_mode: Literal["events", "cohort"] = "events"
    page: int = Field(0, ge=0)
    page_size: int = Field(25, ge=1, le=100)
    link_id: int | None = Field(None, ge=1)
    evidence: str | None = Field(None, max_length=32)
    channel: Literal["web", "bot", "telegram", "miniapp"] | None = None
    currency: str | None = Field(None, pattern=r"^[A-Z]{3,8}$")

    @model_validator(mode="after")
    def _period(self) -> AdReportQuery:
        if self.start and self.end and self.end <= self.start:
            raise ValueError("invalid_ad_period")
        return self


class AdListQuery(AdReportQuery):
    search: str = Field("", max_length=160)
    status: Literal["all", "active", "paused", "archived"] = "all"
    source: str = Field("", max_length=160)
    sort: str = Field(
        "id_desc",
        pattern=r"^(id|source|param|advertiser|cost|registrations|conversions|status)_(asc|desc)$",
    )


class AdEditBody(HttpBodyModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field("", max_length=4000)
    cost: float = Field(0, ge=0, le=100_000_000, allow_inf_nan=False)
    report_currency: str = Field("RUB", pattern=r"^[A-Z]{3,8}$")
    attribution_window_days: int = Field(30, ge=1, le=365)
    spend_source: Literal["legacy", "manual", "import"] = "legacy"


class AdLinkBody(HttpBodyModel):
    label: str = Field("", max_length=160)
    destination: Literal["web", "bot", "miniapp"] = "web"
    landing_path: str = "/"
    utm: dict[str, str] = Field(default_factory=dict)

    @field_validator("landing_path")
    @classmethod
    def _landing(cls, value: str) -> str:
        return landing_path(value)

    @field_validator("utm")
    @classmethod
    def _utm(cls, value: dict[str, str]) -> dict[str, str]:
        result = normalize_utm(value)
        if not result.get("utm_source"):
            raise ValueError("missing_utm_source")
        return result


class AdLinkOut(HttpResponseModel):
    id: int
    code: str
    label: str
    destination: str
    landing_path: str
    utm: dict[str, str]
    urls: dict[str, str]
    is_active: bool


class AdBindingBody(HttpBodyModel):
    promo_code_id: int = Field(ge=1)
    link_id: int | None = Field(None, ge=1)
    purpose: Literal["offer", "manual_code_source"] = "offer"


class AdBindingOut(HttpResponseModel):
    id: int
    promo_code_id: int
    code: str
    link_id: int | None = None
    purpose: str
    starts_at: datetime
    ends_at: datetime | None = None
    version: int
    is_active: bool
    activations: int = 0
    purchases: int = 0
    pending: int = 0
    refunded: int = 0
    effects: dict[str, Any] = Field(default_factory=dict)


class AdSpendBody(HttpBodyModel):
    amount: str
    currency: str = Field("RUB", pattern=r"^[A-Z]{3,8}$")
    occurred_at: AwareDatetime
    note: str = Field("", max_length=256)

    @field_validator("amount")
    @classmethod
    def _money(cls, value: str) -> str:
        return str(money(value))


class AdSpendOut(HttpResponseModel):
    id: int
    amount_minor: MinorAmount
    currency: str
    scale: int
    occurred_at: datetime
    source: str
    note: str


class AdMoneyOut(HttpResponseModel):
    currency: str
    scale: int
    cash_minor: MinorAmount
    product_minor: MinorAmount
    refund_minor: MinorAmount
    net_minor: MinorAmount
    first_purchase_minor: MinorAmount
    repeat_purchase_minor: MinorAmount
    spend_minor: MinorAmount | None
    purchases: int
    roas: float | None = None
    cac_minor: float | None = None
    average_order_minor: float | None = None
    d7_minor: MinorAmount
    d30_minor: MinorAmount
    d90_minor: MinorAmount


class AdvertisingReportOut(HttpResponseModel):
    contacts: int
    attributed_users: int
    registrations: int
    returning_users: int
    trials: int
    payers: int
    first_payers: int
    purchases: int
    currencies: list[AdMoneyOut]
    platform: dict[str, int | None]
    ctr: float | None = None
    registration_conversion: float | None = None
    legacy_payment_count: int
    period_mode: str
    mature_cohorts: dict[str, int]


class AdTouchOut(HttpResponseModel):
    id: int
    user_id: int | None = None
    original_user_id: int | None = None
    channel: str
    evidence: str
    occurred_at: datetime
    received_at: datetime
    is_new_user: bool | None = None
    utm: dict[str, str]


class AdImportPreviewBody(HttpBodyModel):
    csv: str = Field(max_length=1_048_576)
    mapping: dict[str, str]
    timezone: str = Field(min_length=1, max_length=64)
    account: str = Field(min_length=1, max_length=128)
    granularity: Literal["daily", "minute", "interval", "cumulative", "event"] = "daily"
    currency: str | None = Field(None, pattern=r"^[A-Z]{3,8}$")
    delimiter: Literal[",", ";", "\t"] = ","


class AdImportConfirmBody(HttpBodyModel):
    replace: StrictBool = False


class AdCandidatesBody(HttpBodyModel):
    bot_id: str = Field(min_length=1, max_length=64)
    window_seconds: int = Field(ge=1, le=3600)


class AdCandidateDecisionBody(HttpBodyModel):
    status: Literal["confirmed_by_operator", "rejected"]


class AdImportOut(HttpResponseModel):
    id: str
    status: str
    account: str
    timezone: str
    fingerprint: str
    rows: int
    granularity: str
    created_at: datetime


class AdCandidateOut(HttpResponseModel):
    id: int
    batch_id: str
    touchpoint_id: int | None = None
    status: str
    delta_seconds: int | None = None
    reason: str
    window_seconds: int
    bot_id: str
    method_version: str


class AdAuditOut(HttpResponseModel):
    id: int
    action: str
    actor_id: int
    created_at: datetime


class AdDetailOut(HttpResponseModel):
    campaign: AdOut
    name: str
    description: str
    archived_at: datetime | None = None
    report_currency: str
    attribution_window_days: int
    spend_source: str
    report: AdvertisingReportOut
    links: list[AdLinkOut]
    bindings: list[AdBindingOut]
    spends: list[AdSpendOut]
    touches: list[AdTouchOut]
    touch_total: int
    imports: list[AdImportOut]
    candidates: list[AdCandidateOut]
    audit: list[AdAuditOut]
    available_codes: dict[str, int]
    legacy_urls: dict[str, str] = Field(default_factory=dict)
    legacy_warning: str | None = None


class AdUnassignedBody(HttpBodyModel):
    campaign_id: int = Field(ge=1)
    utm: dict[str, str]


class AdUnassignedOut(HttpResponseModel):
    touches: list[AdTouchOut]
    total: int = 0
    campaigns: dict[str, str] = Field(default_factory=dict)


class AdImportPreviewOut(HttpResponseModel):
    batch: AdImportOut
    preview: list[dict[str, Any]]
