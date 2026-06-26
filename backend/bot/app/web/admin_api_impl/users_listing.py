import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple, cast

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
    get_settings,
)
from bot.app.web.webapp.cache_helpers import invalidate_webapp_user_caches
from bot.infra.redis import cache_delete_pattern, redis_key
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from db.models import Subscription

from .auth import _require_admin_user_id
from .common import (
    _ok,
    _premium_traffic_list_payload,
    _serialize_user,
)
from .users_common import (
    _ADMIN_USERS_LIST_CACHES,
    _bulk_user_avatar_keys,
)
from .users_detail import (
    _bulk_active_subscriptions_for_users,
    _bulk_user_payment_summaries,
    _bulk_user_referral_counts,
    _filter_and_sort_users,
)


async def admin_users_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    query = (request.query.get("q") or "").strip()
    filter_value = (request.query.get("filter") or "all").lower()
    panel_status = (request.query.get("panel_status") or "all").lower()
    premium_traffic = (request.query.get("premium_traffic") or "all").lower()
    sort_value = (request.query.get("sort") or "registered_desc").lower()

    payload = await _load_admin_users_list_payload(
        settings,
        async_session_factory,
        page=page,
        page_size=page_size,
        query=query,
        filter_value=filter_value,
        panel_status=panel_status,
        premium_traffic=premium_traffic,
        sort_value=sort_value,
    )
    return _ok(payload)


async def _load_admin_users_list_payload(
    settings: Settings,
    async_session_factory: sessionmaker,
    *,
    page: int,
    page_size: int,
    query: str,
    filter_value: str,
    panel_status: str,
    premium_traffic: str,
    sort_value: str,
) -> Dict[str, Any]:
    cache = _admin_users_list_cache(settings)
    cache_key = _admin_users_list_cache_key(
        page=page,
        page_size=page_size,
        query=query,
        filter_value=filter_value,
        panel_status=panel_status,
        premium_traffic=premium_traffic,
        sort_value=sort_value,
    )
    if cache is None:
        return await _load_admin_users_list_payload_uncached(
            async_session_factory,
            page=page,
            page_size=page_size,
            query=query,
            filter_value=filter_value,
            panel_status=panel_status,
            premium_traffic=premium_traffic,
            sort_value=sort_value,
        )
    return cast(
        Dict[str, Any],
        await cache.get_or_load(
            cache_key,
            lambda: _load_admin_users_list_payload_uncached(
                async_session_factory,
                page=page,
                page_size=page_size,
                query=query,
                filter_value=filter_value,
                panel_status=panel_status,
                premium_traffic=premium_traffic,
                sort_value=sort_value,
            ),
        ),
    )


async def _load_admin_users_list_payload_uncached(
    async_session_factory: sessionmaker,
    *,
    page: int,
    page_size: int,
    query: str,
    filter_value: str,
    panel_status: str,
    premium_traffic: str,
    sort_value: str,
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        users, total = await _filter_and_sort_users(
            session,
            query=query,
            filter_value=filter_value,
            panel_status=panel_status,
            premium_traffic=premium_traffic,
            sort_value=sort_value,
            page=page,
            page_size=page_size,
        )

        statuses = await _bulk_user_statuses(session, [u.user_id for u in users])
        cached_avatar_ids = await _bulk_user_avatar_keys(session, [u.user_id for u in users])
        active_subs = await _bulk_active_subscriptions_for_users(
            session, [u.user_id for u in users]
        )
        payment_summaries = await _bulk_user_payment_summaries(session, [u.user_id for u in users])
        referral_counts = await _bulk_user_referral_counts(session, [u.user_id for u in users])

    serialized = []
    for user in users:
        payload = _serialize_user(user)
        status_payload = statuses.get(user.user_id) or {"status": "bot_only", "end_date": None}
        payload["panel_status"] = status_payload.get("status")
        payload["subscription_expires_at"] = status_payload.get("end_date")
        if status_payload.get("status") == "expired" and status_payload.get("end_date"):
            payload["panel_status_expired_at"] = status_payload["end_date"]
        payload["avatar_url"] = (
            f"/api/admin/users/{user.user_id}/avatar?v={cached_avatar_ids[user.user_id]}"
            if user.user_id in cached_avatar_ids
            else None
        )
        payload["premium_traffic"] = _premium_traffic_list_payload(active_subs.get(user.user_id))
        payment_summary = payment_summaries.get(user.user_id) or {}
        payload["payments_total_amount"] = float(payment_summary.get("total_amount") or 0)
        payload["payments_count"] = int(payment_summary.get("count") or 0)
        payload["payments_currency"] = payment_summary.get("currency")
        payload["invited_users_count"] = int(referral_counts.get(user.user_id) or 0)
        serialized.append(payload)

    return {
        "users": serialized,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def _admin_users_list_cache(settings: Settings) -> Optional[AsyncTTLCache]:
    ttl_seconds = int(settings.ADMIN_USERS_LIST_CACHE_TTL_SECONDS or 0)
    if ttl_seconds <= 0:
        return None
    cache_key = (id(settings), ttl_seconds)
    cache = _ADMIN_USERS_LIST_CACHES.get(cache_key)
    if cache is None:
        cache = AsyncTTLCache(
            ttl_seconds=ttl_seconds,
            settings=settings,
            namespace="admin:users_list",
        )
        _ADMIN_USERS_LIST_CACHES[cache_key] = cache
    return cache


def _admin_users_list_cache_key(**params: Any) -> str:
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _invalidate_admin_users_list_cache(settings: Settings) -> None:
    for settings_id, _ttl in tuple(_ADMIN_USERS_LIST_CACHES):
        if settings_id == id(settings):
            _ADMIN_USERS_LIST_CACHES[(settings_id, _ttl)].invalidate()
    try:
        await cache_delete_pattern(settings, redis_key(settings, "cache", "admin:users_list", "*"))
    except Exception:
        return


async def _invalidate_after_admin_user_mutation(
    settings: Settings,
    user_id: Optional[int] = None,
    *,
    include_devices: bool = True,
) -> None:
    await _invalidate_admin_users_list_cache(settings)
    if user_id is not None:
        await invalidate_webapp_user_caches(
            settings,
            user_id,
            include_devices=include_devices,
        )


def _enabled_admin_tariffs(settings: Settings) -> List[Any]:
    config = settings.tariffs_config
    if not config:
        return []
    return list(getattr(config, "enabled_tariffs", []) or [])


def _enabled_admin_period_tariffs(settings: Settings) -> List[Any]:
    return [
        tariff
        for tariff in _enabled_admin_tariffs(settings)
        if getattr(tariff, "billing_model", None) == "period"
    ]


def _resolve_admin_period_tariff_key(
    settings: Settings,
    explicit_tariff_key: Any,
    *,
    allow_legacy_without_tariffs: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    config = settings.tariffs_config
    if not config:
        return (None, None) if allow_legacy_without_tariffs else (None, "tariffs_not_configured")

    explicit = str(explicit_tariff_key or "").strip()
    if explicit:
        try:
            tariff = config.require(explicit)
        except Exception:
            return None, "invalid_tariff"
        if getattr(tariff, "billing_model", None) != "period":
            return None, "invalid_tariff"
        return str(tariff.key), None

    enabled_tariffs = _enabled_admin_tariffs(settings)
    period_tariffs = _enabled_admin_period_tariffs(settings)
    if len(enabled_tariffs) == 1 and period_tariffs:
        return str(period_tariffs[0].key), None
    if not period_tariffs:
        return None, "no_period_tariffs"
    return None, "tariff_required"


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
        select(
            Subscription.user_id,
            Subscription.status_from_panel,
            Subscription.is_active,
            Subscription.end_date,
        )
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
