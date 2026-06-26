# ruff: noqa: F401,F403,F405,I001
from collections.abc import Awaitable
from typing import cast

from bot.app.web.context import (
    get_panel_service,
    get_session_factory,
    get_settings,
)

import asyncio


from aiohttp import web
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.utils.message_queue import get_queue_manager
from config.settings import Settings
from config.tariffs_config import default_payment_currency_code_for_settings
from datetime import datetime, timedelta, timezone
from db.dal import panel_sync_dal, payment_dal, user_dal
from .schemas import AdminMeOut, AdminPanelSyncOut, AdminStatsOut, PaymentOut
from sqlalchemy.orm import sessionmaker
from typing import Any, Dict, Optional
import logging
from .auth import _require_admin_user_id
from .common import (
    _enrich_bandwidth_nodes_with_online,
    _ok,
    _panel_nodes_online_by_uuid,
    _serialize_payment,
)
from bot.utils.ttl_cache import AsyncTTLCache

logger = logging.getLogger(__name__)

_ADMIN_PANEL_STATS_CACHES: Dict[tuple[int, int], AsyncTTLCache] = {}
_ADMIN_DB_STATS_CACHES: Dict[tuple[int, int], AsyncTTLCache] = {}


register_contract(
    "admin_me_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminMeOut),
        models=(AdminMeOut,),
    ),
)
register_contract(
    "admin_stats_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminStatsOut),
        models=(AdminStatsOut, AdminPanelSyncOut, PaymentOut),
    ),
)


async def admin_me_route(request: web.Request) -> web.Response:
    user_id = _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    return _ok(AdminMeOut(user_id=user_id, admin_ids=list(settings.ADMIN_IDS or [])).model_dump())


async def admin_stats_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    payload = dict(await _load_admin_db_stats(settings, async_session_factory))

    panel_service = get_panel_service(request)
    if panel_service is not None:
        payload["panel"] = await _load_admin_panel_stats(request, settings, panel_service)

    queue_manager = get_queue_manager()
    if queue_manager:
        try:
            payload["queue"] = queue_manager.get_queue_stats()
        except Exception:  # pragma: no cover - defensive
            payload["queue"] = None

    payload["currency_symbol"] = default_payment_currency_code_for_settings(settings)
    return _ok(AdminStatsOut.model_validate(payload).model_dump(mode="json", exclude_none=True))


async def _load_admin_db_stats(
    settings: Settings,
    async_session_factory: sessionmaker,
) -> Dict[str, Any]:
    cache = _admin_db_stats_cache(settings)
    if cache is None:
        return await _load_admin_db_stats_uncached(async_session_factory)
    return cast(
        Dict[str, Any],
        await cache.get_or_load(
            "db",
            lambda: _load_admin_db_stats_uncached(async_session_factory),
        ),
    )


async def _load_admin_db_stats_uncached(async_session_factory: sessionmaker) -> Dict[str, Any]:
    async with async_session_factory() as session:
        user_stats = await user_dal.get_enhanced_user_statistics(session)
        financial_stats = await payment_dal.get_financial_statistics(session)
        sync_status = await panel_sync_dal.get_panel_sync_status(session)
        recent_payments = await payment_dal.get_recent_payment_logs_with_user(session, limit=10)

    return {
        "users": user_stats,
        "financial": financial_stats,
        "panel_sync": AdminPanelSyncOut.from_sync_status(sync_status).model_dump(mode="json"),
        "recent_payments": [_serialize_payment(p) for p in recent_payments],
    }


def _admin_db_stats_cache(settings: Settings) -> Optional[AsyncTTLCache]:
    ttl_seconds = int(settings.ADMIN_DB_STATS_CACHE_TTL_SECONDS or 0)
    if ttl_seconds <= 0:
        return None
    cache_key = (id(settings), ttl_seconds)
    cache = _ADMIN_DB_STATS_CACHES.get(cache_key)
    if cache is None:
        cache = AsyncTTLCache(
            ttl_seconds=ttl_seconds,
            settings=settings,
            namespace="admin:db_stats",
        )
        _ADMIN_DB_STATS_CACHES[cache_key] = cache
    return cache


async def _load_admin_panel_stats(
    request: web.Request,
    settings: Settings,
    panel_service: Any,
) -> Dict[str, Any]:
    cache = _admin_panel_stats_cache(settings)
    if cache is None:
        return await _load_admin_panel_stats_uncached(panel_service)
    return cast(
        Dict[str, Any],
        await cache.get_or_load("panel", lambda: _load_admin_panel_stats_uncached(panel_service)),
    )


def _admin_panel_stats_cache(settings: Settings) -> Optional[AsyncTTLCache]:
    ttl_seconds = int(settings.ADMIN_PANEL_STATS_CACHE_TTL_SECONDS or 0)
    if ttl_seconds <= 0:
        return None
    cache_key = (id(settings), ttl_seconds)
    cache = _ADMIN_PANEL_STATS_CACHES.get(cache_key)
    if cache is None:
        cache = AsyncTTLCache(
            ttl_seconds=ttl_seconds,
            settings=settings,
            namespace="admin:panel_stats",
        )
        _ADMIN_PANEL_STATS_CACHES[cache_key] = cache
    return cache


async def _load_admin_panel_stats_uncached(panel_service: Any) -> Dict[str, Any]:
    try:
        today = datetime.now(timezone.utc).date()
        start_d = today - timedelta(days=7)
        system, bandwidth, nodes, nodes_bw, lookups = await asyncio.gather(
            _safe_panel_call(panel_service.get_system_stats(), "system stats"),
            _safe_panel_call(panel_service.get_bandwidth_stats(), "bandwidth stats"),
            _safe_panel_call(panel_service.get_nodes_statistics(), "nodes stats"),
            _safe_panel_call(
                panel_service.get_nodes_bandwidth_usage(
                    start=start_d.isoformat(),
                    end=today.isoformat(),
                    top_nodes_limit=64,
                ),
                "nodes bandwidth range",
            ),
            _safe_panel_call(panel_service.get_nodes_online_lookups(), "nodes online lookups"),
        )

        panel_body: Dict[str, Any] = {
            "system": system or {},
            "bandwidth": bandwidth or {},
            "nodes": nodes or {},
            "nodes_bandwidth": nodes_bw or {},
        }
        if isinstance(lookups, dict):
            try:
                online_map = _panel_nodes_online_by_uuid(panel_body.get("nodes"))
                for k, v in lookups.get("byUuid", {}).items():
                    online_map[k] = v
                _enrich_bandwidth_nodes_with_online(
                    panel_body.get("nodes_bandwidth"),
                    online_map,
                    lookups.get("byName") or {},
                )
            except Exception as exc_merge:  # pragma: no cover
                logger.debug("Panel nodes online merge skipped: %s", exc_merge)
        return panel_body
    except Exception as exc:
        logger.debug("Panel stats unavailable: %s", exc)
        return {"error": "unavailable"}


async def _safe_panel_call(awaitable: Awaitable[Any], label: str) -> Any:
    try:
        return await awaitable
    except Exception as exc:  # pragma: no cover - optional panel endpoints
        logger.debug("Panel %s unavailable: %s", label, exc)
        return None
