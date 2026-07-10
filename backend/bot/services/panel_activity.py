from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import subscription_dal
from db.models import Subscription

_PANEL_LAST_CONNECTED_KEYS = (
    "onlineAt",
    "online_at",
    "lastSeenAt",
    "last_seen_at",
    "lastConnectedAt",
    "last_connected_at",
    "lastConnectionAt",
    "last_connection_at",
)
_PANEL_CONNECTION_MARKER_KEYS = (
    *_PANEL_LAST_CONNECTED_KEYS,
    "firstConnectedAt",
    "first_connected_at",
    "lastConnectedNodeUuid",
    "last_connected_node_uuid",
)
_PANEL_CONNECTION_MARKER_OBJECT_KEYS = ("lastConnectedNode", "last_connected_node")
_PANEL_TRAFFIC_OBJECT_KEYS = ("userTraffic", "user_traffic", "traffic", "trafficStats")
_PANEL_TRAFFIC_USED_KEYS = (
    "lifetimeUsedTrafficBytes",
    "lifetime_used_traffic_bytes",
    "usedTrafficBytes",
    "used_traffic_bytes",
    "trafficUsedBytes",
    "traffic_used_bytes",
    "downloadBytes",
    "download_bytes",
    "uploadBytes",
    "upload_bytes",
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _panel_user_payload(panel_user_data: Any) -> dict[str, Any]:
    if not isinstance(panel_user_data, dict):
        return {}
    response = panel_user_data.get("response")
    if isinstance(response, dict) and not any(
        key in panel_user_data
        for key in ("uuid", "shortUuid", "subscriptionUrl", "userTraffic", "status")
    ):
        return response
    return panel_user_data


def _coerce_panel_datetime(value: Any) -> str | None:
    if value is None or value is False:
        return None
    if isinstance(value, datetime):
        utc_value = _as_utc(value)
        return utc_value.isoformat() if utc_value else None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        seconds = float(value) / 1000.0 if value > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text or text.lower() in {"0", "null", "none", "never"}:
        return None
    if text.isdigit():
        return _coerce_panel_datetime(int(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    utc_value = _as_utc(parsed)
    return utc_value.isoformat() if utc_value else None


def _coerce_panel_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _panel_nested_dicts(panel_user: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in keys:
        value = panel_user.get(key)
        if isinstance(value, dict):
            out.append(value)
    return out


def _panel_user_connection_containers(panel_user: dict[str, Any]) -> list[dict[str, Any]]:
    traffic_containers = _panel_nested_dicts(panel_user, _PANEL_TRAFFIC_OBJECT_KEYS)
    marker_containers = _panel_nested_dicts(
        panel_user,
        _PANEL_CONNECTION_MARKER_OBJECT_KEYS,
    )
    for traffic_container in traffic_containers:
        marker_containers.extend(
            _panel_nested_dicts(traffic_container, _PANEL_CONNECTION_MARKER_OBJECT_KEYS)
        )
    return [panel_user, *traffic_containers, *marker_containers]


def _panel_user_last_connected_at(panel_user_data: Any) -> str | None:
    panel_user = _panel_user_payload(panel_user_data)
    if not panel_user:
        return None
    for container in _panel_user_connection_containers(panel_user):
        for key in _PANEL_LAST_CONNECTED_KEYS:
            connected_at = _coerce_panel_datetime(container.get(key))
            if connected_at:
                return connected_at
    return None


def panel_user_last_connected_datetime(panel_user_data: Any) -> datetime | None:
    connected_at = _panel_user_last_connected_at(panel_user_data)
    if not connected_at:
        return None
    try:
        parsed = datetime.fromisoformat(connected_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _panel_user_positive_traffic_bytes(panel_user: dict[str, Any]) -> bool:
    containers = [panel_user, *_panel_nested_dicts(panel_user, _PANEL_TRAFFIC_OBJECT_KEYS)]
    for container in containers:
        for key in _PANEL_TRAFFIC_USED_KEYS:
            value = _coerce_panel_int(container.get(key))
            if value is not None and value > 0:
                return True
    return False


def _panel_user_has_connection_marker(panel_user: dict[str, Any]) -> bool:
    for container in _panel_user_connection_containers(panel_user):
        for key in _PANEL_CONNECTION_MARKER_KEYS:
            if key in container:
                return True
    for container in [panel_user, *_panel_nested_dicts(panel_user, _PANEL_TRAFFIC_OBJECT_KEYS)]:
        for key in _PANEL_CONNECTION_MARKER_OBJECT_KEYS:
            if key in container:
                return True
    return False


def _panel_user_has_connected_marker_value(panel_user: dict[str, Any]) -> bool:
    for container in _panel_user_connection_containers(panel_user):
        for key in (*_PANEL_LAST_CONNECTED_KEYS, "firstConnectedAt", "first_connected_at"):
            if _coerce_panel_datetime(container.get(key)):
                return True
        for key in ("lastConnectedNodeUuid", "last_connected_node_uuid"):
            if str(container.get(key) or "").strip():
                return True
    for container in [panel_user, *_panel_nested_dicts(panel_user, _PANEL_TRAFFIC_OBJECT_KEYS)]:
        for key in _PANEL_CONNECTION_MARKER_OBJECT_KEYS:
            marker = container.get(key)
            if isinstance(marker, dict) and any(
                str(value or "").strip() for value in marker.values()
            ):
                return True
            if marker and not isinstance(marker, dict):
                return True
    return False


def _panel_user_connection_activity(panel_user_data: Any) -> dict[str, Any]:
    panel_user = _panel_user_payload(panel_user_data)
    last_connected_at = _panel_user_last_connected_at(panel_user)
    if not panel_user:
        return {"status": "unknown", "last_connected_at": None}
    if last_connected_at or _panel_user_positive_traffic_bytes(panel_user):
        return {"status": "connected", "last_connected_at": last_connected_at}
    if _panel_user_has_connected_marker_value(panel_user):
        return {"status": "connected", "last_connected_at": last_connected_at}
    if _panel_user_has_connection_marker(panel_user):
        return {"status": "never", "last_connected_at": None}
    return {"status": "unknown", "last_connected_at": None}


def connection_activity_from_snapshot(last_connected_at: datetime | None) -> dict[str, Any]:
    connected_at = _as_utc(last_connected_at)
    if connected_at is None:
        return {"status": "unknown", "last_connected_at": None}
    return {"status": "connected", "last_connected_at": connected_at.isoformat()}


async def record_subscription_panel_activity(
    session: AsyncSession,
    subscription: Subscription,
    panel_user_data: Any,
) -> datetime | None:
    connected_at = panel_user_last_connected_datetime(panel_user_data)
    if connected_at is None:
        return None
    current = _as_utc(getattr(subscription, "last_connected_at", None))
    if current is not None and current >= connected_at:
        return current
    subscription_id = getattr(subscription, "subscription_id", None)
    if subscription_id is None:
        return connected_at
    await subscription_dal.update_subscription_last_connected_at(
        session,
        int(subscription_id),
        connected_at,
    )
    subscription.last_connected_at = connected_at
    return connected_at
