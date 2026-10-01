from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel

from .schema_helpers import display_label as _display_label


class AdStatsOut(HttpResponseModel):
    starts: int = 0
    trials: int = 0
    payers: int = 0
    revenue: float = 0.0


class AdOut(HttpResponseModel):
    id: int
    source: str | None = None
    start_param: str | None = None
    cost: float
    is_active: bool
    created_at: datetime | None = None
    advertiser_id: int | None = None
    stats_reset_at: datetime | None = None
    stats: AdStatsOut = Field(default_factory=AdStatsOut)

    @classmethod
    def from_orm_ad(cls, campaign: Any, totals: dict[str, Any] | None = None) -> AdOut:
        return cls(
            id=int(campaign.ad_campaign_id),
            source=campaign.source,
            start_param=campaign.start_param,
            cost=float(campaign.cost or 0),
            is_active=bool(campaign.is_active),
            created_at=campaign.created_at,
            advertiser_id=int(campaign.advertiser_id)
            if getattr(campaign, "advertiser_id", None) is not None
            else None,
            stats_reset_at=getattr(campaign, "stats_reset_at", None),
            stats=AdStatsOut.model_validate(totals or {}),
        )


class AdminAdsListOut(HttpResponseModel):
    campaigns: list[AdOut]
    totals: dict[str, float]


class AdCreateBody(HttpBodyModel):
    source: str
    start_param: str
    cost: float = 0.0
    advertiser_id: int | None = None

    @field_validator("source", "start_param", mode="before")
    @classmethod
    def _strip_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("empty")
        return text

    @field_validator("cost", mode="before")
    @classmethod
    def _coerce_cost(cls, value: Any) -> float:
        return float(value or 0.0)

    @field_validator("advertiser_id", mode="before")
    @classmethod
    def _coerce_advertiser_id(cls, value: Any) -> int | None:
        if value is None or value == "" or value == 0:
            return None
        return int(value)


class AdAssignBody(HttpBodyModel):
    advertiser_id: int | None = None

    @field_validator("advertiser_id", mode="before")
    @classmethod
    def _coerce_advertiser_id(cls, value: Any) -> int | None:
        if value is None or value == "" or value == 0:
            return None
        return int(value)


class AdPurchaseItem(HttpResponseModel):
    payment_id: int
    user_id: int
    username: str | None = None
    amount: float
    currency: str
    description: str | None = None
    created_at: datetime | None = None


class AdPurchasesListOut(HttpResponseModel):
    purchases: list[AdPurchaseItem]


class AdToggleBody(HttpBodyModel):
    is_active: Any = True


class LogOut(HttpResponseModel):
    log_id: int
    user_id: int | None = None
    user_label: str | None = None
    telegram_username: str | None = None
    telegram_first_name: str | None = None
    email: str | None = None
    event_type: str | None = None
    content: str | None = None
    is_admin_event: bool
    target_user_id: int | None = None
    target_user_label: str | None = None
    timestamp: datetime | None = None

    @classmethod
    def from_orm_log(cls, entry: Any) -> LogOut:
        author_user = entry.__dict__.get("author_user")
        target_user = entry.__dict__.get("target_user")
        user_id = int(entry.user_id) if entry.user_id is not None else None
        target_user_id = int(entry.target_user_id) if entry.target_user_id is not None else None
        return cls(
            log_id=int(entry.log_id),
            user_id=user_id,
            user_label=_display_label(
                author_user,
                user_id,
                first_name=entry.telegram_first_name,
                username=entry.telegram_username,
            ),
            telegram_username=entry.telegram_username,
            telegram_first_name=entry.telegram_first_name,
            email=getattr(author_user, "email", None),
            event_type=entry.event_type,
            content=entry.content,
            is_admin_event=bool(entry.is_admin_event),
            target_user_id=target_user_id,
            target_user_label=_display_label(target_user, target_user_id),
            timestamp=entry.timestamp,
        )


class AdminLogsListOut(HttpResponseModel):
    logs: list[LogOut]
    page: int
    page_size: int
    total: int
