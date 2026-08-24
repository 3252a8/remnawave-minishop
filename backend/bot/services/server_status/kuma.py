from __future__ import annotations

from collections.abc import Mapping

from .models import (
    ItemStatus,
    OverallStatus,
    ProviderStatus,
    StatusGroup,
    StatusIncident,
    StatusItem,
)
from .parsing import finite_number, object_dict, object_list, parse_datetime, plain_text


def _item_status(value: object) -> ItemStatus:
    normalized = str(value).strip().lower()
    statuses: dict[str, ItemStatus] = {
        "0": "offline",
        "1": "online",
        "2": "pending",
        "3": "maintenance",
        "down": "offline",
        "up": "online",
        "pending": "pending",
        "maintenance": "maintenance",
        "degraded": "degraded",
    }
    return statuses.get(normalized, "unknown")


def _incident_status(incident: Mapping[str, object]) -> OverallStatus:
    value = str(incident.get("status") or incident.get("style") or "").strip().lower()
    if value in {"resolved", "completed", "operational", "success"}:
        return "operational"
    if value in {"maintenance", "info", "primary"}:
        return "maintenance"
    if value in {"major_outage", "danger", "critical"}:
        return "major_outage"
    if value in {"partial_outage", "warning", "degraded", "active", "investigating"}:
        return "degraded"
    return "unknown"


def _overall_status(groups: list[StatusGroup], incidents: list[StatusIncident]) -> OverallStatus:
    items = [item for group in groups for item in group.items]
    active_incidents = [
        incident.status for incident in incidents if incident.status != "operational"
    ]
    if "major_outage" in active_incidents:
        return "major_outage"
    if items and all(item.status == "offline" for item in items):
        return "major_outage"
    if any(item.status == "offline" for item in items):
        return "partial_outage"
    if active_incidents or any(item.status == "degraded" for item in items):
        return "degraded"
    if any(item.status == "maintenance" for item in items):
        return "maintenance"
    if any(item.status == "online" for item in items):
        return "operational"
    return "unknown"


def _uptime(uptime_list: Mapping[str, object], monitor_id: str) -> float | None:
    raw_value: object = None
    for key in (f"{monitor_id}_24", f"{monitor_id}_24h", monitor_id):
        if key in uptime_list:
            raw_value = uptime_list[key]
            break
    value = finite_number(raw_value)
    if value is None:
        return None
    return round(value * 100 if 0 <= value <= 1 else value, 4)


def parse_kuma_status_page(
    page_payload: object,
    heartbeat_payload: object,
) -> ProviderStatus:
    page = object_dict(page_payload)
    heartbeats = object_dict(heartbeat_payload)
    if page is None or heartbeats is None:
        raise ValueError("invalid Kuma response")

    heartbeat_list = object_dict(heartbeats.get("heartbeatList")) or {}
    uptime_list = object_dict(heartbeats.get("uptimeList")) or {}
    groups: list[StatusGroup] = []
    raw_groups = page.get("publicGroupList", page.get("groups", []))
    for group_index, group in enumerate(object_list(raw_groups)):
        items: list[StatusItem] = []
        raw_monitors = group.get("monitorList", group.get("monitors", []))
        for monitor in object_list(raw_monitors):
            monitor_id = str(monitor.get("id") or "").strip()
            if not monitor_id:
                continue
            history = object_list(heartbeat_list.get(monitor_id, []))
            heartbeat = history[-1] if history else {}
            items.append(
                StatusItem(
                    id=f"kuma:{monitor_id}",
                    name=plain_text(monitor.get("name")) or monitor_id,
                    status=_item_status(heartbeat.get("status")),
                    latency_ms=finite_number(heartbeat.get("ping")),
                    uptime_24h=_uptime(uptime_list, monitor_id),
                    last_check=parse_datetime(heartbeat.get("time")),
                    provider="uptime-kuma",
                )
            )
        group_id = str(group.get("id") or group_index)
        groups.append(
            StatusGroup(
                id=f"kuma:{group_id}",
                name=plain_text(group.get("name")) or "Servers",
                items=items,
            )
        )

    incidents: list[StatusIncident] = []
    raw_incidents: list[dict[str, object]] = []
    raw_incidents.extend(object_list(page.get("incident")))
    raw_incidents.extend(object_list(page.get("incidents")))
    seen_incidents: set[tuple[str, str]] = set()
    for incident in raw_incidents:
        title = plain_text(incident.get("title"))
        content = plain_text(incident.get("content"))
        identity = (title, str(incident.get("createdDate") or incident.get("createdAt") or ""))
        if identity in seen_incidents:
            continue
        seen_incidents.add(identity)
        incidents.append(
            StatusIncident(
                title=title or "Incident",
                content=content,
                status=_incident_status(incident),
                created_at=parse_datetime(incident.get("createdDate") or incident.get("createdAt")),
                provider="uptime-kuma",
            )
        )

    return ProviderStatus(
        provider="uptime-kuma",
        status=_overall_status(groups, incidents),
        groups=groups,
        incidents=incidents,
    )
