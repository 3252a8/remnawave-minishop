from bot.app.web.context import (
    get_email_auth_service,
    get_i18n,
    get_session_factory,
    get_settings,
)
from bot.app.web.webapp.cache_helpers import webapp_cached_user_payload
from bot.infra import events
from bot.infra.event_payloads import AccountEmailLinkedPayload, AccountTelegramLinkedPayload

from ._runtime import (
    Any,
    Dict,
    EmailAuthService,
    Optional,
    Settings,
    UserMergeConflictError,
    UserTelegramAvatar,
    create_webapp_session_token,
    datetime,
    hashlib,
    json_response,
    logger,
    sessionmaker,
    timezone,
    user_dal,
    web,
)
from .assets import (
    _enforce_webapp_rate_limit,
)
from .auth import (
    _build_account_merge_notice,
    _build_webapp_auth_response,
    _hash_email_password,
    _link_telegram_to_user,
    _request_email_code,
    _sync_merged_panel_identity_for_user,
    _sync_panel_identity_for_user,
    _validate_telegram_auth_payload,
)
from .common import (
    _ensure_cached_telegram_avatar,
    _invalidate_webapp_user_caches,
    _json_error,
    _normalize_language,
    _parse_model_payload,
    _require_user_id,
    _telegram_id_for_user,
)
from .payloads import (
    WebAppEmailCodePayload,
    WebAppEmailPayload,
    WebAppLanguagePayload,
    WebAppSetPasswordPayload,
    WebAppTelegramAuthPayload,
)
from .serializers import _build_user_payload
from .telegram_notifications import _probe_telegram_notifications_for_user_id


def _email_auth_enabled(settings: Any) -> bool:
    return bool(getattr(settings, "email_auth_configured", True))


def _email_auth_not_configured_response() -> web.Response:
    return _json_error(503, "email_auth_not_configured", "Email auth is not configured")


async def account_email_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not _email_auth_enabled(settings):
        return _email_auth_not_configured_response()

    email_payload = await _parse_model_payload(request, WebAppEmailPayload)
    email = email_payload.email
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if db_user.email == email and db_user.email_verified_at:
            return json_response({"ok": True, "already_linked": True})
        lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)

    return await _request_email_code(
        request,
        email=email,
        purpose="link_email",
        language_code=lang,
        target_user_id=user_id,
    )


async def account_email_verify_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not _email_auth_enabled(settings):
        return _email_auth_not_configured_response()

    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="account_email_verify",
    )
    if rate_limit_response:
        return rate_limit_response

    email_payload = await _parse_model_payload(request, WebAppEmailCodePayload)
    email = email_payload.email
    code = str(email_payload.code or "")
    email_service: EmailAuthService = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    merge_notice: Optional[Dict[str, Any]] = None
    source_panel_uuid: Optional[str] = None
    final_user_id = user_id
    final_telegram_id: Optional[int] = None
    final_username: Optional[str] = None
    final_first_name: Optional[str] = None
    final_panel_uuid: Optional[str] = None
    should_notify_email_linked = False

    async with async_session_factory() as session:
        try:
            verify_result = await email_service.verify_code(
                session,
                email=email,
                purpose="link_email",
                code=code,
                target_user_id=user_id,
            )
            if not verify_result.ok:
                await session.commit()
                status = 429 if verify_result.error == "rate_limited" else 400
                return json_response(
                    {
                        "ok": False,
                        "error": verify_result.error or "invalid_code",
                        "retry_after": verify_result.retry_after,
                        "message": "Invalid code",
                    },
                    status=status,
                )

            current_user = await user_dal.get_user_by_id(session, user_id)
            if not current_user or current_user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            should_notify_email_linked = (
                bool(_telegram_id_for_user(current_user)) and not current_user.email
            )

            existing_email_user = await user_dal.get_user_by_email(session, email)
            if existing_email_user and existing_email_user.user_id != current_user.user_id:
                source_panel_uuid = existing_email_user.panel_user_uuid
                current_user = await user_dal.merge_users(
                    session,
                    source_user_id=existing_email_user.user_id,
                    target_user_id=current_user.user_id,
                    reason="email_link",
                    send_user_email=True,
                )
                merge_notice = await _build_account_merge_notice(
                    session,
                    merged_user=current_user,
                    source_user_id=existing_email_user.user_id,
                    source_panel_uuid=source_panel_uuid,
                    settings=settings,
                )
            current_user.email = email
            current_user.email_verified_at = datetime.now(timezone.utc)
            if not merge_notice:
                await _sync_panel_identity_for_user(request, current_user)
            await session.commit()
            final_user_id = int(current_user.user_id)
            final_telegram_id = _telegram_id_for_user(current_user)
            final_username = current_user.username
            final_first_name = current_user.first_name
            final_panel_uuid = current_user.panel_user_uuid

            await events.emit_model(
                AccountEmailLinkedPayload(
                    user_id=final_user_id,
                    email=email,
                    first_link=should_notify_email_linked,
                    telegram_id=final_telegram_id,
                    username=final_username,
                    first_name=final_first_name,
                )
            )

            if merge_notice:
                merge_end_date_raw = merge_notice.get("final_end_date")
                merge_end_date = (
                    datetime.fromisoformat(merge_end_date_raw) if merge_end_date_raw else None
                )
                await _sync_merged_panel_identity_for_user(
                    request,
                    current_user,
                    source_panel_uuid=source_panel_uuid,
                    final_panel_uuid=final_panel_uuid,
                    expire_at=merge_end_date,
                )

        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, "account_merge_conflict", str(exc))
        except Exception:
            await session.rollback()
            logger.exception("Email account link failed")
            return _json_error(500, "link_failed", "Link failed")

    await _invalidate_webapp_user_caches(settings, user_id, final_user_id, include_devices=True)

    token = create_webapp_session_token(settings, int(final_user_id))
    response_payload: Dict[str, Any] = {"ok": True}
    if merge_notice:
        response_payload["account_merge"] = merge_notice
        response_payload["user_id"] = final_user_id
    return _build_webapp_auth_response(settings, response_payload, token=token)


async def account_password_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not _email_auth_enabled(settings):
        return _email_auth_not_configured_response()

    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if not db_user.email or not db_user.email_verified_at:
            return _json_error(400, "email_not_linked", "Email is not linked")
        email = db_user.email
        lang = _normalize_language(db_user.language_code or settings.DEFAULT_LANGUAGE)

    return await _request_email_code(
        request,
        email=email,
        purpose="set_password",
        language_code=lang,
        target_user_id=user_id,
    )


async def account_password_confirm_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings_for_gate = request.app.get("settings")
    if not _email_auth_enabled(settings_for_gate):
        return _email_auth_not_configured_response()

    password_payload = await _parse_model_payload(request, WebAppSetPasswordPayload)
    if password_payload.password != password_payload.password_confirm:
        return _json_error(400, "password_mismatch", "Passwords do not match")

    settings: Settings = get_settings(request)
    email_service: EmailAuthService = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            db_user = await user_dal.get_user_by_id(session, user_id)
            if not db_user or db_user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            if not db_user.email or not db_user.email_verified_at:
                await session.rollback()
                return _json_error(400, "email_not_linked", "Email is not linked")

            verify_result = await email_service.verify_code(
                session,
                email=db_user.email,
                purpose="set_password",
                code=str(password_payload.code or ""),
                target_user_id=user_id,
            )
            if not verify_result.ok:
                await session.commit()
                status = 429 if verify_result.error == "rate_limited" else 400
                return json_response(
                    {
                        "ok": False,
                        "error": verify_result.error or "invalid_code",
                        "retry_after": verify_result.retry_after,
                        "message": "Invalid code",
                    },
                    status=status,
                )

            db_user.password_hash = _hash_email_password(str(password_payload.password))
            db_user.password_set_at = datetime.now(timezone.utc)
            await session.flush()
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Email password setup failed")
            return _json_error(500, "password_setup_failed", "Password setup failed")

    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True, "password_auth_enabled": True})


async def account_telegram_link_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    auth_payload = await _parse_model_payload(request, WebAppTelegramAuthPayload)
    payload = auth_payload.model_dump(mode="json", exclude_none=True)
    telegram_user = await _validate_telegram_auth_payload(request, payload)
    if not telegram_user:
        return _json_error(401, "invalid_auth", "Invalid Telegram auth data")

    async_session_factory: sessionmaker = get_session_factory(request)
    merge_notice: Optional[Dict[str, Any]] = None
    source_panel_uuid: Optional[str] = None
    final_user_id = user_id
    final_telegram_id: Optional[int] = None
    final_email: Optional[str] = None
    final_username: Optional[str] = None
    final_first_name: Optional[str] = None
    final_panel_uuid: Optional[str] = None
    should_notify_telegram_linked = False
    async with async_session_factory() as session:
        try:
            current_user_before_link = await user_dal.get_user_by_id(session, user_id)
            if not current_user_before_link or current_user_before_link.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            should_notify_telegram_linked = bool(
                current_user_before_link.email
            ) and not _telegram_id_for_user(current_user_before_link)
            source_panel_uuid = current_user_before_link.panel_user_uuid

            db_user = await _link_telegram_to_user(
                request,
                session,
                current_user_id=user_id,
                telegram_user=telegram_user,
                settings=settings,
                merge_send_user_email=True,
            )
            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            final_user_id = int(db_user.user_id)
            final_telegram_id = _telegram_id_for_user(db_user)
            final_email = db_user.email
            final_username = db_user.username
            final_first_name = db_user.first_name
            final_panel_uuid = db_user.panel_user_uuid
            if final_user_id != user_id:
                merge_notice = await _build_account_merge_notice(
                    session,
                    merged_user=db_user,
                    source_user_id=user_id,
                    source_panel_uuid=source_panel_uuid,
                    settings=settings,
                )
            await session.commit()

            await events.emit_model(
                AccountTelegramLinkedPayload(
                    user_id=final_user_id,
                    telegram_id=final_telegram_id,
                    first_link=should_notify_telegram_linked,
                    email=final_email,
                    username=final_username,
                    first_name=final_first_name,
                )
            )

            if merge_notice:
                merge_end_date_raw = merge_notice.get("final_end_date")
                merge_end_date = (
                    datetime.fromisoformat(merge_end_date_raw) if merge_end_date_raw else None
                )
                await _sync_merged_panel_identity_for_user(
                    request,
                    db_user,
                    source_panel_uuid=source_panel_uuid,
                    final_panel_uuid=final_panel_uuid,
                    expire_at=merge_end_date,
                )

        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, "account_merge_conflict", str(exc))
        except Exception:
            await session.rollback()
            logger.exception("Telegram account link failed")
            return _json_error(500, "link_failed", "Link failed")

    await _invalidate_webapp_user_caches(settings, user_id, final_user_id, include_devices=True)

    await _probe_telegram_notifications_for_user_id(request, int(final_user_id))

    token = create_webapp_session_token(settings, int(final_user_id))
    response_payload: Dict[str, Any] = {
        "ok": True,
        "user_id": int(final_user_id),
        "telegram_id": final_telegram_id,
    }
    if merge_notice:
        response_payload["account_merge"] = merge_notice
    return _build_webapp_auth_response(settings, response_payload, token=token)


async def me_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    fresh = str(request.query.get("fresh") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if fresh:
        await _invalidate_webapp_user_caches(settings, user_id)
        data = await _build_user_payload(request, user_id)
        return json_response({"ok": True, **data})

    data = await webapp_cached_user_payload(
        settings,
        "me",
        user_id,
        int(getattr(settings, "WEBAPP_ME_CACHE_TTL_SECONDS", 15) or 0),
        lambda: _build_user_payload(request, user_id),
    )
    return json_response({"ok": True, **data})


async def account_avatar_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            await session.rollback()
            return _json_error(403, "access_denied", "Access denied")

        avatar = await _ensure_cached_telegram_avatar(request, session, db_user)
        await session.commit()

    if not avatar:
        raise web.HTTPNotFound(text="avatar_not_cached")

    etag = _telegram_avatar_etag(avatar)
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


async def account_language_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    language_payload = await _parse_model_payload(request, WebAppLanguagePayload)

    language = _normalize_language(str(language_payload.language or ""))
    i18n = get_i18n(request)
    if i18n and hasattr(i18n, "reload_overrides_from_file"):
        i18n.reload_overrides_from_file()
    if i18n and language not in getattr(i18n, "locales_data", {}):
        return _json_error(400, "unsupported_language", "Unsupported language")
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            await session.rollback()
            return _json_error(403, "access_denied", "Access denied")

        if _normalize_language(db_user.language_code or "") != language:
            db_user.language_code = language
            await session.flush()
        await session.commit()

    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True, "language": language})


def _telegram_photo_url_value(telegram_user: Dict[str, Any]) -> Optional[str]:
    raw_value = telegram_user.get("photo_url")
    if not raw_value:
        return None
    value = str(raw_value).strip()
    return value or None


def _telegram_avatar_etag(avatar: UserTelegramAvatar) -> str:
    digest = hashlib.sha256(bytes(avatar.image_bytes)).hexdigest()[:16]
    return f'"tg-avatar-{int(avatar.user_id)}-{digest}"'
