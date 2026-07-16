import contextlib
import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from aiohttp import web

from bot.app.web.response_helpers import json_response
from bot.services import panel_activity as _panel_activity
from config.settings import Settings
from config.tariffs_config import TariffsConfig
from config.traffic_strategy import normalize_traffic_limit_strategy
from db.models import AdCampaign, MessageLog, Payment, PromoCode, Subscription, User

from .schemas import AdminSubscriptionOut, AdminUserOut, AdOut, LogOut, PaymentOut, PromoOut


def _ok(payload: dict[str, Any], **extra: Any) -> web.Response:
    body = {"ok": True, **payload, **extra}
    return json_response(body)


def _error(status: int, code: str, message: str = "") -> web.Response:
    return json_response(
        {"ok": False, "error": code, "message": message or code},
        status=status,
    )


def _error_payload(
    status: int,
    code: str,
    *,
    errors: dict[str, Any] | None = None,
    message: str = "",
) -> web.Response:
    body: dict[str, Any] = {"ok": False, "error": code}
    if message:
        body["message"] = message
    if errors:
        body["errors"] = errors
    return json_response(body, status=status)


def _panel_user_connection_activity(panel_user_data: Any) -> dict[str, Any]:
    return _panel_activity._panel_user_connection_activity(panel_user_data)


def _panel_user_last_connected_at(panel_user_data: Any) -> str | None:
    return _panel_activity._panel_user_last_connected_at(panel_user_data)


def _serialize_user(user: User) -> dict[str, Any]:
    return cast(dict[str, Any], AdminUserOut.from_orm_user(user).model_dump(mode="json"))


def _premium_limit_bytes_from_subscription(sub: Subscription) -> int:
    premium_bonus_bytes = int(getattr(sub, "premium_bonus_bytes", 0) or 0)
    return (
        int(sub.premium_baseline_bytes or 0)
        + int(sub.premium_topup_balance_bytes or 0)
        + int(getattr(sub, "premium_topup_used_bytes", 0) or 0)
        + premium_bonus_bytes
    )


def _premium_traffic_list_payload(sub: Subscription | None) -> dict[str, Any]:
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


def _serialize_subscription(sub: Subscription) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        AdminSubscriptionOut.from_orm_subscription(sub).model_dump(mode="json"),
    )


def _is_trial_subscription(sub: Subscription | Any | None) -> bool:
    if sub is None:
        return False
    return bool(getattr(sub, "is_trial", False)) or (
        str(getattr(sub, "provider", "") or "").strip().lower() == "trial"
    )


def _settings_bool(settings: Settings, name: str, default: bool = False) -> bool:
    try:
        return bool(getattr(settings, name))
    except Exception:
        return default


def _admin_subscription_billing_model(
    settings: Settings,
    sub: Subscription | Any | None,
) -> str | None:
    if sub is None or _is_trial_subscription(sub):
        return None

    tariff_key = str(getattr(sub, "tariff_key", "") or "").strip()
    if tariff_key:
        try:
            tariffs_config = settings.tariffs_config
        except Exception:
            tariffs_config = None
        if tariffs_config is not None:
            try:
                tariff = tariffs_config.require(tariff_key)
            except Exception:
                tariff = None
            billing_model = str(getattr(tariff, "billing_model", "") or "").strip().lower()
            if billing_model in {"period", "traffic"}:
                return billing_model
        return "period"

    if _settings_bool(settings, "traffic_sale_mode"):
        return "traffic"
    return "period"


def _admin_subscription_traffic_strategy_fallback(
    settings: Settings,
    sub: Subscription | Any | None,
) -> str:
    if _admin_subscription_billing_model(settings, sub) == "traffic":
        return "NO_RESET"
    if _is_trial_subscription(sub):
        return normalize_traffic_limit_strategy(
            settings.TRIAL_TRAFFIC_STRATEGY,
            default="NO_RESET",
        )
    tariff_key = str(getattr(sub, "tariff_key", "") or "").strip()
    if tariff_key:
        try:
            tariff = settings.tariffs_config.require(tariff_key)
        except Exception:
            tariff = None
        configured_strategy = getattr(tariff, "traffic_limit_strategy", None)
        if configured_strategy:
            return normalize_traffic_limit_strategy(configured_strategy, default="MONTH")
    return normalize_traffic_limit_strategy(
        settings.USER_TRAFFIC_STRATEGY,
        default="NO_RESET",
    )


def _admin_subscription_traffic_strategy_lock_reason(
    settings: Settings,
    sub: Subscription | Any | None,
    *,
    panel_available: bool,
) -> str | None:
    if sub is None:
        return "no_active_subscription"
    if _is_trial_subscription(sub):
        return "trial"
    if _admin_subscription_billing_model(settings, sub) == "traffic":
        return "traffic_tariff"
    if not panel_available:
        return "panel_unavailable"
    return None


def _decorate_admin_subscription_traffic_strategy(
    payload: dict[str, Any],
    settings: Settings,
    sub: Subscription | Any,
    *,
    traffic_limit_strategy: str | None = None,
    panel_available: bool,
) -> dict[str, Any]:
    fallback = _admin_subscription_traffic_strategy_fallback(settings, sub)
    lock_reason = _admin_subscription_traffic_strategy_lock_reason(
        settings,
        sub,
        panel_available=panel_available,
    )
    payload["billing_model"] = _admin_subscription_billing_model(settings, sub)
    payload["traffic_limit_strategy"] = normalize_traffic_limit_strategy(
        traffic_limit_strategy or fallback,
        default=fallback,
    )
    payload["traffic_strategy_editable"] = lock_reason is None
    payload["traffic_strategy_lock_reason"] = lock_reason
    return payload


def _payment_traffic_gb_split(payment: Payment) -> tuple[float | None, float | None]:
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
    fallback_user_id: int | None,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    email: str | None = None,
) -> str | None:
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


def _serialize_payment(payment: Payment) -> dict[str, Any]:
    return cast(dict[str, Any], PaymentOut.from_orm_payment(payment).model_dump(mode="json"))


def _serialize_promo(promo: PromoCode) -> dict[str, Any]:
    return cast(dict[str, Any], PromoOut.from_orm_promo(promo).model_dump(mode="json"))


def _serialize_ad(campaign: AdCampaign, totals: dict[str, Any] | None = None) -> dict[str, Any]:
    return cast(dict[str, Any], AdOut.from_orm_ad(campaign, totals).model_dump(mode="json"))


def _serialize_log(entry: MessageLog) -> dict[str, Any]:
    return cast(dict[str, Any], LogOut.from_orm_log(entry).model_dump(mode="json"))


def _tariffs_config_path(settings: Settings) -> Path:
    return Path(settings.TARIFFS_CONFIG_PATH).expanduser()


def _tariffs_config_payload(config: TariffsConfig) -> dict[str, Any]:
    return cast(dict[str, Any], config.model_dump(mode="json", exclude_none=True))


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
            with contextlib.suppress(OSError):
                tmp_path.unlink()
        path.write_text(payload, encoding="utf-8")


def _webapp_themes_catalog_payload(config: Any) -> dict[str, Any]:
    return cast(dict[str, Any], config.model_dump(mode="json", exclude_none=True))


def _panel_node_uuid_key(node: dict[str, Any]) -> str:
    uid = node.get("nodeUuid") or node.get("node_uuid") or node.get("uuid") or node.get("id")
    return str(uid).strip().lower() if uid else ""


def _panel_node_users_online(node: dict[str, Any]) -> int | None:
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


def _panel_nodes_online_by_uuid(nodes_payload: Any) -> dict[str, int]:
    """Build node_uuid(lower) -> usersOnline from GET /system/stats/nodes payload."""
    out: dict[str, int] = {}
    raw_list: list[Any] | None = None
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
    online_by_uuid: dict[str, int],
    online_by_name: dict[str, int] | None = None,
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
    base_url: str | None, referral_code: str | None
) -> str | None:
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


def _build_admin_promo_bot_link(bot_username: str | None, code: str | None) -> str | None:
    username = str(bot_username or "").strip().lstrip("@")
    normalized_code = str(code or "").strip()
    if not username or username == "your_bot_username" or not normalized_code:
        return None
    return f"https://t.me/{quote(username, safe='')}?start=promo_{quote(normalized_code, safe='')}"


def _build_admin_promo_webapp_link(base_url: str | None, code: str | None) -> str | None:
    raw = str(base_url or "").strip()
    normalized_code = str(code or "").strip()
    if not raw or not normalized_code:
        return None
    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["startapp"] = f"promo_{normalized_code}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
