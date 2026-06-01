# ruff: noqa: F401,F403,F405,I001
import asyncio

from ._runtime import *  # noqa: F403,F405
from .auth import _require_admin_user_id
from .common import _ok, _serialize_payment
from bot.utils.ttl_cache import AsyncTTLCache

_ADMIN_PANEL_STATS_CACHES: Dict[tuple[int, int], AsyncTTLCache] = {}
_ADMIN_DB_STATS_CACHES: Dict[tuple[int, int], AsyncTTLCache] = {}


async def admin_me_route(request: web.Request) -> web.Response:
    user_id = _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    return _ok({}, user_id=user_id, admin_ids=list(settings.ADMIN_IDS or []))


async def admin_stats_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    payload = dict(await _load_admin_db_stats(settings, async_session_factory))

    panel_service = request.app.get("panel_service")
    if panel_service is not None:
        payload["panel"] = await _load_admin_panel_stats(request, settings, panel_service)

    queue_manager = get_queue_manager()
    if queue_manager:
        try:
            payload["queue"] = queue_manager.get_queue_stats()
        except Exception:  # pragma: no cover - defensive
            payload["queue"] = None

    payload["currency_symbol"] = default_payment_currency_code_for_settings(settings)
    return _ok(payload)


async def _load_admin_db_stats(
    settings: Settings,
    async_session_factory: sessionmaker,
) -> Dict[str, Any]:
    cache = _admin_db_stats_cache(settings)
    if cache is None:
        return await _load_admin_db_stats_uncached(async_session_factory)
    return await cache.get_or_load(
        "db",
        lambda: _load_admin_db_stats_uncached(async_session_factory),
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
        "panel_sync": {
            "status": sync_status.status if sync_status else "never_run",
            "last_sync_time": sync_status.last_sync_time.isoformat()
            if sync_status and sync_status.last_sync_time
            else None,
            "details": sync_status.details if sync_status else None,
            "users_processed": sync_status.users_processed_from_panel if sync_status else 0,
            "subscriptions_synced": sync_status.subscriptions_synced if sync_status else 0,
        },
        "recent_payments": [_serialize_payment(p) for p in recent_payments],
    }


def _admin_db_stats_cache(settings: Settings) -> Optional[AsyncTTLCache]:
    ttl_seconds = int(getattr(settings, "ADMIN_DB_STATS_CACHE_TTL_SECONDS", 5) or 0)
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
    panel_service,
) -> Dict[str, Any]:
    cache = _admin_panel_stats_cache(settings)
    if cache is None:
        return await _load_admin_panel_stats_uncached(panel_service)
    return await cache.get_or_load("panel", lambda: _load_admin_panel_stats_uncached(panel_service))


def _admin_panel_stats_cache(settings: Settings) -> Optional[AsyncTTLCache]:
    ttl_seconds = int(getattr(settings, "ADMIN_PANEL_STATS_CACHE_TTL_SECONDS", 15) or 0)
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


async def _load_admin_panel_stats_uncached(panel_service) -> Dict[str, Any]:
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


async def _safe_panel_call(awaitable, label: str) -> Any:
    try:
        return await awaitable
    except Exception as exc:  # pragma: no cover - optional panel endpoints
        logger.debug("Panel %s unavailable: %s", label, exc)
        return None
