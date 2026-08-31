import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

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
from bot.services.partner_common import currency_scale
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from db.dal import partner_dal, user_balance_dal
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
) -> dict[str, Any]:
    cache = _admin_users_list_cache(settings)
    valid_tariff_keys = _admin_tariff_keys(settings)
    balance_config = settings.balance_settings
    balance_enabled = bool(balance_config.enabled)
    partner_balance_enabled = bool(settings.partner_settings.enabled)
    balance_currency = str(balance_config.currency).upper()
    balance_currency_scale = currency_scale(balance_currency)
    cache_key = _admin_users_list_cache_key(
        page=page,
        page_size=page_size,
        query=query,
        filter_value=filter_value,
        panel_status=panel_status,
        premium_traffic=premium_traffic,
        sort_value=sort_value,
        valid_tariff_keys=sorted(valid_tariff_keys),
        balance_enabled=balance_enabled,
        partner_balance_enabled=partner_balance_enabled,
        balance_currency=balance_currency,
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
            valid_tariff_keys=valid_tariff_keys,
            balance_enabled=balance_enabled,
            partner_balance_enabled=partner_balance_enabled,
            balance_currency=balance_currency,
            balance_currency_scale=balance_currency_scale,
        )
    return cast(
        dict[str, Any],
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
                valid_tariff_keys=valid_tariff_keys,
                balance_enabled=balance_enabled,
                partner_balance_enabled=partner_balance_enabled,
                balance_currency=balance_currency,
                balance_currency_scale=balance_currency_scale,
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
    valid_tariff_keys: set[str],
    balance_enabled: bool,
    partner_balance_enabled: bool,
    balance_currency: str,
    balance_currency_scale: int,
) -> dict[str, Any]:
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
            valid_tariff_keys=valid_tariff_keys,
        )

        user_ids = [int(user.user_id) for user in users]
        statuses = await _bulk_user_statuses(session, user_ids)
        cached_avatar_ids = await _bulk_user_avatar_keys(session, user_ids)
        active_subs = await _bulk_active_subscriptions_for_users(session, user_ids)
        payment_summaries = await _bulk_user_payment_summaries(session, user_ids)
        referral_counts = await _bulk_user_referral_counts(session, user_ids)
        user_balances = (
            await user_balance_dal.balance_minor_by_user_ids(
                session,
                user_ids,
                balance_currency,
            )
            if balance_enabled
            else {}
        )
        partner_balances = (
            await partner_dal.balance_minor_by_user_ids(
                session,
                user_ids,
                balance_currency,
            )
            if partner_balance_enabled
            else {}
        )

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
        payload["user_balance_amount_minor"] = int(user_balances.get(user.user_id) or 0)
        payload["partner_balance_amount_minor"] = int(partner_balances.get(user.user_id) or 0)
        serialized.append(payload)

    return {
        "users": serialized,
        "page": page,
        "page_size": page_size,
        "total": total,
        "user_balance_enabled": balance_enabled,
        "partner_balance_enabled": partner_balance_enabled,
        "balance_currency": balance_currency,
        "balance_currency_scale": balance_currency_scale,
    }


def _admin_users_list_cache(settings: Settings) -> AsyncTTLCache | None:
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
    user_id: int | None = None,
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


def _enabled_admin_tariffs(settings: Settings) -> list[Any]:
    config = settings.tariffs_config
    if not config:
        return []
    return list(getattr(config, "enabled_tariffs", []) or [])


def _admin_tariff_keys(settings: Settings) -> set[str]:
    config = settings.tariffs_config
    if not config:
        return set()
    return {
        str(tariff.key)
        for tariff in getattr(config, "tariffs", []) or []
        if str(getattr(tariff, "key", "") or "")
    }


def _enabled_admin_period_tariffs(settings: Settings) -> list[Any]:
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
) -> tuple[str | None, str | None]:
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
    session: AsyncSession, user_ids: list[int]
) -> dict[int, dict[str, str | None]]:
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
    out: dict[int, dict[str, str | None]] = {}
    now = datetime.now(UTC)
    for uid, panel_status, is_active, end_date in rows:
        if uid in out:
            continue
        if is_active and (end_date is None or end_date > now):
            status = (panel_status or "active").lower()
        elif end_date and end_date <= now:
            status = "expired"
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
