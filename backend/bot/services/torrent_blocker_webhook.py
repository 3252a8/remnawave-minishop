from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

TORRENT_BLOCKER_EVENT = "torrent_blocker.report"
TORRENT_BLOCKER_SCOPE = "torrent_blocker"
MAX_TORRENT_BLOCKER_DURATION_SECONDS = 365 * 24 * 60 * 60


def _utc_isoformat(value: datetime) -> str:
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


class TorrentBlockerActionReportPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    blocked: StrictBool
    ip: StrictStr
    block_duration: StrictInt = Field(
        alias="blockDuration",
        ge=0,
        le=MAX_TORRENT_BLOCKER_DURATION_SECONDS,
    )
    will_unblock_at: AwareDatetime = Field(alias="willUnblockAt")
    user_id: StrictStr = Field(alias="userId")
    processed_at: AwareDatetime = Field(alias="processedAt")

    def notification_context(self, *, event_timestamp: datetime) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "ip": self.ip,
            "block_duration": self.block_duration,
            "will_unblock_at": _utc_isoformat(self.will_unblock_at),
            "processed_at": _utc_isoformat(self.processed_at),
            "event_timestamp": _utc_isoformat(event_timestamp),
        }


class TorrentBlockerReportPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_report: TorrentBlockerActionReportPayload = Field(alias="actionReport")
    xray_report: dict[str, Any] = Field(alias="xrayReport")


class TorrentBlockerWebhookData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node: dict[str, Any]
    user: dict[str, Any]
    report: TorrentBlockerReportPayload


class TorrentBlockerWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scope: Literal["torrent_blocker"]
    event: Literal["torrent_blocker.report"]
    timestamp: AwareDatetime
    data: TorrentBlockerWebhookData

    def sanitized_user_payload(self) -> dict[str, Any]:
        allowed_keys = (
            "uuid",
            "userUuid",
            "shortUuid",
            "telegramId",
            "email",
        )
        return {key: self.data.user[key] for key in allowed_keys if key in self.data.user}

    def notification_context(self) -> dict[str, Any]:
        return self.data.report.action_report.notification_context(
            event_timestamp=self.timestamp,
        )
