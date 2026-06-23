from bot.app.web.context import (
    get_session_factory,
    get_settings,
)

from ._runtime import (
    Any,
    ClientTimeout,
    Dict,
    Optional,
    Settings,
    User,
    UserMergeConflictError,
    base64,
    create_telegram_oauth_nonce,
    create_webapp_session_token,
    datetime,
    json_response,
    logger,
    secrets,
    sessionmaker,
    urlencode,
    user_dal,
    validate_telegram_login_widget_data,
    validate_telegram_oauth_id_token,
    validate_telegram_webapp_init_data,
    verify_telegram_oauth_nonce,
    web,
)
from .assets import (
    _enforce_webapp_rate_limit,
    _get_shared_http_session,
)
from .auth_common import (
    _build_webapp_auth_response,
    _clear_telegram_oauth_state_cookie,
    _clear_webapp_auth_cookies,
    _read_telegram_oauth_state_payload,
    _set_telegram_oauth_state_cookie,
    _set_webapp_auth_cookies,
    _telegram_oauth_callback_url,
    _telegram_oauth_redirect_url,
    _urlsafe_sha256,
)
from .auth_panel import (
    _build_account_merge_notice,
    _link_telegram_to_user,
    _sync_merged_panel_identity_for_user,
)
from .auth_referral import (
    _apply_referral_to_existing_user,
    _apply_referral_welcome_bonus_if_needed,
    _ensure_user_from_telegram,
)
from .common import (
    _extract_authenticated_user_id,
    _invalidate_webapp_user_caches,
    _json_error,
    _parse_model_payload,
    _resolve_telegram_oauth_client_id,
    _resolve_telegram_oauth_request_access,
)
from .payloads import (
    WebAppTelegramAuthPayload,
)
from .telegram_notifications import _probe_telegram_notifications_for_user_id


async def _exchange_telegram_oauth_code(
    request: web.Request,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> Optional[Dict[str, Any]]:
    settings: Settings = get_settings(request)
    client_id = _resolve_telegram_oauth_client_id(settings)
    client_secret = str(getattr(settings, "TELEGRAM_OAUTH_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret or not code or not code_verifier:
        return None

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    session = await _get_shared_http_session()
    try:
        async with session.post(
            "https://oauth.telegram.org/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": str(client_id),
                "code_verifier": code_verifier,
            },
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=ClientTimeout(total=15),
        ) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                logger.warning(
                    "Telegram OAuth token exchange failed with HTTP %s: %s",
                    response.status,
                    payload,
                )
                return None
            return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Telegram OAuth token exchange failed: %s", exc)
        return None


async def telegram_oauth_nonce_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    client_id = _resolve_telegram_oauth_client_id(settings)
    if not client_id:
        return _json_error(400, "telegram_oauth_not_configured", "Telegram OAuth is not configured")

    nonce = create_telegram_oauth_nonce(
        settings,
        ttl_seconds=settings.WEBAPP_LOGIN_TOKEN_TTL_SECONDS,
    )
    return json_response(
        {
            "ok": True,
            "nonce": nonce,
            "client_id": client_id,
            "request_access": _resolve_telegram_oauth_request_access(settings),
        }
    )


async def telegram_oauth_start_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    client_id = _resolve_telegram_oauth_client_id(settings)
    client_secret = str(getattr(settings, "TELEGRAM_OAUTH_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret:
        raise web.HTTPFound(_telegram_oauth_redirect_url("/", status="not_configured"))

    purpose = str(request.query.get("purpose") or "login").strip().lower()
    if purpose not in {"login", "link"}:
        purpose = "login"

    current_user_id = _extract_authenticated_user_id(request)
    if purpose == "link" and not current_user_id:
        raise web.HTTPFound(_telegram_oauth_redirect_url("/", status="unauthorized"))

    code_verifier = secrets.token_urlsafe(32)
    code_challenge = _urlsafe_sha256(code_verifier)
    nonce = secrets.token_urlsafe(16)
    state = secrets.token_urlsafe(16)
    state_payload = {
        "state": state,
        "purpose": purpose,
        "user_id": int(current_user_id) if current_user_id else None,
        "referral_code": str(request.query.get("referral_code") or "")[:128],
        "code_verifier": code_verifier,
        "nonce": nonce,
    }

    scopes = ["openid", "profile"]
    for permission in _resolve_telegram_oauth_request_access(settings):
        if permission == "phone":
            scopes.append("phone")
        elif permission == "write":
            scopes.append("telegram:bot_access")

    auth_query = urlencode(
        {
            "client_id": str(client_id),
            "redirect_uri": _telegram_oauth_callback_url(settings, request),
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    response = web.HTTPFound(f"https://oauth.telegram.org/auth?{auth_query}")
    _set_telegram_oauth_state_cookie(response, settings, state_payload)
    raise response


async def telegram_oauth_callback_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)

    def redirect(path: str = "/", status: Optional[str] = None) -> web.HTTPFound:
        response = web.HTTPFound(_telegram_oauth_redirect_url(path, status=status))
        _clear_telegram_oauth_state_cookie(response)
        return response

    error = str(request.query.get("error") or "")
    if error:
        raise redirect("/", "cancelled")

    code = str(request.query.get("code") or "")
    state = _read_telegram_oauth_state_payload(request, str(request.query.get("state") or ""))
    if not code or not state:
        raise redirect("/", "invalid_state")

    token_payload = await _exchange_telegram_oauth_code(
        request,
        code=code,
        code_verifier=str(state.get("code_verifier") or ""),
        redirect_uri=_telegram_oauth_callback_url(settings, request),
    )
    id_token = str(token_payload.get("id_token") or "") if token_payload else ""
    telegram_user = await validate_telegram_oauth_id_token(
        id_token,
        client_id=int(_resolve_telegram_oauth_client_id(settings) or 0),
        expected_nonce=str(state.get("nonce") or ""),
        max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
    )
    if not telegram_user:
        raise redirect("/", "invalid_token")

    purpose = str(state.get("purpose") or "login")
    redirect_path = "/settings" if purpose == "link" else "/"
    async_session_factory: sessionmaker = get_session_factory(request)
    final_user_id: Optional[int] = None
    source_user_id_for_cache: Optional[int] = None
    linked_user_for_panel: Optional[User] = None
    link_source_panel_uuid: Optional[str] = None
    link_final_panel_uuid: Optional[str] = None
    link_merge_notice: Optional[Dict[str, Any]] = None
    async with async_session_factory() as session:
        try:
            if purpose == "link":
                current_user_id = int(state.get("user_id") or 0)
                source_user_id_for_cache = current_user_id
                current_user_before_link = await user_dal.get_user_by_id(session, current_user_id)
                link_source_panel_uuid = (
                    current_user_before_link.panel_user_uuid if current_user_before_link else None
                )
                db_user = await _link_telegram_to_user(
                    request,
                    session,
                    current_user_id=current_user_id,
                    telegram_user=telegram_user,
                    settings=settings,
                    merge_reason="telegram_link",
                )
                if int(db_user.user_id) != current_user_id:
                    link_final_panel_uuid = db_user.panel_user_uuid
                    link_merge_notice = await _build_account_merge_notice(
                        session,
                        merged_user=db_user,
                        source_user_id=current_user_id,
                        source_panel_uuid=link_source_panel_uuid,
                        settings=settings,
                    )
                linked_user_for_panel = db_user
            else:
                db_user = await _ensure_user_from_telegram(
                    session,
                    telegram_user,
                    settings,
                    referral_param=str(state.get("referral_code") or ""),
                )
                referral_applied = await _apply_referral_to_existing_user(
                    request,
                    session,
                    db_user,
                    str(state.get("referral_code") or "") or telegram_user.get("start_param"),
                )
                if getattr(db_user, "_webapp_created", False) or referral_applied:
                    await _apply_referral_welcome_bonus_if_needed(
                        request,
                        session,
                        db_user,
                        str(state.get("referral_code") or "") or telegram_user.get("start_param"),
                    )

            if db_user.is_banned:
                await session.rollback()
                raise redirect("/", "banned")

            final_user_id = int(db_user.user_id)
            await session.commit()
        except web.HTTPFound:
            raise
        except UserMergeConflictError:
            await session.rollback()
            raise redirect(redirect_path, "merge_conflict")
        except Exception:
            await session.rollback()
            logger.exception("Telegram OAuth callback failed")
            raise redirect(redirect_path, "failed")

    await _invalidate_webapp_user_caches(settings, final_user_id, include_devices=True)
    if source_user_id_for_cache and source_user_id_for_cache != final_user_id:
        await _invalidate_webapp_user_caches(
            settings,
            source_user_id_for_cache,
            final_user_id,
            include_devices=True,
        )

    if purpose == "link" and link_merge_notice and linked_user_for_panel:
        merge_end_date_raw = link_merge_notice.get("final_end_date")
        merge_end_date = datetime.fromisoformat(merge_end_date_raw) if merge_end_date_raw else None
        await _sync_merged_panel_identity_for_user(
            request,
            linked_user_for_panel,
            source_panel_uuid=link_source_panel_uuid,
            final_panel_uuid=link_final_panel_uuid,
            expire_at=merge_end_date,
        )

    if final_user_id:
        await _probe_telegram_notifications_for_user_id(request, int(final_user_id))

    token = create_webapp_session_token(settings, int(final_user_id))
    response = web.HTTPFound(_telegram_oauth_redirect_url(redirect_path, status="success"))
    _clear_telegram_oauth_state_cookie(response)
    _set_webapp_auth_cookies(response, settings, token, secrets.token_hex(32))
    raise response


async def _validate_telegram_auth_payload(
    request: web.Request,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    settings: Settings = get_settings(request)
    init_data = str(payload.get("init_data") or "")
    if init_data:
        return validate_telegram_webapp_init_data(
            init_data,
            settings.BOT_TOKEN,
            max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
        )

    oauth_id_token = str(payload.get("id_token") or "")
    if oauth_id_token:
        nonce = str(payload.get("nonce") or "")
        client_id = _resolve_telegram_oauth_client_id(settings)
        if not client_id or not verify_telegram_oauth_nonce(settings, nonce):
            return None
        return await validate_telegram_oauth_id_token(
            oauth_id_token,
            client_id=client_id,
            expected_nonce=nonce,
            max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
        )

    auth_data = payload.get("auth_data")
    if auth_data is not None:
        return validate_telegram_login_widget_data(
            auth_data,
            settings.BOT_TOKEN,
            max_age_seconds=settings.WEBAPP_AUTH_MAX_AGE_SECONDS,
        )

    return None


async def auth_token_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    auth_payload = await _parse_model_payload(request, WebAppTelegramAuthPayload)
    payload = auth_payload.model_dump(mode="json", exclude_none=True)
    referral_param = str(auth_payload.referral_code or auth_payload.start_param or "")
    telegram_user = await _validate_telegram_auth_payload(request, payload)

    if not telegram_user:
        return _json_error(401, "invalid_auth", "Invalid Telegram auth data")

    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=int(telegram_user.get("id") or 0),
        action="auth_token",
    )
    if rate_limit_response:
        return rate_limit_response

    async_session_factory: sessionmaker = get_session_factory(request)
    authenticated_user_id: Optional[int] = None
    async with async_session_factory() as session:
        try:
            db_user = await _ensure_user_from_telegram(
                session,
                telegram_user,
                settings,
                referral_param=referral_param,
            )
            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")
            referral_applied = await _apply_referral_to_existing_user(
                request,
                session,
                db_user,
                referral_param or telegram_user.get("start_param"),
            )
            if getattr(db_user, "_webapp_created", False) or referral_applied:
                await _apply_referral_welcome_bonus_if_needed(
                    request,
                    session,
                    db_user,
                    referral_param or telegram_user.get("start_param"),
                )
            authenticated_user_id = int(db_user.user_id)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("WebApp auth failed")
            return _json_error(500, "auth_failed", "Auth failed")

    await _invalidate_webapp_user_caches(settings, authenticated_user_id, include_devices=True)
    await _probe_telegram_notifications_for_user_id(request, int(authenticated_user_id))
    token = create_webapp_session_token(settings, int(authenticated_user_id))
    return _build_webapp_auth_response(settings, {"ok": True}, token=token)


async def logout_route(request: web.Request) -> web.Response:
    response = json_response({"ok": True})
    _clear_webapp_auth_cookies(response)
    return response
