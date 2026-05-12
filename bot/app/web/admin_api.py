"""HTTP API powering the admin section of the subscription Mini App.

All routes require an authenticated webapp session (cookie or Bearer
token) AND the resolved Telegram user id must appear in
``settings.ADMIN_IDS``. Authorization is enforced via the
``_require_admin_user_id`` helper, never trusted from the client.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiohttp import web
from pydantic import ValidationError
from sqlalchemy import func as sa_func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_settings_manifest import (
    SETTINGS_MANIFEST,
    coerce_value,
    get_field_by_key,
    manifest_payload,
)
from bot.services.settings_override_service import (
    current_value,
    update_overrides,
)
from bot.services.referral_service import ReferralService
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from config.settings import Settings
from config.tariffs_config import TariffsConfig
from db.dal import (
    ad_dal,
    app_settings_dal,
    message_log_dal,
    panel_sync_dal,
    payment_dal,
    promo_code_dal,
    subscription_dal,
    user_dal,
)
from db.models import (
    AdCampaign,
    MessageLog,
    Payment,
    PromoCode,
    Subscription,
    User,
    UserTelegramAvatar,
)

logger = logging.getLogger(__name__)


# ─── Auth ──────────────────────────────────────────────────────────


def _require_admin_user_id(request: web.Request) -> int:
    """Return the authenticated user id, or raise 401/403 for non-admins."""

    from bot.app.web.subscription_webapp import _extract_authenticated_user_id

    settings: Settings = request.app["settings"]
    user_id = _extract_authenticated_user_id(request)
    if not user_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"ok": False, "error": "unauthorized"}),
            content_type="application/json",
        )

    admin_ids = settings.ADMIN_IDS or []
    db_user_telegram_id = request.get("admin_telegram_id")
    if db_user_telegram_id is None:
        raise web.HTTPForbidden(
            text=json.dumps({"ok": False, "error": "forbidden"}),
            content_type="application/json",
        )

    if int(db_user_telegram_id) not in {int(x) for x in admin_ids}:
        raise web.HTTPForbidden(
            text=json.dumps({"ok": False, "error": "forbidden"}),
            content_type="application/json",
        )
    return int(user_id)


@web.middleware
async def admin_auth_middleware(request: web.Request, handler):
    """Resolve the Telegram id of the current user and stash it on the request.

    Doing this once per request lets every admin route call
    ``_require_admin_user_id`` without re-querying the DB.
    """

    if not request.path.startswith("/api/admin"):
        return await handler(request)

    from bot.app.web.subscription_webapp import _extract_authenticated_user_id

    user_id = _extract_authenticated_user_id(request)
    if user_id:
        async_session_factory: sessionmaker = request.app["async_session_factory"]
        async with async_session_factory() as session:
            db_user = await user_dal.get_user_by_id(session, user_id)
        if db_user and db_user.telegram_id:
            request["admin_telegram_id"] = int(db_user.telegram_id)
        elif db_user:
            # No telegram_id yet (email-only user) — can't be an admin
            request["admin_telegram_id"] = None

    return await handler(request)


# ─── Helpers ───────────────────────────────────────────────────────


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


def _serialize_subscription(sub: Subscription) -> Dict[str, Any]:
    premium_limit_bytes = (
        int(sub.premium_baseline_bytes or 0)
        + int(sub.premium_topup_balance_bytes or 0)
        + int(getattr(sub, "premium_topup_used_bytes", 0) or 0)
    )
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
        "premium_is_limited": bool(sub.premium_is_limited),
        "tariff_key": sub.tariff_key,
        "auto_renew_enabled": bool(sub.auto_renew_enabled),
        "provider": sub.provider,
        "is_throttled": bool(sub.is_throttled),
    }


def _serialize_payment(payment: Payment) -> Dict[str, Any]:
    # Avoid lazy-loading `payment.user` outside an active SQLAlchemy session.
    # Some admin routes serialize payments after the session scope is closed.
    user_label = str(payment.user_id)
    loaded_user = payment.__dict__.get("user")
    if loaded_user is not None:
        user_label = loaded_user.username or loaded_user.first_name or str(payment.user_id)
    return {
        "payment_id": int(payment.payment_id),
        "user_id": int(payment.user_id),
        "user_label": user_label,
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
        "created_by_admin_id": int(promo.created_by_admin_id) if promo.created_by_admin_id else None,
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
    return {
        "log_id": int(entry.log_id),
        "user_id": int(entry.user_id) if entry.user_id else None,
        "telegram_username": entry.telegram_username,
        "telegram_first_name": entry.telegram_first_name,
        "event_type": entry.event_type,
        "content": entry.content,
        "is_admin_event": bool(entry.is_admin_event),
        "target_user_id": int(entry.target_user_id) if entry.target_user_id else None,
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


# ─── Routes ────────────────────────────────────────────────────────


async def admin_me_route(request: web.Request) -> web.Response:
    user_id = _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    return _ok({}, user_id=user_id, admin_ids=list(settings.ADMIN_IDS or []))


async def admin_stats_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        user_stats = await user_dal.get_enhanced_user_statistics(session)
        financial_stats = await payment_dal.get_financial_statistics(session)
        sync_status = await panel_sync_dal.get_panel_sync_status(session)
        recent_payments = await payment_dal.get_recent_payment_logs_with_user(session, limit=10)

    payload = {
        "users": user_stats,
        "financial": financial_stats,
        "panel_sync": {
            "status": sync_status.status if sync_status else "never_run",
            "last_sync_time": sync_status.last_sync_time.isoformat() if sync_status and sync_status.last_sync_time else None,
            "details": sync_status.details if sync_status else None,
            "users_processed": sync_status.users_processed_from_panel if sync_status else 0,
            "subscriptions_synced": sync_status.subscriptions_synced if sync_status else 0,
        },
        "recent_payments": [_serialize_payment(p) for p in recent_payments],
    }

    panel_service = request.app.get("panel_service")
    if panel_service is not None:
        try:
            system = await panel_service.get_system_stats()
            bandwidth = await panel_service.get_bandwidth_stats()
            panel_body: Dict[str, Any] = {
                "system": system or {},
                "bandwidth": bandwidth or {},
            }
            try:
                nodes = await panel_service.get_nodes_statistics()
                panel_body["nodes"] = nodes or {}
            except Exception as exc_nodes:  # pragma: no cover - optional endpoint
                logger.debug("Panel nodes stats unavailable: %s", exc_nodes)
                panel_body["nodes"] = {}
            try:
                today = datetime.now(timezone.utc).date()
                start_d = today - timedelta(days=7)
                nodes_bw = await panel_service.get_nodes_bandwidth_usage(
                    start=start_d.isoformat(),
                    end=today.isoformat(),
                    top_nodes_limit=64,
                )
                panel_body["nodes_bandwidth"] = nodes_bw or {}
            except Exception as exc_nb:  # pragma: no cover - optional endpoint
                logger.debug("Panel nodes bandwidth range unavailable: %s", exc_nb)
                panel_body["nodes_bandwidth"] = {}
            try:
                online_map = _panel_nodes_online_by_uuid(panel_body.get("nodes"))
                lookups = await panel_service.get_nodes_online_lookups()
                for k, v in lookups.get("byUuid", {}).items():
                    online_map[k] = v
                _enrich_bandwidth_nodes_with_online(
                    panel_body.get("nodes_bandwidth"),
                    online_map,
                    lookups.get("byName") or {},
                )
            except Exception as exc_merge:  # pragma: no cover
                logger.debug("Panel nodes online merge skipped: %s", exc_merge)
            payload["panel"] = panel_body
        except Exception as exc:
            logger.debug("Panel stats unavailable: %s", exc)
            payload["panel"] = {"error": "unavailable"}

    queue_manager = get_queue_manager()
    if queue_manager:
        try:
            payload["queue"] = queue_manager.get_queue_stats()
        except Exception:  # pragma: no cover - defensive
            payload["queue"] = None

    payload["currency_symbol"] = settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    return _ok(payload)


# ─── Users ─────────────────────────────────────────────────────────


async def admin_users_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    query = (request.query.get("q") or "").strip()
    filter_value = (request.query.get("filter") or "all").lower()
    panel_status = (request.query.get("panel_status") or "all").lower()
    sort_value = (request.query.get("sort") or "registered_desc").lower()

    async with async_session_factory() as session:
        users, total = await _filter_and_sort_users(
            session,
            query=query,
            filter_value=filter_value,
            panel_status=panel_status,
            sort_value=sort_value,
            page=page,
            page_size=page_size,
        )

        statuses = await _bulk_user_statuses(session, [u.user_id for u in users])
        cached_avatar_ids = await _bulk_user_avatar_keys(session, [u.user_id for u in users])

    serialized = []
    for user in users:
        payload = _serialize_user(user)
        status_payload = statuses.get(user.user_id) or {"status": "bot_only", "end_date": None}
        payload["panel_status"] = status_payload.get("status")
        if status_payload.get("status") == "expired" and status_payload.get("end_date"):
            payload["panel_status_expired_at"] = status_payload["end_date"]
        payload["avatar_url"] = (
            f"/api/admin/users/{user.user_id}/avatar?v={cached_avatar_ids[user.user_id]}"
            if user.user_id in cached_avatar_ids
            else None
        )
        serialized.append(payload)

    return _ok(
        {
            "users": serialized,
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    )


async def _bulk_user_statuses(
    session: AsyncSession, user_ids: List[int]
) -> Dict[int, Dict[str, Optional[str]]]:
    """Return active subscription status for a batch of users.

    Returns the panel status (active/expired/limited/disabled) when an active
    subscription exists, otherwise ``"bot_only"`` when the user is in the bot
    but has no panel subscription.
    """

    if not user_ids:
        return {}
    stmt = (
        select(Subscription.user_id, Subscription.status_from_panel, Subscription.is_active, Subscription.end_date)
        .where(Subscription.user_id.in_(user_ids))
        .order_by(Subscription.is_active.desc(), Subscription.end_date.desc().nullslast())
    )
    rows = (await session.execute(stmt)).all()
    out: Dict[int, Dict[str, Optional[str]]] = {}
    for uid, panel_status, is_active, end_date in rows:
        if uid in out:
            continue
        if is_active:
            status = (panel_status or "active").lower()
        else:
            status = (panel_status or "expired").lower()
        out[uid] = {
            "status": status,
            "end_date": end_date.isoformat() if end_date else None,
        }
    for uid in user_ids:
        if uid not in out:
            out[uid] = {"status": "bot_only", "end_date": None}
    return out


async def _bulk_user_avatar_keys(
    session: AsyncSession, user_ids: List[int]
) -> Dict[int, str]:
    """Return ``{user_id: cache_key}`` for users with a cached Telegram avatar.

    The cache key is the row's ``updated_at`` timestamp — used as a
    cache-buster query param so the browser refetches when the avatar
    changes.
    """

    if not user_ids:
        return {}
    stmt = select(UserTelegramAvatar.user_id, UserTelegramAvatar.updated_at).where(
        UserTelegramAvatar.user_id.in_(user_ids)
    )
    rows = (await session.execute(stmt)).all()
    return {
        int(uid): (updated_at.isoformat() if updated_at else "")
        for uid, updated_at in rows
    }


async def admin_user_avatar_route(request: web.Request) -> web.Response:
    """Serve the cached Telegram avatar for any user (admin-only).

    Mirrors ``/api/account/avatar`` but takes a ``user_id`` from the URL
    and uses admin auth. Only the cached blob from
    ``user_telegram_avatars`` is served — refreshing from Telegram is the
    job of the user-facing endpoint, so the admin list never blocks on a
    Telegram round-trip.
    """

    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        avatar = await session.get(UserTelegramAvatar, target_id)

    if not avatar:
        raise web.HTTPNotFound(text="avatar_not_cached")

    etag = (
        f'W/"avatar-{target_id}-{int(avatar.updated_at.timestamp())}"'
        if avatar.updated_at
        else None
    )
    if etag and request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers={"ETag": etag})

    response = web.Response(
        body=bytes(avatar.image_bytes),
        content_type=avatar.content_type or "image/jpeg",
    )
    response.headers["Cache-Control"] = "private, max-age=3600"
    if etag:
        response.headers["ETag"] = etag
    return response


async def _filter_and_sort_users(
    session: AsyncSession,
    *,
    query: str = "",
    filter_value: str,
    panel_status: str = "all",
    sort_value: str,
    page: int,
    page_size: int,
) -> tuple[List[User], int]:
    """Return paginated users with optional search, filter and sort applied."""

    stmt = select(User)
    count_stmt = select(sa_func.count(User.user_id))

    search_cond = _user_search_condition(query)
    if search_cond is not None:
        stmt = stmt.where(search_cond)
        count_stmt = count_stmt.where(search_cond)

    f = (filter_value or "all").lower()
    if f == "banned":
        cond = User.is_banned.is_(True)
    elif f == "active":
        cond = User.is_banned.is_(False)
    elif f == "tg_linked":
        cond = User.telegram_id.is_not(None)
    elif f == "no_tg":
        cond = User.telegram_id.is_(None)
    elif f == "email_linked":
        cond = User.email.is_not(None)
    elif f == "no_email":
        cond = User.email.is_(None)
    elif f == "panel_linked":
        cond = User.panel_user_uuid.is_not(None)
    else:
        cond = None

    if cond is not None:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    panel_cond = _user_panel_status_condition(panel_status)
    if panel_cond is not None:
        stmt = stmt.where(panel_cond)
        count_stmt = count_stmt.where(panel_cond)

    sort_map = {
        "registered_desc": User.registration_date.desc().nullslast(),
        "registered_asc": User.registration_date.asc().nullslast(),
        "name_asc": (
            sa_func.coalesce(User.first_name, User.username, User.email).asc(),
            User.user_id.asc(),
        ),
        "name_desc": (
            sa_func.coalesce(User.first_name, User.username, User.email).desc(),
            User.user_id.desc(),
        ),
        "id_asc": User.user_id.asc(),
        "id_desc": User.user_id.desc(),
    }
    order = sort_map.get(sort_value, sort_map["registered_desc"])
    if isinstance(order, tuple):
        stmt = stmt.order_by(*order)
    else:
        stmt = stmt.order_by(order)

    stmt = stmt.offset(max(page, 0) * max(page_size, 1)).limit(max(page_size, 1))

    users = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return users, int(total)


def _user_panel_status_condition(panel_status: str):
    status = (panel_status or "all").lower()
    if status not in {"active", "expired", "limited"}:
        return None

    normalized_status = sa_func.lower(sa_func.coalesce(Subscription.status_from_panel, ""))
    blank_status = or_(Subscription.status_from_panel.is_(None), Subscription.status_from_panel == "")
    if status == "active":
        status_cond = or_(normalized_status == "active", blank_status & Subscription.is_active.is_(True))
    elif status == "expired":
        status_cond = or_(normalized_status == "expired", blank_status & Subscription.is_active.is_(False))
    else:
        status_cond = normalized_status == "limited"

    return (
        select(Subscription.subscription_id)
        .where(Subscription.user_id == User.user_id, status_cond)
        .exists()
    )


def _user_search_condition(query: str):
    raw = (query or "").strip().lstrip("@")
    if not raw:
        return None

    like = f"%{raw}%"
    conditions = [
        User.username.ilike(like),
        User.first_name.ilike(like),
        User.last_name.ilike(like),
        User.email.ilike(like),
    ]
    if raw.isdigit():
        numeric = int(raw)
        conditions.extend([User.user_id == numeric, User.telegram_id == numeric])

    return or_(*conditions)


async def admin_user_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    settings: Settings = request.app["settings"]

    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found", "User not found")

        active_sub = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        latest_subs_stmt = (
            select(Subscription)
            .where(Subscription.user_id == target_id)
            .order_by(Subscription.start_date.desc().nullslast())
            .limit(20)
        )
        latest_subs = (await session.execute(latest_subs_stmt)).scalars().all()
        total_paid = await payment_dal.get_user_total_paid(session, target_id)
        recent_payments_stmt = (
            select(Payment)
            .where(Payment.user_id == target_id)
            .order_by(Payment.created_at.desc())
            .limit(20)
        )
        recent_payments = (await session.execute(recent_payments_stmt)).scalars().all()
        log_count = await message_log_dal.count_user_message_logs(session, target_id)
        avatar_keys = await _bulk_user_avatar_keys(session, [target_id])

        # Referral links — both the bot deep-link and the webapp deep-link.
        referral_code: Optional[str] = None
        try:
            referral_code = await user_dal.ensure_referral_code(session, user)
            await session.commit()
        except Exception as exc_ref:  # pragma: no cover — defensive
            logger.warning("Failed to ensure referral code for user %s: %s", target_id, exc_ref)
            await session.rollback()

    referral_service: Optional[ReferralService] = request.app.get("referral_service")
    bot_username = request.app.get("bot_username") or ""
    referral_bot_link: Optional[str] = None
    if referral_service and bot_username and referral_code:
        try:
            async with async_session_factory() as session:
                referral_bot_link = await referral_service.generate_referral_link(
                    session, bot_username, target_id
                )
        except Exception as exc_link:  # pragma: no cover
            logger.warning("Failed to build bot referral link for %s: %s", target_id, exc_link)
    referral_webapp_link = _build_admin_webapp_referral_link(
        getattr(settings, "SUBSCRIPTION_MINI_APP_URL", None),
        referral_code,
    )

    # Subscription page URL — the raw panel `subscriptionUrl` that the user
    # imports into their VPN client. May be missing if the user has never
    # been provisioned on the panel.
    subscription_url: Optional[str] = None
    panel_uuid = getattr(user, "panel_user_uuid", None)
    if panel_uuid:
        subscription_service = request.app.get("subscription_service")
        panel_service = getattr(subscription_service, "panel_service", None)
        if panel_service is not None:
            try:
                panel_data = await panel_service.get_user_by_uuid(panel_uuid)
                if panel_data:
                    subscription_url = panel_data.get("subscriptionUrl") or None
            except Exception as exc_panel:  # pragma: no cover
                logger.warning(
                    "Failed to fetch subscriptionUrl for user %s (uuid=%s): %s",
                    target_id, panel_uuid, exc_panel,
                )

    serialized_user = _serialize_user(user)
    serialized_user["avatar_url"] = (
        f"/api/admin/users/{target_id}/avatar?v={avatar_keys[target_id]}"
        if target_id in avatar_keys
        else None
    )

    return _ok(
        {
            "user": serialized_user,
            "active_subscription": _serialize_subscription(active_sub) if active_sub else None,
            "subscriptions": [_serialize_subscription(s) for s in (latest_subs or [])],
            "total_paid": float(total_paid),
            "recent_payments": [_serialize_payment(p) for p in recent_payments],
            "log_count": int(log_count or 0),
            "subscription_url": subscription_url,
            "referral": {
                "code": referral_code,
                "bot_link": referral_bot_link,
                "webapp_link": referral_webapp_link,
            },
        }
    )


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


async def admin_user_ban_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    payload = await _read_json(request)
    desired = bool(payload.get("banned"))

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")
        user.is_banned = bool(desired)
        await session.commit()
        await session.refresh(user)
    return _ok({"user": _serialize_user(user)})


async def admin_user_message_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    payload = await _read_json(request)
    text = str(payload.get("text") or "").strip()
    if not text:
        return _error(400, "empty_text")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        target_user = await user_dal.get_user_by_id(session, target_id)
        if not target_user or not target_user.telegram_id:
            return _error(404, "no_telegram_account")

        try:
            await send_message_via_queue(
                queue_manager,
                int(target_user.telegram_id),
                MessageContent(content_type="text", text=text),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.warning("Admin direct message failed: %s", exc)
            return _error(502, "send_failed", str(exc))

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_direct_message_webapp",
                "content": text[:4000],
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )

    return _ok({})


async def admin_user_message_preview_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    admin_telegram_id = request.get("admin_telegram_id")
    target_id = int(request.match_info["user_id"])
    payload = await _read_json(request)
    text = str(payload.get("text") or "").strip()
    if not text:
        return _error(400, "empty_text")
    if not admin_telegram_id:
        return _error(403, "admin_telegram_unavailable")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    try:
        await send_message_via_queue(
            queue_manager,
            int(admin_telegram_id),
            MessageContent(content_type="text", text=text),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning("Admin direct message preview failed: %s", exc)
        return _error(502, "preview_failed", str(exc))

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_direct_message_preview_webapp",
                "content": text[:4000],
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )

    return _ok({})


async def admin_user_delete_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        ok = await user_dal.delete_user_and_relations(session, target_id)
        if not ok:
            await session.rollback()
            return _error(404, "not_found")
        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_delete_user_webapp",
                "content": f"Deleted user_id={target_id}",
                "is_admin_event": True,
            },
        )
        await session.commit()
    return _ok({})


async def admin_user_reset_trial_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    panel_service = request.app.get("panel_service")
    subscription_service = request.app.get("subscription_service")
    if panel_service is None or subscription_service is None:
        return _error(503, "service_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")

        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if active:
            await session.delete(active)

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_reset_trial_webapp",
                "content": f"Reset trial for user_id={target_id}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
    return _ok({})


async def admin_user_extend_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    payload = await _read_json(request)
    try:
        days = int(payload.get("days") or 0)
    except (TypeError, ValueError):
        return _error(400, "invalid_days")
    if days <= 0:
        return _error(400, "invalid_days")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if not active:
            return _error(404, "no_active_subscription")

        new_end = (active.end_date or datetime.now(timezone.utc)) + timedelta(days=days)
        active.end_date = new_end
        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_extend_subscription_webapp",
                "content": f"+{days}d -> {new_end.isoformat()}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
        await session.refresh(active)
    return _ok({"subscription": _serialize_subscription(active)})


# ─── Payments ──────────────────────────────────────────────────────


async def admin_payments_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))

    async with async_session_factory() as session:
        from sqlalchemy.orm import selectinload

        stmt = (
            select(Payment)
            .options(selectinload(Payment.user))
            .order_by(Payment.created_at.desc())
            .offset(page * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(stmt)).scalars().all()
        total = await payment_dal.get_payments_count(session)

    return _ok(
        {
            "payments": [_serialize_payment(p) for p in rows],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )


async def admin_payments_export_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        from sqlalchemy.orm import selectinload

        stmt = (
            select(Payment)
            .options(selectinload(Payment.user))
            .order_by(Payment.created_at.desc())
            .limit(10000)
        )
        rows = (await session.execute(stmt)).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "payment_id",
            "user_id",
            "user_label",
            "provider",
            "provider_payment_id",
            "amount",
            "currency",
            "status",
            "description",
            "duration_months",
            "sale_mode",
            "tariff_key",
            "created_at",
        ]
    )
    for p in rows:
        label = ""
        if p.user:
            label = p.user.username or p.user.first_name or ""
        writer.writerow(
            [
                p.payment_id,
                p.user_id,
                label,
                p.provider,
                p.provider_payment_id or "",
                p.amount,
                p.currency,
                p.status,
                p.description or "",
                p.subscription_duration_months or "",
                p.sale_mode or "",
                p.tariff_key or "",
                p.created_at.isoformat() if p.created_at else "",
            ]
        )

    response = web.Response(
        body=buffer.getvalue().encode("utf-8-sig"),
        content_type="text/csv",
        charset="utf-8",
    )
    response.headers["Content-Disposition"] = 'attachment; filename="payments.csv"'
    return response


# ─── Promo codes ───────────────────────────────────────────────────


async def admin_promos_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    async with async_session_factory() as session:
        promos = await promo_code_dal.get_all_promo_codes_with_details(
            session, limit=page_size, offset=page * page_size
        )
        total = await promo_code_dal.get_promo_codes_count(session)
    return _ok(
        {
            "promos": [_serialize_promo(p) for p in promos],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )


async def admin_promo_create_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    payload = await _read_json(request)
    code = str(payload.get("code") or "").strip().upper()
    bonus_days = int(payload.get("bonus_days") or 0)
    max_activations = int(payload.get("max_activations") or 0)
    valid_days = payload.get("valid_days")
    if not code or bonus_days <= 0 or max_activations <= 0:
        return _error(400, "invalid_payload")

    valid_until = None
    if valid_days:
        try:
            valid_until = datetime.now(timezone.utc) + timedelta(days=int(valid_days))
        except (TypeError, ValueError):
            return _error(400, "invalid_valid_days")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        existing = await promo_code_dal.get_promo_code_by_code(session, code)
        if existing:
            return _error(409, "duplicate_code")
        promo = await promo_code_dal.create_promo_code(
            session,
            {
                "code": code,
                "bonus_days": bonus_days,
                "max_activations": max_activations,
                "valid_until": valid_until,
                "created_by_admin_id": actor_id,
                "is_active": True,
            },
        )
        await session.commit()
    return _ok({"promo": _serialize_promo(promo)})


async def admin_promo_update_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    promo_id = int(request.match_info["promo_id"])
    payload = await _read_json(request)
    update_data: Dict[str, Any] = {}
    if "is_active" in payload:
        update_data["is_active"] = bool(payload["is_active"])
    if "bonus_days" in payload and payload["bonus_days"] is not None:
        update_data["bonus_days"] = int(payload["bonus_days"])
    if "max_activations" in payload and payload["max_activations"] is not None:
        update_data["max_activations"] = int(payload["max_activations"])

    if not update_data:
        return _error(400, "no_changes")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        promo = await promo_code_dal.update_promo_code(session, promo_id, update_data)
        if not promo:
            return _error(404, "not_found")
        await session.commit()
        await session.refresh(promo)
    return _ok({"promo": _serialize_promo(promo)})


async def admin_promo_delete_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    promo_id = int(request.match_info["promo_id"])
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        promo = await promo_code_dal.delete_promo_code(session, promo_id)
        if not promo:
            return _error(404, "not_found")
        await session.commit()
    return _ok({})


# ─── Logs ──────────────────────────────────────────────────────────


async def admin_logs_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(200, max(1, int(request.query.get("page_size", 50) or 50)))
    user_filter = request.query.get("user_id")

    async with async_session_factory() as session:
        if user_filter:
            try:
                user_id = int(user_filter)
            except (TypeError, ValueError):
                return _error(400, "invalid_user_id")
            entries = await message_log_dal.get_user_message_logs(
                session, user_id, page_size, page * page_size
            )
            total = await message_log_dal.count_user_message_logs(session, user_id)
        else:
            entries = await message_log_dal.get_all_message_logs(
                session, page_size, page * page_size
            )
            total = await message_log_dal.count_all_message_logs(session)

    return _ok(
        {
            "logs": [_serialize_log(l) for l in entries],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )


# ─── Broadcast ─────────────────────────────────────────────────────


async def admin_broadcast_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    payload = await _read_json(request)
    text = str(payload.get("text") or "").strip()
    target = str(payload.get("target") or "all").strip().lower()
    if not text:
        return _error(400, "empty_text")
    if target not in {"all", "active", "inactive"}:
        target = "all"

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        if target == "active":
            user_ids = await user_dal.get_user_ids_with_active_subscription(session)
        elif target == "inactive":
            user_ids = await user_dal.get_user_ids_without_active_subscription(session)
        else:
            user_ids = await user_dal.get_all_active_user_ids_for_broadcast(session)

        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await send_message_via_queue(
                    queue_manager,
                    int(uid),
                    MessageContent(content_type="text", text=text),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent += 1
            except Exception as exc:
                failed += 1
                logger.debug("Broadcast queue failed for %s: %s", uid, exc)

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_broadcast_webapp",
                "content": f"target={target} sent={sent} failed={failed} text={text[:120]}",
                "is_admin_event": True,
            },
        )

    return _ok({"queued": sent, "failed": failed, "target": target})


# ─── Sync ──────────────────────────────────────────────────────────


async def admin_sync_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    panel_service = request.app.get("panel_service")
    if panel_service is None:
        return _error(503, "panel_unavailable")
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    i18n = request.app.get("i18n")

    from bot.handlers.admin.sync_admin import perform_sync

    async with async_session_factory() as session:
        result = await perform_sync(
            panel_service=panel_service,
            session=session,
            settings=settings,
            i18n_instance=i18n,
        )
    return _ok({"result": result or {}})


# ─── Ad campaigns ──────────────────────────────────────────────────


async def admin_ads_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        campaigns = await ad_dal.list_campaigns(session)
        totals = await ad_dal.get_totals(session)
        results = []
        for campaign in campaigns:
            try:
                stats = await ad_dal.get_campaign_stats(session, campaign.ad_campaign_id)
            except Exception:
                stats = {}
            results.append(_serialize_ad(campaign, stats))
    return _ok({"campaigns": results, "totals": totals})


async def admin_ad_create_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    payload = await _read_json(request)
    source = str(payload.get("source") or "").strip()
    start_param = str(payload.get("start_param") or "").strip()
    cost = float(payload.get("cost") or 0.0)
    if not source or not start_param:
        return _error(400, "invalid_payload")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        existing = await ad_dal.get_campaign_by_start_param(session, start_param)
        if existing:
            return _error(409, "duplicate_start_param")
        campaign = await ad_dal.create_campaign(
            session,
            source=source,
            start_param=start_param,
            cost=cost,
        )
        await session.commit()
        await session.refresh(campaign)
    return _ok({"campaign": _serialize_ad(campaign)})


async def admin_ad_toggle_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    payload = await _read_json(request)
    is_active = bool(payload.get("is_active", True))
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        ok = await ad_dal.toggle_campaign_active(session, campaign_id, is_active)
        if not ok:
            return _error(404, "not_found")
        await session.commit()
    return _ok({})


async def admin_ad_delete_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        ok = await ad_dal.delete_campaign(session, campaign_id)
        if not ok:
            return _error(404, "not_found")
        await session.commit()
    return _ok({})


# ─── Settings (manifest + overrides) ───────────────────────────────


async def admin_settings_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        overrides = await app_settings_dal.get_overrides_with_meta(session)

    overrides_by_key = {entry["key"]: entry for entry in overrides}

    fields = manifest_payload()
    sections: Dict[str, Dict[str, Any]] = {}
    for field in fields:
        key = field["key"]
        section_id = field["section"]
        if section_id not in sections:
            sections[section_id] = {
                "id": section_id,
                "order": field["section_order"],
                "fields": [],
            }
        override = overrides_by_key.get(key)
        sections[section_id]["fields"].append(
            {
                **field,
                "value": current_value(settings, key),
                "overridden": bool(override),
                "updated_at": override.get("updated_at") if override else None,
            }
        )

    ordered_sections = sorted(sections.values(), key=lambda s: s["order"])
    return _ok({"sections": ordered_sections})


async def admin_settings_patch_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    payload = await _read_json(request)
    updates = payload.get("updates") or {}
    deletes = payload.get("deletes") or []
    if not isinstance(updates, dict):
        return _error(400, "invalid_updates")
    if not isinstance(deletes, list):
        return _error(400, "invalid_deletes")

    result = await update_overrides(
        settings,
        async_session_factory,
        updates=updates,
        deletes=deletes,
        actor_id=actor_id,
    )
    if not result.get("ok"):
        return web.json_response(
            {"ok": False, "error": "validation_failed", "errors": result.get("errors", {})},
            status=400,
        )

    # Bust the public webapp settings cache so users see new values immediately.
    cache = request.app.get("webapp_settings_cache")
    if isinstance(cache, dict):
        cache["ts"] = 0.0
        cache["data"] = {}

    return _ok({"applied": result.get("applied", 0), "reverted": result.get("reverted", 0)})


# ─── Tariffs catalog ────────────────────────────────────────────────


async def admin_tariffs_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    path = _tariffs_config_path(settings)

    try:
        config = settings.tariffs_config
    except Exception as exc:
        logger.warning("Invalid tariffs config requested from admin UI: %s", exc)
        return _error(400, "invalid_tariffs_config", str(exc))

    if config is None:
        return _ok(
            {
                "exists": path.exists(),
                "path": str(path),
                "catalog": {
                    "default_tariff": "",
                    "topup_packages_default": {"rub": [], "stars": []},
                    "tariffs": [],
                },
            }
        )

    return _ok(
        {
            "exists": True,
            "path": str(path),
            "catalog": _tariffs_config_payload(config),
        }
    )


async def admin_tariffs_save_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    catalog = payload.get("catalog") if "catalog" in payload else payload
    if not isinstance(catalog, dict):
        return _error(400, "invalid_payload", "catalog must be an object")

    try:
        config = TariffsConfig.model_validate(catalog)
    except (ValidationError, ValueError) as exc:
        return _error(400, "invalid_tariffs_config", str(exc))

    path = _tariffs_config_path(settings)
    try:
        _write_tariffs_config_file(path, config)
    except OSError as exc:
        logger.exception("Failed to write tariffs config to %s", path)
        return _error(500, "write_failed", str(exc))

    cache = request.app.get("webapp_settings_cache")
    if isinstance(cache, dict):
        cache["ts"] = 0.0
        cache["data"] = {}

    return _ok({"exists": True, "path": str(path), "catalog": _tariffs_config_payload(config)})


async def admin_panel_internal_squads_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    panel_service = request.app.get("panel_service")
    if panel_service is None:
        return _error(503, "panel_unavailable", "Panel service unavailable")
    try:
        squads = await panel_service.get_internal_squads()
    except Exception as exc:
        logger.exception("Failed to load internal squads from panel")
        return _error(502, "panel_request_failed", str(exc))
    if squads is None:
        return _error(502, "panel_request_failed", "Unable to load internal squads")
    items = []
    for squad in squads:
        if not isinstance(squad, dict):
            continue
        uuid = squad.get("uuid") or squad.get("id")
        if not uuid:
            continue
        items.append(
            {
                "uuid": str(uuid),
                "name": squad.get("name") or squad.get("title") or str(uuid),
                "members_count": squad.get("membersCount") or squad.get("usersCount") or squad.get("members_count"),
                "active_inbounds_count": squad.get("activeInboundsCount") or squad.get("active_inbounds_count"),
            }
        )
    return _ok({"squads": items})


# ─── Router setup ──────────────────────────────────────────────────


def setup_admin_routes(app: web.Application) -> None:
    router = app.router
    router.add_get("/api/admin/me", admin_me_route)
    router.add_get("/api/admin/stats", admin_stats_route)

    router.add_get("/api/admin/users", admin_users_list_route)
    router.add_get("/api/admin/users/{user_id:-?\\d+}", admin_user_detail_route)
    router.add_get("/api/admin/users/{user_id:-?\\d+}/avatar", admin_user_avatar_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/ban", admin_user_ban_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/message", admin_user_message_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/message/preview", admin_user_message_preview_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/reset-trial", admin_user_reset_trial_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/extend", admin_user_extend_route)
    router.add_delete("/api/admin/users/{user_id:-?\\d+}", admin_user_delete_route)

    router.add_get("/api/admin/payments", admin_payments_list_route)
    router.add_get("/api/admin/payments/export.csv", admin_payments_export_route)

    router.add_get("/api/admin/promos", admin_promos_list_route)
    router.add_post("/api/admin/promos", admin_promo_create_route)
    router.add_patch("/api/admin/promos/{promo_id:\\d+}", admin_promo_update_route)
    router.add_delete("/api/admin/promos/{promo_id:\\d+}", admin_promo_delete_route)

    router.add_get("/api/admin/logs", admin_logs_route)

    router.add_post("/api/admin/broadcast", admin_broadcast_route)
    router.add_post("/api/admin/sync", admin_sync_route)

    router.add_get("/api/admin/ads", admin_ads_list_route)
    router.add_post("/api/admin/ads", admin_ad_create_route)
    router.add_post("/api/admin/ads/{campaign_id:\\d+}/toggle", admin_ad_toggle_route)
    router.add_delete("/api/admin/ads/{campaign_id:\\d+}", admin_ad_delete_route)

    router.add_get("/api/admin/settings", admin_settings_get_route)
    router.add_patch("/api/admin/settings", admin_settings_patch_route)

    router.add_get("/api/admin/tariffs", admin_tariffs_get_route)
    router.add_put("/api/admin/tariffs", admin_tariffs_save_route)
    router.add_get("/api/admin/panel/internal-squads", admin_panel_internal_squads_route)
