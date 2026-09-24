import logging
from datetime import UTC, datetime
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
from bot.app.web.message_image_contracts import message_image_request_content
from bot.app.web.request_parsing import parse_body_or_400, parse_body_with_optional_image_or_400
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_for,
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
from bot.services.message_image_service import (
    MessageImageError,
    persist_message_image,
    prepare_message_image,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from db.broadcast_models import AdminBroadcast
from db.dal import broadcast_dal, message_log_dal, promo_code_dal, user_dal

from .auth import (
    _require_admin_user_id,
)
from .broadcast_content import (
    BroadcastButton,
    BroadcastValidationError,
    broadcast_promo_codes,
    email_links_for_buttons,
    normalize_broadcast_channels,
    resolve_broadcast_buttons,
    resolve_localized_text,
    telegram_markup_for_buttons,
)
from .common import (
    _error,
    _ok,
)
from .response_schemas import (
    AdminBroadcastAudienceCountsOut,
    AdminBroadcastAudienceOut,
    AdminBroadcastButtonOut,
    AdminBroadcastCreateOut,
    AdminBroadcastDeleteOut,
    AdminBroadcastListOut,
    AdminBroadcastOut,
)
from .schemas import AdminBroadcastBody, AdminBroadcastScheduleBody

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
        request_content=message_image_request_content(AdminBroadcastBody),
        response_schema=ok_envelope_for(AdminBroadcastCreateOut),
        models=(
            AdminBroadcastBody,
            AdminBroadcastCreateOut,
            AdminBroadcastOut,
            AdminBroadcastButtonOut,
        ),
    ),
)
register_contract(
    "admin_broadcasts_list_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBroadcastListOut),
        models=(AdminBroadcastListOut, AdminBroadcastOut, AdminBroadcastButtonOut),
    ),
)
register_contract(
    "admin_broadcast_reschedule_route",
    RouteContract(
        request_model=AdminBroadcastScheduleBody,
        response_schema=ok_envelope_for(AdminBroadcastOut),
        models=(AdminBroadcastOut, AdminBroadcastButtonOut),
    ),
)
register_contract(
    "admin_broadcast_delete_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBroadcastDeleteOut),
        models=(AdminBroadcastDeleteOut,),
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
    return AudienceSegmentationService(
        get_session_factory(request),
        panel_service=_resolve_panel_service(request),
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
        )
    cache_key = "with-panel" if panel_service is not None else "without-panel"
    return cast(
        dict[str, int | None],
        await cache.get_or_load(
            cache_key,
            lambda: _load_broadcast_audience_counts_uncached(
                async_session_factory,
                panel_service,
            ),
        ),
    )


async def _load_broadcast_audience_counts_uncached(
    async_session_factory: sessionmaker,
    panel_service: Any,
) -> dict[str, int | None]:
    async with async_session_factory() as session:
        from bot.services.account_roles import active_admin_user_ids

        counts: dict[str, int | None] = {
            "all": await user_dal.count_all_active_users_for_broadcast(session),
            "active": await user_dal.count_users_with_active_subscription_for_broadcast(session),
            "inactive": await user_dal.count_users_without_active_subscription_for_broadcast(
                session
            ),
            "expired": await user_dal.count_users_with_expired_subscription_for_broadcast(session),
            "never": await user_dal.count_users_without_any_subscription_for_broadcast(session),
            BROADCAST_TARGET_ACTIVE_NEVER_CONNECTED: None,
            AUDIENCE_ADMINS: len(await active_admin_user_ids(session)),
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


async def _legacy_admin_broadcast_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminBroadcastBody)
    settings: Settings = get_settings(request)
    text = str(body.text or "").strip()
    target = str(body.target or "all").strip().lower()
    # The message exists in as many languages as the author wrote; ``text`` is
    # the one they wrote for everybody. Either alone is enough to send.
    texts = dict(body.texts)
    if text:
        texts.setdefault(str(settings.DEFAULT_LANGUAGE or "").strip().lower() or "en", text)
    if not texts:
        return _error(400, "empty_text")
    i18n = get_i18n(request)
    try:
        channels = normalize_broadcast_channels(body.channels)
        # Resolved once up front so an unusable button is a 400 before anything
        # is queued; the per-language captions are resolved again per recipient.
        buttons = resolve_broadcast_buttons(
            body.buttons,
            settings=settings,
            bot_username=get_bot_username(request),
            language=settings.DEFAULT_LANGUAGE,
            i18n=i18n,
        )
    except BroadcastValidationError as exc:
        return _error(400, exc.code, exc.detail)

    telegram_enabled = "telegram" in channels
    email_enabled = "email" in channels
    if email_enabled and not settings.smtp_delivery_configured:
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
    email_subjects = dict(body.email_subjects)
    if email_subject:
        email_subjects.setdefault(
            str(settings.DEFAULT_LANGUAGE or "").strip().lower() or "en", email_subject
        )
    # Every language variant is checked, not just the default one: a broken
    # shortcode or tag in one of them would only surface for the customers who
    # read that language.
    checked = [
        *texts.values(),
        *(email_subjects.values() if email_enabled else []),
        *(str(button.url or "") for button in body.buttons),
    ]
    unknown: set[str] = set()
    needed: set[str] = set()
    for variant in checked:
        unknown |= unknown_shortcodes(variant)
        needed |= known_shortcodes(variant)
    if unknown:
        return _error(400, "unknown_shortcode", ", ".join(sorted(unknown)))
    for variant in texts.values():
        html_error = telegram_html_error(variant)
        if html_error:
            return _error(400, "invalid_telegram_html", html_error)
    personalize = bool(needed)
    bot_username = get_bot_username(request)

    audience_service = _resolve_audience_service(request)
    try:
        user_ids = [int(uid) for uid in await audience_service.resolve_user_ids(target)]
    except AudienceNotFoundError:
        return _error(400, "invalid_audience", target)
    except AudienceUnavailableError:
        return _error(403, "audience_unavailable", target)
    promo_codes = broadcast_promo_codes(buttons)

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

        def _language(uid: int, fallback_lang: str | None) -> str:
            ctx = contexts.get(uid)
            return str(
                (ctx.language_code if ctx else None) or fallback_lang or settings.DEFAULT_LANGUAGE
            )

        def _variant(variants: dict[str, str], lang: str) -> str:
            return resolve_localized_text(
                variants, language=lang, default_language=settings.DEFAULT_LANGUAGE
            )

        def _render(template: str, uid: int, lang: str, *, escape: bool) -> str:
            return render_broadcast_text(
                template,
                contexts.get(uid),
                lang=lang,
                i18n=i18n,
                settings=settings,
                bot_username=bot_username,
                escape=escape,
            )

        button_shortcodes = set().union(
            *(known_shortcodes(str(button.url or "")) for button in body.buttons)
        )
        button_cache: dict[tuple[str, int | None], list[BroadcastButton]] = {}

        def _buttons(lang: str, uid: int) -> list[BroadcastButton]:
            cache_key = (lang, uid if button_shortcodes else None)
            if cache_key not in button_cache:
                personalized_buttons = [
                    button.model_copy(
                        update={"url": _render(str(button.url or ""), uid, lang, escape=False)}
                    )
                    if known_shortcodes(str(button.url or ""))
                    else button
                    for button in body.buttons
                ]
                button_cache[cache_key] = resolve_broadcast_buttons(
                    personalized_buttons,
                    settings=settings,
                    bot_username=bot_username,
                    language=lang,
                    i18n=i18n,
                )
            return button_cache[cache_key]

        if telegram_enabled and queue_manager is not None:
            telegram_recipients = await user_dal.get_telegram_recipients_for_broadcast(
                session, user_ids
            )
            for uid, chat_id in telegram_recipients:
                lang = _language(uid, None)
                variant = _variant(texts, lang)
                message_text = _render(variant, uid, lang, escape=True) if personalize else variant
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
                        reply_markup=telegram_markup_for_buttons(_buttons(lang, uid)),
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
                lang = _language(uid, language)
                variant = _variant(texts, lang)
                subject_variant = _variant(email_subjects, lang)
                recipients.append(
                    BroadcastEmailRecipient(
                        user_id=uid,
                        email=email,
                        language_code=language,
                        message_text=(
                            _render(variant, uid, lang, escape=True) if personalize else variant
                        ),
                        subject=(
                            _render(subject_variant, uid, lang, escape=False)
                            if personalize and subject_variant
                            else (subject_variant or None)
                        ),
                        buttons=email_links_for_buttons(_buttons(lang, uid)),
                    )
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


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _personal_broadcast_target_id(target: str) -> int | None:
    if not target.startswith("user:"):
        return None
    try:
        return int(target.partition(":")[2])
    except (TypeError, ValueError):
        return None


def _broadcast_out(item: AdminBroadcast) -> AdminBroadcastOut:
    created_at = _utc_datetime(cast(datetime | None, item.created_at))
    updated_at = _utc_datetime(cast(datetime | None, item.updated_at) or created_at)
    image_id = getattr(item, "image_id", None)
    raw_buttons = list(cast(list[dict[str, Any]], item.buttons or []))
    return AdminBroadcastOut(
        broadcast_id=int(item.broadcast_id),
        status=str(item.status),
        target=str(item.target),
        channels=[str(value) for value in list(item.channels or [])],
        exclude_blocked_telegram=bool(getattr(item, "exclude_blocked_telegram", False)),
        texts={str(key): str(value) for key, value in dict(item.texts or {}).items()},
        email_subjects={
            str(key): str(value) for key, value in dict(item.email_subjects or {}).items()
        },
        buttons=[
            AdminBroadcastButtonOut(
                kind=str(button.get("kind") or "url"),
                label=str(button.get("label") or ""),
                url=str(button.get("url") or ""),
                promo_code=str(button.get("promo_code") or ""),
                section=str(button.get("section") or ""),
                labels={
                    str(key): str(value) for key, value in dict(button.get("labels") or {}).items()
                },
            )
            for button in raw_buttons
            if isinstance(button, dict)
        ],
        image_id=str(image_id) if image_id else None,
        scheduled_at=_utc_datetime(cast(datetime | None, item.scheduled_at)),
        created_at=created_at,
        started_at=cast(datetime | None, item.started_at),
        finished_at=cast(datetime | None, item.finished_at),
        updated_at=updated_at,
        recipient_count=int(item.recipient_count or 0),
        total_deliveries=int(item.total_deliveries or 0),
        successful_deliveries=int(item.successful_deliveries or 0),
        failed_deliveries=int(item.failed_deliveries or 0),
        telegram_sent=int(item.telegram_sent or 0),
        telegram_failed=int(item.telegram_failed or 0),
        email_sent=int(item.email_sent or 0),
        email_failed=int(item.email_failed or 0),
        last_error=str(item.last_error) if item.last_error else None,
    )


async def admin_broadcast_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body, upload = await parse_body_with_optional_image_or_400(request, AdminBroadcastBody)
    try:
        image = await prepare_message_image(upload)
    except MessageImageError as exc:
        return _error(400, exc.code, exc.detail)
    settings: Settings = get_settings(request)
    target = str(body.target or "all").strip().lower()
    texts = dict(body.texts)
    text = str(body.text or "").strip()
    default_language = str(settings.DEFAULT_LANGUAGE or "").strip().lower() or "en"
    if text:
        texts.setdefault(default_language, text)
    if not texts and image is None:
        return _error(400, "empty_text")

    email_subjects = dict(body.email_subjects)
    email_subject = str(body.email_subject or "").strip()
    if email_subject:
        email_subjects.setdefault(default_language, email_subject)

    try:
        channels = normalize_broadcast_channels(body.channels)
        resolved_buttons = resolve_broadcast_buttons(
            body.buttons,
            settings=settings,
            bot_username=get_bot_username(request),
            language=settings.DEFAULT_LANGUAGE,
            i18n=get_i18n(request),
        )
    except BroadcastValidationError as exc:
        return _error(400, exc.code, exc.detail)

    if "email" in channels and not settings.smtp_delivery_configured:
        return _error(503, "email_not_configured")

    unknown = set().union(
        *(
            unknown_shortcodes(value)
            for value in [
                *texts.values(),
                *email_subjects.values(),
                *(str(button.url or "") for button in body.buttons),
            ]
        )
    )
    if unknown:
        return _error(400, "unknown_shortcode", ", ".join(sorted(unknown)))
    for variant in texts.values():
        html_error = telegram_html_error(variant)
        if html_error:
            return _error(400, "invalid_telegram_html", html_error)

    requested_scheduled_at = body.scheduled_at
    scheduled_at = _utc_datetime(requested_scheduled_at)
    if requested_scheduled_at is not None and scheduled_at <= datetime.now(UTC):
        return _error(400, "broadcast_schedule_future")

    audience_service = _resolve_audience_service(request)
    try:
        await audience_service.resolve_user_ids(target)
    except AudienceNotFoundError:
        return _error(400, "invalid_audience", target)
    except AudienceUnavailableError:
        return _error(403, "audience_unavailable", target)

    immediate = requested_scheduled_at is None
    queue_manager = get_queue_manager()
    if immediate and "telegram" in channels and queue_manager is None:
        return _error(503, "queue_unavailable")

    exclude_blocked_telegram = (
        body.exclude_blocked_telegram
        if body.exclude_blocked_telegram is not None
        else settings.ADMIN_BROADCAST_EXCLUDE_BLOCKED_TELEGRAM
    )

    async_session_factory = get_session_factory(request)
    async with async_session_factory() as session:
        promo_error = await _validate_broadcast_promo_codes(
            session, broadcast_promo_codes(resolved_buttons)
        )
        if promo_error is not None:
            return promo_error
        stored_image = await persist_message_image(session, image)
        personal_target_id = _personal_broadcast_target_id(target)
        if personal_target_id is not None:
            audit_text = text or next(iter(texts.values()), "") or "[image]"
            await message_log_dal.create_message_log_no_commit(
                session,
                {
                    "user_id": actor_id,
                    "event_type": "admin_direct_message_webapp",
                    "content": f"channels={','.join(channels)} | {audit_text}"[:4000],
                    "is_admin_event": True,
                    "target_user_id": personal_target_id,
                    "timestamp": datetime.now(UTC),
                },
            )
        item = await broadcast_dal.create_broadcast(
            session,
            actor_id=actor_id,
            target=target,
            channels=channels,
            exclude_blocked_telegram=exclude_blocked_telegram,
            texts=texts,
            email_subjects=email_subjects,
            buttons=[button.model_dump(mode="json") for button in body.buttons],
            scheduled_at=scheduled_at,
            is_visible=True,
            image_id=str(stored_image.image_id) if stored_image is not None else None,
        )

    # The worker claims due broadcasts from the durable queue. Waiting for
    # delivery preparation here can outlive the client's request timeout.
    payload = AdminBroadcastCreateOut(
        broadcast=_broadcast_out(item),
        target=target,
        channels=channels,
    )
    return _ok(payload.model_dump(mode="json"))


async def admin_broadcasts_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async with get_session_factory(request)() as session:
        broadcasts = await broadcast_dal.list_broadcasts(session)
    payload = AdminBroadcastListOut(broadcasts=[_broadcast_out(item) for item in broadcasts])
    return _ok(payload.model_dump(mode="json"))


async def admin_broadcast_reschedule_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminBroadcastScheduleBody)
    scheduled_at = _utc_datetime(body.scheduled_at)
    if scheduled_at <= datetime.now(UTC):
        return _error(400, "broadcast_schedule_future")
    broadcast_id = int(request.match_info["id"])
    async with get_session_factory(request)() as session:
        item = await broadcast_dal.reschedule_broadcast(
            session,
            broadcast_id,
            scheduled_at,
        )
    if item is None:
        return _error(409, "broadcast_not_reschedulable")
    return _ok(_broadcast_out(item).model_dump(mode="json"))


async def admin_broadcast_delete_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    broadcast_id = int(request.match_info["id"])
    async with get_session_factory(request)() as session:
        item = await broadcast_dal.delete_broadcast(session, broadcast_id)
    if item is None:
        return _error(404, "broadcast_not_found")
    payload = AdminBroadcastDeleteOut(broadcast_id=broadcast_id)
    return _ok(payload.model_dump(mode="json"))


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
                    icon=audience.icon,
                )
                for audience in audiences
            ],
            email_enabled=bool(settings.smtp_delivery_configured),
        ).model_dump(mode="json")
    )
