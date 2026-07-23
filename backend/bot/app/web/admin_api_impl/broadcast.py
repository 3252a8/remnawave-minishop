import logging
from typing import Any, cast

from aiohttp import web
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
    AudienceNotFoundError,
    AudienceSegmentationService,
    AudienceUnavailableError,
)
from bot.services.broadcast_email_service import (
    BroadcastEmailRecipient,
    schedule_broadcast_emails,
)
from bot.services.broadcast_personalization import (
    BroadcastUserContext,
    known_shortcodes,
    load_broadcast_contexts,
    render_broadcast_text,
    telegram_html_error,
    unknown_shortcodes,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from db.dal import message_log_dal, promo_code_dal, user_dal

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
)
from .response_schemas import AdminBroadcastAudienceCountsOut, AdminBroadcastAudienceOut
from .schemas import AdminBroadcastBody

logger = logging.getLogger(__name__)

BROADCAST_TARGET_ACTIVE_NEVER_CONNECTED = AUDIENCE_ACTIVE_NEVER_CONNECTED
BROADCAST_TARGETS = AUDIENCE_TARGETS
# Telegram rejects messages over 4096 chars; a shortcode expansion can push a
# per-recipient message past the limit, so we skip+count those rather than let
# the queue fail them later with an opaque error.
TELEGRAM_MESSAGE_MAX_LENGTH = 4096
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
        models=(AdminBroadcastAudienceCountsOut, AdminBroadcastAudienceOut),
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
    service = AudienceSegmentationService(cast(sessionmaker, None))
    entries_by_user = await service._active_subscription_panel_uuids_by_user(session)
    return {
        user_id: [panel_uuid for panel_uuid, _last_connected_at in entries]
        for user_id, entries in entries_by_user.items()
    }


async def _user_ids_with_active_subscription_never_connected(
    session: AsyncSession,
    panel_service: Any,
) -> list[int]:
    service = AudienceSegmentationService(
        cast(sessionmaker, None),
        panel_service=panel_service,
    )
    return await service._user_ids_with_active_subscription_never_connected(session)


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

    email_subject = str(body.email_subject or "")
    unknown = unknown_shortcodes(text)
    if email_enabled:
        unknown |= unknown_shortcodes(email_subject)
    if unknown:
        return _error(400, "unknown_shortcode", ", ".join(sorted(unknown)))
    html_error = telegram_html_error(text)
    if html_error:
        return _error(400, "invalid_telegram_html", html_error)
    needed = known_shortcodes(text)
    if email_enabled:
        needed |= known_shortcodes(email_subject)
    personalize = bool(needed)
    i18n = get_i18n(request)
    bot_username = get_bot_username(request)

    audience_service = _resolve_audience_service(request)
    try:
        user_ids = [int(uid) for uid in await audience_service.resolve_user_ids(target)]
    except AudienceNotFoundError:
        return _error(400, "invalid_audience", target)
    except AudienceUnavailableError:
        return _error(403, "audience_unavailable", target)
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

        contexts: dict[int, BroadcastUserContext] = {}
        if personalize:
            contexts = await load_broadcast_contexts(
                session,
                settings,
                user_ids,
                needed,
                _resolve_panel_service(request),
            )

        def _render(template: str, uid: int, fallback_lang: str | None, *, escape: bool) -> str:
            ctx = contexts.get(uid)
            lang = (
                (ctx.language_code if ctx else None) or fallback_lang or settings.DEFAULT_LANGUAGE
            )
            return render_broadcast_text(
                template,
                ctx,
                lang=lang,
                i18n=i18n,
                settings=settings,
                bot_username=bot_username,
                escape=escape,
            )

        if telegram_enabled and queue_manager is not None:
            telegram_recipients = await user_dal.get_telegram_recipients_for_broadcast(
                session, user_ids
            )
            for uid, chat_id in telegram_recipients:
                message_text = _render(text, uid, None, escape=True) if personalize else text
                if len(message_text) > TELEGRAM_MESSAGE_MAX_LENGTH:
                    failed += 1
                    logger.warning(
                        "Broadcast skipped for user %s: rendered text %s chars exceeds limit",
                        uid,
                        len(message_text),
                    )
                    continue
                try:
                    await send_message_via_queue(
                        queue_manager,
                        chat_id,
                        MessageContent(content_type="text", text=message_text),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=markup,
                    )
                    sent += 1
                except Exception as exc:
                    failed += 1
                    logger.debug(
                        "Broadcast queue failed for user %s chat %s: %s",
                        uid,
                        chat_id,
                        exc,
                    )

        if email_enabled:
            recipients: list[BroadcastEmailRecipient] = []
            for uid, email, language in await user_dal.get_email_recipients_for_broadcast(
                session, user_ids
            ):
                if personalize:
                    rendered_text = _render(text, uid, language, escape=True)
                    rendered_subject = (
                        _render(email_subject, uid, language, escape=False)
                        if email_subject
                        else None
                    )
                    recipients.append(
                        BroadcastEmailRecipient(
                            user_id=uid,
                            email=email,
                            language_code=language,
                            message_text=rendered_text,
                            subject=rendered_subject,
                        )
                    )
                else:
                    recipients.append(
                        BroadcastEmailRecipient(user_id=uid, email=email, language_code=language)
                    )
            email_queued = schedule_broadcast_emails(
                settings=settings,
                i18n=i18n,
                recipients=recipients,
                subject=email_subject,
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
        audiences = service.audiences()
    else:
        async_session_factory: sessionmaker = get_session_factory(request)
        panel_service = _resolve_panel_service(request)
        counts = await _load_broadcast_audience_counts(
            settings,
            async_session_factory,
            panel_service,
        )
        audiences = []

    return _ok(
        AdminBroadcastAudienceCountsOut(
            counts=counts,
            audiences=[
                AdminBroadcastAudienceOut(
                    target=audience.target,
                    label_key=audience.label_key,
                    fallback_label=audience.fallback_label,
                    order=audience.order,
                    available=audience.available,
                    group_label_key=audience.group_label_key,
                    group_fallback_label=audience.group_fallback_label,
                )
                for audience in audiences
            ],
            email_enabled=bool(settings.email_auth_configured),
        ).model_dump(mode="json")
    )
