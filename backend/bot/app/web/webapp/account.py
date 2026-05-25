# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

from bot.app.web.webapp.cache_helpers import webapp_cached_user_payload
from .auth import (
    _hash_email_password,
    _notify_account_merged,
    _sync_merged_panel_identity_for_user,
)
from .common import _invalidate_webapp_user_caches


async def account_email_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    email_payload, validation_error = _validate_model_payload(WebAppEmailPayload, payload)
    if validation_error:
        return validation_error
    email = email_payload.email
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if db_user.email == email and db_user.email_verified_at:
            return web.json_response({"ok": True, "already_linked": True})
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
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="account_email_verify",
    )
    if rate_limit_response:
        return rate_limit_response

    payload = await _read_json(request)
    email_payload, validation_error = _validate_model_payload(WebAppEmailCodePayload, payload)
    if validation_error:
        return validation_error
    email = email_payload.email
    code = str(email_payload.code or "")
    email_service: EmailAuthService = request.app["email_auth_service"]
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    merge_notice: Optional[Dict[str, Any]] = None
    source_panel_uuid: Optional[str] = None
    final_user_id = user_id
    final_email = email
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
                return web.json_response(
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

                email_service: EmailAuthService = request.app.get("email_auth_service")
                if email_service and final_email:
                    email_content = render_account_merged(
                        settings,
                        language_code=merge_notice.get("language") or settings.DEFAULT_LANGUAGE,
                        primary_user_id=merge_notice.get("primary_user_id"),
                        removed_user_id=merge_notice.get("removed_user_id"),
                        final_end_date_text=str(
                            merge_notice.get("final_end_date_text")
                            or merge_notice.get("final_end_date")
                            or ""
                        ),
                    )
                    try:
                        await email_service.send_rendered_email(
                            email=final_email,
                            content=email_content,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to send account merge email to %s: %s",
                            final_email,
                            exc,
                        )
        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, "account_merge_conflict", str(exc))
        except Exception:
            await session.rollback()
            logger.exception("Email account link failed")
            return _json_error(500, "link_failed", "Link failed")

    await _invalidate_webapp_user_caches(settings, user_id, final_user_id, include_devices=True)
    if merge_notice:
        await _notify_account_merged(
            request,
            settings,
            merge_notice=merge_notice,
            email=final_email,
            telegram_id=final_telegram_id,
            username=final_username,
            first_name=final_first_name,
        )
    if should_notify_email_linked:
        try:
            from bot.services.notification_service import NotificationService

            bot: Bot = request.app["bot"]
            notification_service = NotificationService(
                bot,
                settings,
                request.app.get("i18n"),
            )
            await notification_service.notify_account_email_linked(
                user_id=int(final_user_id),
                email=final_email,
                telegram_id=final_telegram_id,
                username=final_username,
                first_name=final_first_name,
            )
        except Exception:
            logger.exception("Failed to send account email linked notification")

    token = create_webapp_session_token(settings, int(final_user_id))
    response_payload: Dict[str, Any] = {"ok": True}
    if merge_notice:
        response_payload["account_merge"] = merge_notice
        response_payload["user_id"] = final_user_id
    return _build_webapp_auth_response(settings, response_payload, token=token)


async def account_password_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

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
    payload = await _read_json(request)
    password_payload, validation_error = _validate_model_payload(WebAppSetPasswordPayload, payload)
    if validation_error:
        return validation_error
    if password_payload.password != password_payload.password_confirm:
        return _json_error(400, "password_mismatch", "Passwords do not match")

    settings: Settings = request.app["settings"]
    email_service: EmailAuthService = request.app["email_auth_service"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
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
                return web.json_response(
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
    return web.json_response({"ok": True, "password_auth_enabled": True})


async def account_telegram_link_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    telegram_user = await _validate_telegram_auth_payload(request, payload)
    if not telegram_user:
        return _json_error(401, "invalid_auth", "Invalid Telegram auth data")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
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

                email_service: EmailAuthService = request.app.get("email_auth_service")
                if email_service and final_email:
                    email_content = render_account_merged(
                        settings,
                        language_code=merge_notice.get("language") or settings.DEFAULT_LANGUAGE,
                        primary_user_id=merge_notice.get("primary_user_id"),
                        removed_user_id=merge_notice.get("removed_user_id"),
                        final_end_date_text=str(
                            merge_notice.get("final_end_date_text")
                            or merge_notice.get("final_end_date")
                            or ""
                        ),
                    )
                    try:
                        await email_service.send_rendered_email(
                            email=final_email,
                            content=email_content,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to send account merge email to %s: %s",
                            final_email,
                            exc,
                        )
        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, "account_merge_conflict", str(exc))
        except Exception:
            await session.rollback()
            logger.exception("Telegram account link failed")
            return _json_error(500, "link_failed", "Link failed")

    await _invalidate_webapp_user_caches(settings, user_id, final_user_id, include_devices=True)
    if merge_notice:
        await _notify_account_merged(
            request,
            settings,
            merge_notice=merge_notice,
            email=final_email,
            telegram_id=final_telegram_id,
            username=final_username,
            first_name=final_first_name,
        )
    if should_notify_telegram_linked and final_telegram_id:
        try:
            from bot.services.notification_service import NotificationService

            bot: Bot = request.app["bot"]
            notification_service = NotificationService(
                bot,
                settings,
                request.app.get("i18n"),
            )
            await notification_service.notify_account_telegram_linked(
                user_id=int(final_user_id),
                email=final_email,
                telegram_id=int(final_telegram_id),
                username=final_username,
                first_name=final_first_name,
            )
        except Exception:
            logger.exception("Failed to send account Telegram linked notification")

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
    settings: Settings = request.app["settings"]
    fresh = str(request.query.get("fresh") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if fresh:
        await _invalidate_webapp_user_caches(settings, user_id)
        data = await _build_user_payload(request, user_id)
        return web.json_response({"ok": True, **data})

    data = await webapp_cached_user_payload(
        settings,
        "me",
        user_id,
        int(getattr(settings, "WEBAPP_ME_CACHE_TTL_SECONDS", 15) or 0),
        lambda: _build_user_payload(request, user_id),
    )
    return web.json_response({"ok": True, **data})


async def account_avatar_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    async_session_factory: sessionmaker = request.app["async_session_factory"]
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
    payload = await _read_json(request)
    language_payload, validation_error = _validate_model_payload(WebAppLanguagePayload, payload)
    if validation_error:
        return validation_error

    language = _normalize_language(str(language_payload.language or ""))
    i18n = request.app.get("i18n")
    if i18n and hasattr(i18n, "reload_overrides_from_file"):
        i18n.reload_overrides_from_file()
    if i18n and language not in getattr(i18n, "locales_data", {}):
        return _json_error(400, "unsupported_language", "Unsupported language")
    async_session_factory: sessionmaker = request.app["async_session_factory"]
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
    return web.json_response({"ok": True, "language": language})


def _format_webapp_datetime(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.strftime("%d.%m.%Y %H:%M")


def _telegram_photo_url_value(telegram_user: Dict[str, Any]) -> Optional[str]:
    raw_value = telegram_user.get("photo_url")
    if not raw_value:
        return None
    value = str(raw_value).strip()
    return value or None


def _telegram_avatar_is_stale(avatar: Optional[UserTelegramAvatar]) -> bool:
    if not avatar or not avatar.updated_at:
        return True
    updated_at = avatar.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return (
        datetime.now(timezone.utc) - updated_at
    ).total_seconds() >= WEBAPP_TELEGRAM_AVATAR_REFRESH_SECONDS


def _telegram_avatar_etag(avatar: UserTelegramAvatar) -> str:
    digest = hashlib.sha256(bytes(avatar.image_bytes)).hexdigest()[:16]
    return f'"tg-avatar-{int(avatar.user_id)}-{digest}"'


def _telegram_avatar_url(avatar: Optional[UserTelegramAvatar]) -> str:
    if not avatar:
        return ""
    updated_at = avatar.updated_at
    if updated_at and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    version = (
        int(updated_at.timestamp())
        if updated_at
        else hashlib.sha256(bytes(avatar.image_bytes)).hexdigest()[:8]
    )
    return f"/api/account/avatar?v={version}"


def _select_compact_telegram_photo_size(sizes: List[Any]) -> Optional[Any]:
    if not sizes:
        return None
    suitable = [size for size in sizes if int(getattr(size, "width", 0) or 0) >= 160]
    candidates = suitable or sizes
    return min(
        candidates,
        key=lambda size: (
            int(getattr(size, "file_size", 0) or 0)
            or int(getattr(size, "width", 0) or 0) * int(getattr(size, "height", 0) or 0),
            int(getattr(size, "width", 0) or 0),
        ),
    )


def _telegram_file_content_type(file_path: Optional[str]) -> str:
    path = str(file_path or "").lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


async def _fetch_compact_telegram_avatar(
    bot: Bot, telegram_id: int
) -> Optional[Tuple[bytes, str, Optional[str]]]:
    photos = await bot.get_user_profile_photos(user_id=telegram_id, limit=1)
    if not photos or not photos.photos:
        return None

    photo_size = _select_compact_telegram_photo_size(list(photos.photos[0] or []))
    if not photo_size:
        return None

    file_info = await bot.get_file(photo_size.file_id)
    destination = io.BytesIO()
    await bot.download_file(file_info.file_path, destination=destination)
    body = destination.getvalue()
    if not body or len(body) > WEBAPP_TELEGRAM_AVATAR_MAX_BYTES:
        return None
    return (
        body,
        _telegram_file_content_type(file_info.file_path),
        getattr(photo_size, "file_unique_id", None),
    )


async def _ensure_cached_telegram_avatar(
    request: web.Request,
    session: AsyncSession,
    user: User,
) -> Optional[UserTelegramAvatar]:
    avatar = await user_dal.get_user_telegram_avatar(session, int(user.user_id))
    telegram_id = _telegram_id_for_user(user)
    if not telegram_id:
        return avatar
    if avatar and not _telegram_avatar_is_stale(avatar):
        return avatar

    bot: Bot = request.app["bot"]
    try:
        fetched = await asyncio.wait_for(
            _fetch_compact_telegram_avatar(bot, int(telegram_id)),
            timeout=WEBAPP_TELEGRAM_AVATAR_FETCH_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info("Failed to refresh Telegram avatar for user %s: %s", user.user_id, exc)
        return avatar

    if not fetched:
        return avatar

    body, content_type, file_unique_id = fetched
    return await user_dal.upsert_user_telegram_avatar(
        session,
        user_id=int(user.user_id),
        file_unique_id=file_unique_id,
        content_type=content_type,
        image_bytes=body,
    )
