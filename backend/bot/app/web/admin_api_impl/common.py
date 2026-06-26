import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from aiohttp import web
from schemas import AdminSubscriptionOut, AdminUserOut, AdOut, LogOut, PaymentOut

from config.settings import Settings
from config.tariffs_config import TariffsConfig
from db.models import AdCampaign, MessageLog, Payment, PromoCode, Subscription, User


def _ok(payload: Dict[str, Any], **extra: Any) -> web.Response:
    body = {"ok": True, **payload, **extra}
    return web.json_response(body)


def _error(status: int, code: str, message: str = "") -> web.Response:
    return web.json_response(
        {"ok": False, "error": code, "message": message or code},
        status=status,
    )


def _error_payload(
    status: int,
    code: str,
    *,
    errors: Dict[str, Any] | None = None,
    message: str = "",
) -> web.Response:
    body: Dict[str, Any] = {"ok": False, "error": code}
    if message:
        body["message"] = message
    if errors:
        body["errors"] = errors
    return web.json_response(body, status=status)


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


def _panel_user_payload(panel_user_data: Any) -> Dict[str, Any]:
    if not isinstance(panel_user_data, dict):
        return {}
    response = panel_user_data.get("response")
    if isinstance(response, dict) and not any(
        key in panel_user_data
        for key in ("uuid", "shortUuid", "subscriptionUrl", "userTraffic", "status")
    ):
        return response
    return panel_user_data


def _coerce_panel_datetime(value: Any) -> Optional[str]:
    if value is None or value is False:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        seconds = float(value) / 1000.0 if value > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
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
    return parsed.isoformat()


def _coerce_panel_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _panel_nested_dicts(panel_user: Dict[str, Any], keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in keys:
        value = panel_user.get(key)
        if isinstance(value, dict):
            out.append(value)
    return out


def _panel_user_connection_containers(panel_user: Dict[str, Any]) -> List[Dict[str, Any]]:
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


def _panel_user_last_connected_at(panel_user_data: Any) -> Optional[str]:
    panel_user = _panel_user_payload(panel_user_data)
    if not panel_user:
        return None
    for container in _panel_user_connection_containers(panel_user):
        for key in _PANEL_LAST_CONNECTED_KEYS:
            connected_at = _coerce_panel_datetime(container.get(key))
            if connected_at:
                return connected_at
    return None


def _panel_user_positive_traffic_bytes(panel_user: Dict[str, Any]) -> bool:
    containers = [panel_user, *_panel_nested_dicts(panel_user, _PANEL_TRAFFIC_OBJECT_KEYS)]
    for container in containers:
        for key in _PANEL_TRAFFIC_USED_KEYS:
            value = _coerce_panel_int(container.get(key))
            if value is not None and value > 0:
                return True
    return False


def _panel_user_has_connection_marker(panel_user: Dict[str, Any]) -> bool:
    for container in _panel_user_connection_containers(panel_user):
        for key in _PANEL_CONNECTION_MARKER_KEYS:
            if key in container:
                return True
    for container in [panel_user, *_panel_nested_dicts(panel_user, _PANEL_TRAFFIC_OBJECT_KEYS)]:
        for key in _PANEL_CONNECTION_MARKER_OBJECT_KEYS:
            if key in container:
                return True
    return False


def _panel_user_has_connected_marker_value(panel_user: Dict[str, Any]) -> bool:
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


def _panel_user_connection_activity(panel_user_data: Any) -> Dict[str, Any]:
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


def _serialize_user(user: User) -> Dict[str, Any]:
    return cast(Dict[str, Any], AdminUserOut.from_orm_user(user).model_dump(mode="json"))


def _premium_limit_bytes_from_subscription(sub: Subscription) -> int:
    premium_bonus_bytes = int(getattr(sub, "premium_bonus_bytes", 0) or 0)
    return (
        int(sub.premium_baseline_bytes or 0)
        + int(sub.premium_topup_balance_bytes or 0)
        + int(getattr(sub, "premium_topup_used_bytes", 0) or 0)
        + premium_bonus_bytes
    )


def _premium_traffic_list_payload(sub: Optional[Subscription]) -> Dict[str, Any]:
    """Premium traffic column when subscription has a finite premium quota (bytes > 0).

    Note: ``Subscription.premium_is_limited`` in the DB means *quota exhausted* for panel
    routing, not 'tariff includes premium traffic' — do not use it here.
    """

    if sub is None:
        return {"state": "none"}
    if bool(getattr(sub, "premium_unlimited_override", False)):
        return {
            "state": "unlimited",
            "unlimited": True,
            "used_bytes": int(sub.premium_used_bytes or 0),
            "limit_bytes": None,
            "percent": None,
        }
    limit_bytes = _premium_limit_bytes_from_subscription(sub)
    if limit_bytes <= 0:
        return {"state": "none"}
    used_bytes = int(sub.premium_used_bytes or 0)
    ratio = float(used_bytes) / float(limit_bytes) if limit_bytes else 0.0
    pct = int(max(0, min(100, round(ratio * 100))))
    if ratio >= 1.0:
        state = "critical"
    elif ratio >= 0.85:
        state = "warn"
    else:
        state = "good"
    return {
        "state": state,
        "unlimited": False,
        "used_bytes": used_bytes,
        "limit_bytes": limit_bytes,
        "percent": pct,
    }


def _serialize_subscription(sub: Subscription) -> Dict[str, Any]:
    return cast(
        Dict[str, Any],
        AdminSubscriptionOut.from_orm_subscription(sub).model_dump(mode="json"),
    )


def _payment_traffic_gb_split(payment: Payment) -> Tuple[Optional[float], Optional[float]]:
    """For traffic purchases: ``(regular_gb, premium_gb)``. Other payments → (None, None)."""
    if payment.purchased_gb is None:
        return None, None
    try:
        gb = float(payment.purchased_gb)
    except (TypeError, ValueError):
        return None, None
    sm = (payment.sale_mode or "").strip()
    if not sm:
        return None, None
    base = sm.split("@", 1)[0].split("|", 1)[0].lower()
    if base == "premium_topup":
        return None, gb
    if base in {"traffic", "traffic_package", "topup"}:
        return gb, None
    return None, None


def _user_display_label(
    loaded_user: Any,
    fallback_user_id: Optional[int],
    *,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[str]:
    """Human-facing name: TG profile name, else email, else user id."""
    tid = getattr(loaded_user, "telegram_id", None)
    if loaded_user is not None and tid is not None:
        fn = (getattr(loaded_user, "first_name", None) or "").strip()
        ln = (getattr(loaded_user, "last_name", None) or "").strip()
        full = f"{fn} {ln}".strip()
        if full:
            return full
        un = (getattr(loaded_user, "username", None) or "").strip()
        if un:
            return un if un.startswith("@") else f"@{un}"
    elif loaded_user is not None:
        email = (getattr(loaded_user, "email", None) or "").strip()
        if email:
            return email
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    full = f"{fn} {ln}".strip()
    if full:
        return full
    un = (username or "").strip()
    if un:
        return un if un.startswith("@") else f"@{un}"
    email_value = (email or "").strip()
    if email_value:
        return email_value
    if fallback_user_id is None:
        return None
    return str(fallback_user_id)


def _payment_user_display_label(loaded_user: Any, payment_user_id: int) -> str:
    label = _user_display_label(loaded_user, payment_user_id)
    if label:
        return label
    return str(payment_user_id)


def _serialize_payment(payment: Payment) -> Dict[str, Any]:
    return cast(Dict[str, Any], PaymentOut.from_orm_payment(payment).model_dump(mode="json"))


def _serialize_promo(promo: PromoCode) -> Dict[str, Any]:
    return {
        "id": int(promo.promo_code_id),
        "code": promo.code,
        "bonus_days": int(promo.bonus_days),
        "max_activations": int(promo.max_activations),
        "current_activations": int(promo.current_activations or 0),
        "is_active": bool(promo.is_active),
        "valid_until": promo.valid_until.isoformat() if promo.valid_until else None,
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
        "created_by_admin_id": int(promo.created_by_admin_id)
        if promo.created_by_admin_id
        else None,
    }


def _serialize_ad(campaign: AdCampaign, totals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return cast(Dict[str, Any], AdOut.from_orm_ad(campaign, totals).model_dump(mode="json"))


def _serialize_log(entry: MessageLog) -> Dict[str, Any]:
    return cast(Dict[str, Any], LogOut.from_orm_log(entry).model_dump(mode="json"))


def _tariffs_config_path(settings: Settings) -> Path:
    return Path(settings.TARIFFS_CONFIG_PATH).expanduser()


def _tariffs_config_payload(config: TariffsConfig) -> Dict[str, Any]:
    return cast(Dict[str, Any], config.model_dump(mode="json", exclude_none=True))


def _write_tariffs_config_file(path: Path, config: TariffsConfig) -> None:
    data = _tariffs_config_payload(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(path)
    except PermissionError:
        # A docker-compose single-file bind mount can make /app/config
        # unwritable while the mounted tariffs.json itself is writable.
        # Fall back to updating the existing file in-place.
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        path.write_text(payload, encoding="utf-8")


def _webapp_themes_catalog_payload(config: Any) -> Dict[str, Any]:
    return cast(Dict[str, Any], config.model_dump(mode="json", exclude_none=True))


def _panel_node_uuid_key(node: Dict[str, Any]) -> str:
    uid = node.get("nodeUuid") or node.get("node_uuid") or node.get("uuid") or node.get("id")
    return str(uid).strip().lower() if uid else ""


def _panel_node_users_online(node: Dict[str, Any]) -> Optional[int]:
    uo = node.get("usersOnline")
    if uo is None:
        uo = node.get("users_online")
    if uo is None:
        uo = node.get("onlineUsers") or node.get("online_users")
    if uo is None:
        mg = node.get("metricGroups")
        if isinstance(mg, dict):
            uo = mg.get("onlineUsers") or mg.get("online_users")
    if uo is None:
        return None
    try:
        return int(uo)
    except (TypeError, ValueError):
        return None


def _panel_nodes_online_by_uuid(nodes_payload: Any) -> Dict[str, int]:
    """Build node_uuid(lower) -> usersOnline from GET /system/stats/nodes payload."""
    out: Dict[str, int] = {}
    raw_list: Optional[List[Any]] = None
    if isinstance(nodes_payload, list):
        raw_list = nodes_payload
    elif isinstance(nodes_payload, dict):
        raw_list = nodes_payload.get("nodes")
        if raw_list is None:
            raw_list = nodes_payload.get("items") or nodes_payload.get("data")
    if not isinstance(raw_list, list):
        return out
    for n in raw_list:
        if not isinstance(n, dict):
            continue
        key = _panel_node_uuid_key(n)
        if not key:
            continue
        online = _panel_node_users_online(n)
        if online is not None:
            out[key] = online
    return out


def _enrich_bandwidth_nodes_with_online(
    bw: Any,
    online_by_uuid: Dict[str, int],
    online_by_name: Optional[Dict[str, int]] = None,
) -> None:
    """Attach usersOnline to topNodes/series (UUID and optional node name)."""
    if not isinstance(bw, dict):
        return
    if not online_by_uuid and not online_by_name:
        return
    for key in ("topNodes", "series"):
        arr = bw.get(key)
        if not isinstance(arr, list):
            continue
        for item in arr:
            if not isinstance(item, dict):
                continue
            if item.get("usersOnline") is not None:
                continue
            uid = item.get("uuid") or item.get("nodeUuid") or item.get("node_uuid")
            if uid and online_by_uuid:
                hit = online_by_uuid.get(str(uid).strip().lower())
                if hit is not None:
                    item["usersOnline"] = hit
                    continue
            if online_by_name:
                nm = item.get("name")
                if nm and isinstance(nm, str):
                    hitn = online_by_name.get(nm.strip().lower())
                    if hitn is not None:
                        item["usersOnline"] = hitn


def _build_admin_webapp_referral_link(
    base_url: Optional[str], referral_code: Optional[str]
) -> Optional[str]:
    """Mirror of ``subscription_webapp._build_webapp_referral_link``.

    Kept local to avoid a cross-module import cycle (subscription_webapp
    imports admin_api).
    """
    if not base_url or not referral_code:
        return None
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ref"] = f"u{referral_code}"
    new_query = "&".join(f"{k}={v}" for k, v in query.items())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
