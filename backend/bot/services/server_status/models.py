from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from bot.app.web.http_contracts import HttpResponseModel

type OverallStatus = Literal[
    "operational",
    "degraded",
    "partial_outage",
    "major_outage",
    "maintenance",
    "unknown",
]
type ItemStatus = Literal["online", "offline", "degraded", "maintenance", "pending", "unknown"]
type StatusProvider = Literal["url", "uptime-kuma", "xray-checker"]
type NativeStatusProvider = Literal["uptime-kuma", "xray-checker"]


class StatusModel(HttpResponseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class StatusSource(StatusModel):
    provider: StatusProvider
    status: OverallStatus
    error: str | None = None


class StatusItem(StatusModel):
    id: str
    name: str
    status: ItemStatus
    latency_ms: float | None = Field(default=None, alias="latencyMs")
    uptime_24h: float | None = Field(default=None, alias="uptime24h")
    last_check: datetime | None = Field(default=None, alias="lastCheck")
    provider: NativeStatusProvider


class StatusGroup(StatusModel):
    id: str
    name: str
    items: list[StatusItem]


class StatusIncident(StatusModel):
    title: str
    content: str
    status: OverallStatus
    created_at: datetime | None = Field(default=None, alias="createdAt")
    provider: NativeStatusProvider


class ProviderStatus(StatusModel):
    provider: NativeStatusProvider
    status: OverallStatus
    groups: list[StatusGroup] = Field(default_factory=list)
    incidents: list[StatusIncident] = Field(default_factory=list)


class ServerStatus(StatusModel):
    enabled: bool
    status: OverallStatus
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    stale: bool = False
    external_url: str | None = Field(default=None, alias="externalUrl")
    sources: list[StatusSource] = Field(default_factory=list)
    groups: list[StatusGroup] = Field(default_factory=list)
    incidents: list[StatusIncident] = Field(default_factory=list)
