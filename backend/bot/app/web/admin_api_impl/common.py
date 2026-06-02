# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


def _ok(payload: Dict[str, Any], **extra) -> web.Response:
    body = {"ok": True, **payload, **extra}
    return web.json_response(body)


def _error(status: int, code: str, message: str = "") -> web.Response:
    return web.json_response(
        {"ok": False, "error": code, "message": message or code},
        status=status,
    )


async def _read_json(request: web.Request) -> Dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _serialize_user(user: User) -> Dict[str, Any]:
    return {
        "user_id": int(user.user_id),
        "telegram_id": int(user.telegram_id) if user.telegram_id else None,
        "telegram_photo_url": user.telegram_photo_url,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "language_code": user.language_code,
        "is_banned": bool(user.is_banned),
        "registration_date": user.registration_date.isoformat() if user.registration_date else None,
        "panel_user_uuid": user.panel_user_uuid,
        "referral_code": user.referral_code,
        "referred_by_id": int(user.referred_by_id) if user.referred_by_id else None,
    }


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
    premium_bonus_bytes = int(getattr(sub, "premium_bonus_bytes", 0) or 0)
    regular_bonus_bytes = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
    regular_unlimited_override = bool(getattr(sub, "regular_unlimited_override", False))
    premium_unlimited_override = bool(getattr(sub, "premium_unlimited_override", False))
    premium_limit_bytes = _premium_limit_bytes_from_subscription(sub)
    provider = sub.provider
    is_trial = str(provider or "").strip().lower() == "trial"
    display_label = "Trial" if is_trial else sub.tariff_key
    return {
        "subscription_id": int(sub.subscription_id),
        "panel_user_uuid": sub.panel_user_uuid,
        "panel_subscription_uuid": sub.panel_subscription_uuid,
        "start_date": sub.start_date.isoformat() if sub.start_date else None,
        "end_date": sub.end_date.isoformat() if sub.end_date else None,
        "duration_months": sub.duration_months,
        "is_active": bool(sub.is_active),
        "status_from_panel": sub.status_from_panel,
        "traffic_limit_bytes": sub.traffic_limit_bytes,
        "traffic_used_bytes": sub.traffic_used_bytes,
        "tier_baseline_bytes": sub.tier_baseline_bytes,
        "topup_balance_bytes": sub.topup_balance_bytes,
        "premium_used_bytes": sub.premium_used_bytes,
        "premium_limit_bytes": premium_limit_bytes,
        "premium_baseline_bytes": sub.premium_baseline_bytes,
        "premium_topup_balance_bytes": sub.premium_topup_balance_bytes,
        "premium_topup_used_bytes": getattr(sub, "premium_topup_used_bytes", 0),
        "premium_bonus_bytes": premium_bonus_bytes,
        "regular_bonus_bytes": regular_bonus_bytes,
        "regular_unlimited_override": regular_unlimited_override,
        "premium_unlimited_override": premium_unlimited_override,
        "premium_is_limited": bool(sub.premium_is_limited),
        "tariff_key": sub.tariff_key,
        "display_label": display_label,
        "is_trial": is_trial,
        "auto_renew_enabled": bool(sub.auto_renew_enabled),
        "provider": provider,
        "is_throttled": bool(sub.is_throttled),
    }


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
    # Avoid lazy-loading `payment.user` outside an active SQLAlchemy session.
    # Some admin routes serialize payments after the session scope is closed.
    telegram_id = None
    loaded_user = payment.__dict__.get("user")
    user_label = _payment_user_display_label(loaded_user, int(payment.user_id))
    if loaded_user is not None:
        tid = getattr(loaded_user, "telegram_id", None)
        if tid is not None:
            try:
                telegram_id = int(tid)
            except (TypeError, ValueError):
                telegram_id = None
    reg_gb, prem_gb = _payment_traffic_gb_split(payment)
    return {
        "payment_id": int(payment.payment_id),
        "user_id": int(payment.user_id),
        "user_label": user_label,
        "telegram_id": telegram_id,
        "traffic_regular_gb": reg_gb,
        "traffic_premium_gb": prem_gb,
        "provider": payment.provider,
        "provider_payment_id": payment.provider_payment_id,
        "amount": float(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
        "description": payment.description,
        "subscription_duration_months": payment.subscription_duration_months,
        "sale_mode": payment.sale_mode,
        "tariff_key": payment.tariff_key,
        "purchased_gb": payment.purchased_gb,
        "purchased_hwid_devices": payment.purchased_hwid_devices,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
    }


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
    return {
        "id": int(campaign.ad_campaign_id),
        "source": campaign.source,
        "start_param": campaign.start_param,
        "cost": float(campaign.cost or 0),
        "is_active": bool(campaign.is_active),
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "stats": totals or {},
    }


def _serialize_log(entry: MessageLog) -> Dict[str, Any]:
    author_user = entry.__dict__.get("author_user")
    target_user = entry.__dict__.get("target_user")
    user_id = int(entry.user_id) if entry.user_id is not None else None
    target_user_id = int(entry.target_user_id) if entry.target_user_id is not None else None
    return {
        "log_id": int(entry.log_id),
        "user_id": user_id,
        "user_label": _user_display_label(
            author_user,
            user_id,
            first_name=entry.telegram_first_name,
            username=entry.telegram_username,
        ),
        "telegram_username": entry.telegram_username,
        "telegram_first_name": entry.telegram_first_name,
        "email": getattr(author_user, "email", None),
        "event_type": entry.event_type,
        "content": entry.content,
        "is_admin_event": bool(entry.is_admin_event),
        "target_user_id": target_user_id,
        "target_user_label": _user_display_label(target_user, target_user_id),
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
    }


def _tariffs_config_path(settings: Settings) -> Path:
    return Path(settings.TARIFFS_CONFIG_PATH).expanduser()


def _tariffs_config_payload(config: TariffsConfig) -> Dict[str, Any]:
    return config.model_dump(mode="json", exclude_none=True)


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
    return config.model_dump(mode="json", exclude_none=True)


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
