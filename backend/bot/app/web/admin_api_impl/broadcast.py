import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, cast

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot_username,
    get_i18n,
    get_optional_subscription_service,
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    INTEGER_SCHEMA,
    STRING_SCHEMA,
    RouteContract,
    ok_envelope_for,
    ok_envelope_with,
    register_contract,
)
from bot.services.audience_segmentation import (
    AUDIENCE_ACTIVE_NEVER_CONNECTED,
    AUDIENCE_ADMINS,
    AUDIENCE_TARGETS,
    AudienceSegmentationService,
)
from bot.services.broadcast_email_service import (
    BroadcastEmailRecipient,
    schedule_broadcast_emails,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from db.dal import message_log_dal, promo_code_dal, user_dal
from db.models import Subscription, User

from .auth import (
    _require_admin_user_id,
)
from .broadcast_content import (
    BroadcastValidationError,
    broadcast_promo_codes,
    email_links_for_buttons,
    normalize_broadcast_channels,
    resolve_broadcast_buttons,
    telegram_markup_for_buttons,
)
from .common import (
    _error,
    _ok,
    _panel_user_connection_activity,
)
from .response_schemas import AdminBroadcastAudienceCountsOut
from .schemas import AdminBroadcastBody

logger = logging.getLogger(__name__)

BROADCAST_TARGET_ACTIVE_NEVER_CONNECTED = AUDIENCE_ACTIVE_NEVER_CONNECTED
BROADCAST_TARGETS = AUDIENCE_TARGETS
PANEL_ACTIVITY_LOOKUP_CONCURRENCY = 10
_ADMIN_BROADCAST_AUDIENCE_COUNT_CACHES: dict[tuple[int, int], AsyncTTLCache] = {}

register_contract(
    "admin_broadcast_route",
    RouteContract(
        request_model=AdminBroadcastBody,
        response_schema=ok_envelope_with(
            {
                "queued": INTEGER_SCHEMA,
                "failed": INTEGER_SCHEMA,
                "email_queued": INTEGER_SCHEMA,
                "target": STRING_SCHEMA,
                "channels": {"type": "array", "items": STRING_SCHEMA},
            }
        ),
    ),
)
register_contract(
    "admin_broadcast_audience_counts_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBroadcastAudienceCountsOut),
        models=(AdminBroadcastAudienceCountsOut,),
    ),
)


def _resolve_panel_service(request: web.Request) -> Any:
    subscription_service = get_optional_subscription_service(request)
    return getattr(subscription_service, "panel_service", None)


def _resolve_audience_service(request: web.Request) -> AudienceSegmentationService:
    service = request.app.get("audience_segmentation_service")
    if isinstance(service, AudienceSegmentationService):
        return service
    settings: Settings = get_settings(request)
    return AudienceSegmentationService(
        get_session_factory(request),
        panel_service=_resolve_panel_service(request),
        admin_ids=settings.ADMIN_IDS,
    )


async def _active_subscription_panel_uuids_by_user(
    session: AsyncSession,
) -> dict[int, list[str]]:
    now = datetime.now(UTC)
    stmt = (
        select(Subscription.user_id, Subscription.panel_user_uuid)
        .join(User, Subscription.user_id == User.user_id)
        .where(
            User.is_banned == False,
            Subscription.is_active == True,
            Subscription.end_date > now,
            Subscription.panel_user_uuid.is_not(None),
            Subscription.panel_user_uuid != "",
        )
        .order_by(Subscription.user_id.asc(), Subscription.end_date.desc())
    )
    result = await session.execute(stmt)

    grouped: dict[int, list[str]] = defaultdict(list)
    seen: dict[int, set[str]] = defaultdict(set)
    for user_id, panel_uuid in result.all():
        user_id_int = int(user_id)
        panel_uuid_str = str(panel_uuid or "").strip()
        if panel_uuid_str and panel_uuid_str not in seen[user_id_int]:
            grouped[user_id_int].append(panel_uuid_str)
            seen[user_id_int].add(panel_uuid_str)
    return dict(grouped)


async def _panel_connection_status(panel_service: Any, panel_uuid: str) -> str:
    try:
        panel_user = await panel_service.get_user_by_uuid(panel_uuid)
    except Exception as exc:
        logger.warning("Failed to fetch panel user activity uuid=%s: %s", panel_uuid, exc)
        return "unknown"
    activity = _panel_user_connection_activity(panel_user)
    return str(activity.get("status") or "unknown")


async def _user_ids_with_active_subscription_never_connected(
    session: AsyncSession,
    panel_service: Any,
) -> list[int]:
    panel_uuids_by_user = await _active_subscription_panel_uuids_by_user(session)
    semaphore = asyncio.Semaphore(PANEL_ACTIVITY_LOOKUP_CONCURRENCY)

    async def lookup(panel_uuid: str) -> str:
        async with semaphore:
            return await _panel_connection_status(panel_service, panel_uuid)

    panel_uuids = list(
        dict.fromkeys(
            panel_uuid
            for user_panel_uuids in panel_uuids_by_user.values()
            for panel_uuid in user_panel_uuids
        )
    )
    statuses_by_uuid = dict(
        zip(
            panel_uuids,
            await asyncio.gather(*(lookup(uuid) for uuid in panel_uuids)),
            strict=True,
        )
    )

    user_ids: list[int] = []
    for user_id, panel_uuids in panel_uuids_by_user.items():
        statuses = [statuses_by_uuid.get(panel_uuid, "unknown") for panel_uuid in panel_uuids]
        if statuses and all(status == "never" for status in statuses):
            user_ids.append(user_id)
    return user_ids


def _admin_broadcast_audience_counts_cache(settings: Settings) -> AsyncTTLCache | None:
    ttl_seconds = int(settings.ADMIN_BROADCAST_AUDIENCE_COUNTS_CACHE_TTL_SECONDS or 0)
    if ttl_seconds <= 0:
        return None
    cache_key = (id(settings), ttl_seconds)
    cache = _ADMIN_BROADCAST_AUDIENCE_COUNT_CACHES.get(cache_key)
    if cache is None:
        cache = AsyncTTLCache(
            ttl_seconds=ttl_seconds,
            settings=settings,
            namespace="admin:broadcast_audience_counts",
        )
        _ADMIN_BROADCAST_AUDIENCE_COUNT_CACHES[cache_key] = cache
    return cache


async def _load_broadcast_audience_counts(
    settings: Settings,
    async_session_factory: sessionmaker,
    panel_service: Any,
) -> dict[str, int | None]:
    cache = _admin_broadcast_audience_counts_cache(settings)
    if cache is None:
        return await _load_broadcast_audience_counts_uncached(
            async_session_factory,
            panel_service,
            admin_ids=settings.ADMIN_IDS,
        )
    cache_key = "with-panel" if panel_service is not None else "without-panel"
    return cast(
        dict[str, int | None],
        await cache.get_or_load(
            cache_key,
            lambda: _load_broadcast_audience_counts_uncached(
                async_session_factory,
                panel_service,
                admin_ids=settings.ADMIN_IDS,
            ),
        ),
    )


async def _load_broadcast_audience_counts_uncached(
    async_session_factory: sessionmaker,
    panel_service: Any,
    *,
    admin_ids: list[int] | None = None,
) -> dict[str, int | None]:
    async with async_session_factory() as session:
        counts: dict[str, int | None] = {
            "all": await user_dal.count_all_active_users_for_broadcast(session),
            "active": await user_dal.count_users_with_active_subscription_for_broadcast(session),
            "inactive": await user_dal.count_users_without_active_subscription_for_broadcast(
                session
            ),
            "expired": await user_dal.count_users_with_expired_subscription_for_broadcast(session),
            "never": await user_dal.count_users_without_any_subscription_for_broadcast(session),
            BROADCAST_TARGET_ACTIVE_NEVER_CONNECTED: None,
            AUDIENCE_ADMINS: len(dict.fromkeys(admin_ids or [])),
        }
        if panel_service is not None:
            counts[BROADCAST_TARGET_ACTIVE_NEVER_CONNECTED] = len(
                await _user_ids_with_active_subscription_never_connected(
                    session,
                    panel_service,
                )
            )
    return counts


async def _validate_broadcast_promo_codes(
    session: AsyncSession,
    promo_codes: list[str],
) -> web.Response | None:
    """Catch admin typos before anything is queued: codes must exist and be live."""
    for code in promo_codes:
        promo = await promo_code_dal.get_promo_code_by_code(session, code)
        if promo is None:
            return _error(400, "promo_code_not_found", code)
        if promo.__dict__.get("archived_at") is not None or not bool(
            promo.__dict__.get("is_active")
        ):
            return _error(400, "promo_code_inactive", code)
    return None


async def admin_broadcast_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminBroadcastBody)
    settings: Settings = get_settings(request)
    text = str(body.text or "").strip()
    target = str(body.target or "all").strip().lower()
    if not text:
        return _error(400, "empty_text")
    if target not in BROADCAST_TARGETS:
        target = "all"

    try:
        channels = normalize_broadcast_channels(body.channels)
        buttons = resolve_broadcast_buttons(
            body.buttons,
            settings=settings,
            bot_username=get_bot_username(request),
        )
    except BroadcastValidationError as exc:
        return _error(400, exc.code, exc.detail)

    telegram_enabled = "telegram" in channels
    email_enabled = "email" in channels
    if email_enabled and not settings.email_auth_configured:
        return _error(503, "email_not_configured")

    queue_manager = get_queue_manager() if telegram_enabled else None
    if telegram_enabled and not queue_manager:
        return _error(503, "queue_unavailable")

    if (
        target == BROADCAST_TARGET_ACTIVE_NEVER_CONNECTED
        and _resolve_panel_service(request) is None
    ):
        return _error(503, "panel_service_unavailable")

    audience_service = _resolve_audience_service(request)
    user_ids = [int(uid) for uid in await audience_service.resolve_user_ids(target)]
    promo_codes = broadcast_promo_codes(buttons)
    markup = telegram_markup_for_buttons(buttons)

    async_session_factory: sessionmaker = get_session_factory(request)
    sent = 0
    failed = 0
    email_queued = 0
    async with async_session_factory() as session:
        promo_error = await _validate_broadcast_promo_codes(session, promo_codes)
        if promo_error is not None:
            return promo_error

        if telegram_enabled and queue_manager is not None:
            for uid in user_ids:
                try:
                    await send_message_via_queue(
                        queue_manager,
                        uid,
                        MessageContent(content_type="text", text=text),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=markup,
                    )
                    sent += 1
                except Exception as exc:
                    failed += 1
                    logger.debug("Broadcast queue failed for %s: %s", uid, exc)

        if email_enabled:
            recipients = [
                BroadcastEmailRecipient(user_id=uid, email=email, language_code=language)
                for uid, email, language in await user_dal.get_email_recipients_for_broadcast(
                    session, user_ids
                )
            ]
            email_queued = schedule_broadcast_emails(
                settings=settings,
                i18n=get_i18n(request),
                recipients=recipients,
                subject=str(body.email_subject or ""),
                message_text=text,
                buttons=email_links_for_buttons(buttons),
                session_factory=async_session_factory,
                actor_id=actor_id,
                target=target,
            )

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_broadcast_webapp",
                "content": (
                    f"target={target} channels={','.join(channels)} sent={sent} "
                    f"failed={failed} email_queued={email_queued} "
                    f"buttons={len(buttons)} text={text[:120]}"
                ),
                "is_admin_event": True,
            },
        )

    return _ok(
        {
            "queued": sent,
            "failed": failed,
            "email_queued": email_queued,
            "target": target,
            "channels": channels,
        }
    )


async def admin_broadcast_audience_counts_route(request: web.Request) -> web.Response:
    """Return how many users each broadcast audience currently resolves to."""
    _require_admin_user_id(request)

    settings: Settings = get_settings(request)
    service = request.app.get("audience_segmentation_service")
    if isinstance(service, AudienceSegmentationService):
        counts = await service.counts()
    else:
        async_session_factory: sessionmaker = get_session_factory(request)
        panel_service = _resolve_panel_service(request)
        counts = await _load_broadcast_audience_counts(
            settings,
            async_session_factory,
            panel_service,
        )

    return _ok(
        AdminBroadcastAudienceCountsOut(
            counts=counts,
            email_enabled=bool(settings.email_auth_configured),
        ).model_dump(mode="json")
    )
