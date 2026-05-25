# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405
from .common import _invalidate_webapp_user_caches


def _resolve_telegram_bot_id(bot_token: str) -> Optional[int]:
    token_prefix = str(bot_token or "").strip().split(":", 1)[0]
    if not token_prefix.isdigit():
        return None
    try:
        return int(token_prefix)
    except ValueError:
        return None


def _resolve_telegram_oauth_client_id(settings: Settings) -> Optional[int]:
    configured_client_id = getattr(settings, "TELEGRAM_OAUTH_CLIENT_ID", None)
    if configured_client_id:
        try:
            return int(configured_client_id)
        except (TypeError, ValueError):
            return None
    return _resolve_telegram_bot_id(settings.BOT_TOKEN)


def _resolve_telegram_oauth_request_access(settings: Settings) -> List[str]:
    raw_value = str(getattr(settings, "TELEGRAM_OAUTH_REQUEST_ACCESS", "") or "")
    allowed = {"write", "phone"}
    scopes = []
    for item in raw_value.split(","):
        value = item.strip().lower()
        if value in allowed and value not in scopes:
            scopes.append(value)
    return scopes


def _public_webapp_base_url(settings: Settings, request: web.Request) -> str:
    configured_url = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if configured_url:
        parsed_url = urlsplit(configured_url)
        if parsed_url.scheme and parsed_url.netloc:
            return f"{parsed_url.scheme}://{parsed_url.netloc}"

    headers = request.headers
    if _request_remote_is_trusted_proxy(settings, request):
        scheme = _first_header_value(headers.get("X-Forwarded-Proto")) or request.scheme
        host = (
            _first_header_value(headers.get("X-Forwarded-Host"))
            or headers.get("Host")
            or request.host
        )
    else:
        scheme = request.scheme
        host = headers.get("Host") or request.host
    return f"{scheme}://{host}".rstrip("/")


def _first_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.split(",", 1)[0].strip()


def _request_remote_is_trusted_proxy(settings: Settings, request: web.Request) -> bool:
    try:
        remote_ip = ipaddress.ip_address(str(request.remote or "").strip())
    except ValueError:
        return False
    return any(remote_ip in network for network in parse_ip_entries(settings.trusted_proxies))


def _telegram_oauth_callback_url(settings: Settings, request: web.Request) -> str:
    return f"{_public_webapp_base_url(settings, request)}/auth/telegram/callback"


def _telegram_oauth_redirect_url(path: str = "/", *, status: Optional[str] = None) -> str:
    target_path = path if path.startswith("/") else "/"
    if target_path not in {"/", "/settings"}:
        target_path = "/"
    if not status:
        return target_path
    separator = "&" if "?" in target_path else "?"
    return f"{target_path}{separator}telegram_auth={status}"


def _set_telegram_oauth_state_cookie(
    response: web.StreamResponse,
    settings: Settings,
    payload: Dict[str, Any],
) -> None:
    max_age = max(60, int(settings.WEBAPP_LOGIN_TOKEN_TTL_SECONDS))
    response.set_cookie(
        WEBAPP_TELEGRAM_OAUTH_STATE_COOKIE_NAME,
        create_signed_telegram_oauth_state(settings, payload, ttl_seconds=max_age),
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/auth/telegram",
        max_age=max_age,
    )


def _clear_telegram_oauth_state_cookie(response: web.StreamResponse) -> None:
    response.set_cookie(
        WEBAPP_TELEGRAM_OAUTH_STATE_COOKIE_NAME,
        "",
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/auth/telegram",
        max_age=0,
    )


def _read_telegram_oauth_state_payload(
    request: web.Request,
    state_token: str,
) -> Optional[Dict[str, Any]]:
    settings: Settings = request.app["settings"]
    signed_payload = request.cookies.get(WEBAPP_TELEGRAM_OAUTH_STATE_COOKIE_NAME, "")
    payload = verify_signed_telegram_oauth_state(settings, signed_payload)
    if not payload:
        return None

    expected_state = str(payload.get("state") or "")
    if not expected_state or not hmac.compare_digest(expected_state, state_token):
        return None
    return payload


def _urlsafe_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


def _password_hash_b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _password_hash_unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _hash_email_password(password: str) -> str:
    salt = secrets.token_bytes(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            _password_hash_b64(salt),
            _password_hash_b64(digest),
        ]
    )


def _verify_email_password(password: str, stored_hash: Optional[str]) -> bool:
    if not stored_hash:
        return False
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = _password_hash_unb64(salt_raw)
        expected_digest = _password_hash_unb64(digest_raw)
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
    except Exception:
        return False
    return hmac.compare_digest(actual_digest, expected_digest)


async def _exchange_telegram_oauth_code(
    request: web.Request,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> Optional[Dict[str, Any]]:
    settings: Settings = request.app["settings"]
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
    settings: Settings = request.app["settings"]
    client_id = _resolve_telegram_oauth_client_id(settings)
    if not client_id:
        return _json_error(400, "telegram_oauth_not_configured", "Telegram OAuth is not configured")

    nonce = create_telegram_oauth_nonce(
        settings,
        ttl_seconds=settings.WEBAPP_LOGIN_TOKEN_TTL_SECONDS,
    )
    return web.json_response(
        {
            "ok": True,
            "nonce": nonce,
            "client_id": client_id,
            "request_access": _resolve_telegram_oauth_request_access(settings),
        }
    )


async def telegram_oauth_start_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
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
    settings: Settings = request.app["settings"]

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
    async_session_factory: sessionmaker = request.app["async_session_factory"]
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
        await _notify_account_merged(
            request,
            settings,
            merge_notice=link_merge_notice,
            email=linked_user_for_panel.email,
            telegram_id=_telegram_id_for_user(linked_user_for_panel),
            username=linked_user_for_panel.username,
            first_name=linked_user_for_panel.first_name,
        )

    token = create_webapp_session_token(settings, int(final_user_id))
    response = web.HTTPFound(_telegram_oauth_redirect_url(redirect_path, status="success"))
    _clear_telegram_oauth_state_cookie(response)
    _set_webapp_auth_cookies(response, settings, token, secrets.token_hex(32))
    raise response


async def _validate_telegram_auth_payload(
    request: web.Request,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    settings: Settings = request.app["settings"]
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
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    referral_param = str(payload.get("referral_code") or payload.get("start_param") or "")
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

    async_session_factory: sessionmaker = request.app["async_session_factory"]
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
    token = create_webapp_session_token(settings, int(authenticated_user_id))
    return _build_webapp_auth_response(settings, {"ok": True}, token=token)


async def logout_route(request: web.Request) -> web.Response:
    response = web.json_response({"ok": True})
    _clear_webapp_auth_cookies(response)
    return response


def _password_login_failure_response(
    *,
    status: int = 401,
    retry_after: Optional[int] = None,
) -> web.Response:
    payload: Dict[str, Any] = {
        "ok": False,
        "error": "password_login_failed",
        "fallback": "email_code",
        "message": "Password login failed",
    }
    if retry_after is not None:
        payload["retry_after"] = retry_after
    return web.json_response(payload, status=status)


async def email_password_auth_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.email_auth_configured:
        return _json_error(503, "email_auth_not_configured", "Email auth is not configured")

    payload = await _read_json(request)
    password_payload, validation_error = _validate_model_payload(
        WebAppEmailPasswordPayload,
        payload,
    )
    if validation_error:
        return validation_error

    email = password_payload.email
    password = str(password_payload.password or "")
    now = datetime.now(timezone.utc)

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    authenticated_user_id: Optional[int] = None
    authenticated_telegram_id: Optional[int] = None
    async with async_session_factory() as session:
        try:
            throttle = await security_dal.check_throttle(
                session,
                scope=security_dal.EMAIL_PASSWORD_LOGIN_SCOPE,
                identifier=email,
                now=now,
            )
            if throttle.locked:
                await session.commit()
                return _json_error(
                    429,
                    "rate_limited",
                    "Too many password attempts",
                )

            db_user = await user_dal.get_user_by_email(session, email)
            password_ok = bool(
                db_user
                and db_user.email_verified_at
                and db_user.password_hash
                and _verify_email_password(password, db_user.password_hash)
            )

            if not password_ok:
                throttle_result = await security_dal.record_throttle_failure(
                    session,
                    scope=security_dal.EMAIL_PASSWORD_LOGIN_SCOPE,
                    identifier=email,
                    max_failures=settings.BRUTE_FORCE_MAX_FAILURES,
                    window_seconds=settings.BRUTE_FORCE_WINDOW_SECONDS,
                    lock_seconds=settings.BRUTE_FORCE_LOCK_SECONDS,
                    now=now,
                )
                await session.commit()
                if throttle_result.locked:
                    return _json_error(
                        429,
                        "rate_limited",
                        "Too many password attempts",
                    )
                return _password_login_failure_response()

            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            await security_dal.clear_throttle_state(
                session,
                scope=security_dal.EMAIL_PASSWORD_LOGIN_SCOPE,
                identifier=email,
            )
            authenticated_user_id = int(db_user.user_id)
            authenticated_telegram_id = _telegram_id_for_user(db_user)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Email password auth failed")
            return _json_error(500, "auth_failed", "Auth failed")

    token = create_webapp_session_token(settings, int(authenticated_user_id))
    return _build_webapp_auth_response(
        settings,
        {
            "ok": True,
            "user_id": int(authenticated_user_id),
            "telegram_id": authenticated_telegram_id,
        },
        token=token,
    )


async def email_auth_request_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    email_payload, validation_error = _validate_model_payload(WebAppEmailPayload, payload)
    if validation_error:
        return validation_error
    email = email_payload.email
    lang = _normalize_language(str(payload.get("language") or settings.DEFAULT_LANGUAGE))
    return await _request_email_code(
        request,
        email=email,
        purpose="login",
        language_code=lang,
        target_user_id=None,
    )


async def email_auth_verify_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    email_payload, validation_error = _validate_model_payload(WebAppEmailCodePayload, payload)
    if validation_error:
        return validation_error
    email = email_payload.email
    code = str(email_payload.code or "")
    referral_param = str(payload.get("referral_code") or payload.get("start_param") or "")
    email_service: EmailAuthService = request.app["email_auth_service"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    created_user = False
    new_user_referrer_id: Optional[int] = None

    async with async_session_factory() as session:
        try:
            verify_result = await email_service.verify_code(
                session,
                email=email,
                purpose="login",
                code=code,
                target_user_id=None,
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

            db_user = await user_dal.get_user_by_email(session, email)
            if not db_user:
                referred_by_id = await _resolve_referrer_id(
                    session,
                    referral_param,
                    current_user_id=None,
                )
                db_user, _ = await user_dal.create_email_user(
                    session,
                    email=email,
                    language_code=_normalize_language(settings.DEFAULT_LANGUAGE),
                    email_verified_at=datetime.now(timezone.utc),
                    referred_by_id=referred_by_id,
                )
                created_user = True
                new_user_referrer_id = referred_by_id
            elif not db_user.email_verified_at:
                db_user.email_verified_at = datetime.now(timezone.utc)

            referral_applied = await _apply_referral_to_existing_user(
                request,
                session,
                db_user,
                referral_param,
            )
            if created_user or referral_applied:
                await _apply_referral_welcome_bonus_if_needed(
                    request,
                    session,
                    db_user,
                    referral_param,
                )

            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Email WebApp auth failed")
            return _json_error(500, "auth_failed", "Auth failed")

    await _invalidate_webapp_user_caches(settings, int(db_user.user_id), include_devices=True)
    if created_user:
        try:
            from bot.services.notification_service import NotificationService

            bot: Bot = request.app["bot"]
            notification_service = NotificationService(
                bot,
                settings,
                request.app.get("i18n"),
            )
            await notification_service.notify_new_email_user_registration(
                user_id=int(db_user.user_id),
                email=email,
                referred_by_id=new_user_referrer_id,
            )
        except Exception:
            logger.exception("Failed to send new email user notification")

    token = create_webapp_session_token(settings, int(db_user.user_id))
    return _build_webapp_auth_response(
        settings,
        {
            "ok": True,
            "user_id": int(db_user.user_id),
            "telegram_id": _telegram_id_for_user(db_user),
        },
        token=token,
    )


async def email_auth_magic_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    magic_payload, validation_error = _validate_model_payload(WebAppEmailMagicPayload, payload)
    if validation_error:
        return validation_error
    token_value = str(magic_payload.token).strip()
    referral_param = str(payload.get("referral_code") or payload.get("start_param") or "")
    email_service: EmailAuthService = request.app["email_auth_service"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    created_user = False
    new_user_referrer_id: Optional[int] = None
    verified_email: Optional[str] = None

    async with async_session_factory() as session:
        try:
            magic_result = await email_service.verify_magic_token(
                session,
                token=token_value,
                purpose="login",
                target_user_id=None,
            )
            if not magic_result.ok:
                await session.commit()
                return web.json_response(
                    {
                        "ok": False,
                        "error": magic_result.error or "invalid_token",
                        "message": "Invalid login link",
                    },
                    status=400,
                )

            verified_email = magic_result.email or ""
            db_user = await user_dal.get_user_by_email(session, verified_email)
            if not db_user:
                referred_by_id = await _resolve_referrer_id(
                    session,
                    referral_param,
                    current_user_id=None,
                )
                db_user, _ = await user_dal.create_email_user(
                    session,
                    email=verified_email,
                    language_code=_normalize_language(settings.DEFAULT_LANGUAGE),
                    email_verified_at=datetime.now(timezone.utc),
                    referred_by_id=referred_by_id,
                )
                created_user = True
                new_user_referrer_id = referred_by_id
            elif not db_user.email_verified_at:
                db_user.email_verified_at = datetime.now(timezone.utc)

            referral_applied = await _apply_referral_to_existing_user(
                request,
                session,
                db_user,
                referral_param,
            )
            if created_user or referral_applied:
                await _apply_referral_welcome_bonus_if_needed(
                    request,
                    session,
                    db_user,
                    referral_param,
                )

            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Email magic-link auth failed")
            return _json_error(500, "auth_failed", "Auth failed")

    await _invalidate_webapp_user_caches(settings, int(db_user.user_id), include_devices=True)
    if created_user and verified_email:
        try:
            from bot.services.notification_service import NotificationService

            bot: Bot = request.app["bot"]
            notification_service = NotificationService(
                bot,
                settings,
                request.app.get("i18n"),
            )
            await notification_service.notify_new_email_user_registration(
                user_id=int(db_user.user_id),
                email=verified_email,
                referred_by_id=new_user_referrer_id,
            )
        except Exception:
            logger.exception("Failed to send new email user notification")

    session_token = create_webapp_session_token(settings, int(db_user.user_id))
    return _build_webapp_auth_response(
        settings,
        {
            "ok": True,
            "user_id": int(db_user.user_id),
            "telegram_id": _telegram_id_for_user(db_user),
        },
        token=session_token,
    )


def _set_webapp_auth_cookies(
    response: web.StreamResponse,
    settings: Settings,
    session_token: str,
    csrf_token: str,
) -> None:
    max_age = max(60, int(settings.WEBAPP_SESSION_TTL_SECONDS))
    response.set_cookie(
        WEBAPP_SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        secure=True,
        samesite="None",
        path="/",
        max_age=max_age,
    )
    response.set_cookie(
        WEBAPP_CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=True,
        samesite="None",
        path="/",
        max_age=max_age,
    )


def _clear_webapp_auth_cookies(response: web.StreamResponse) -> None:
    response.set_cookie(
        WEBAPP_SESSION_COOKIE_NAME,
        "",
        httponly=True,
        secure=True,
        samesite="None",
        path="/",
        max_age=0,
    )
    response.set_cookie(
        WEBAPP_CSRF_COOKIE_NAME,
        "",
        httponly=False,
        secure=True,
        samesite="None",
        path="/",
        max_age=0,
    )


def _build_webapp_auth_response(
    settings: Settings,
    payload: Dict[str, Any],
    *,
    token: str,
    csrf_token: Optional[str] = None,
) -> web.Response:
    response_payload = dict(payload)
    response_payload["ok"] = True
    csrf_value = csrf_token or secrets.token_hex(32)
    response_payload["csrf_token"] = csrf_value
    response = web.json_response(response_payload)
    _set_webapp_auth_cookies(response, settings, token, csrf_value)
    return response


def _extract_authenticated_user_id(request: web.Request) -> Optional[int]:
    from bot.app.web.session import extract_authenticated_user_id

    return extract_authenticated_user_id(request)


def _require_user_id(request: web.Request) -> int:
    user_id = _extract_authenticated_user_id(request)
    if not user_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"ok": False, "error": "unauthorized"}),
            content_type="application/json",
        )
    return user_id


async def _request_email_code(
    request: web.Request,
    *,
    email: str,
    purpose: str,
    language_code: str,
    target_user_id: Optional[int],
) -> web.Response:
    email_service: EmailAuthService = request.app["email_auth_service"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        try:
            result = await email_service.request_code(
                session,
                email=email,
                purpose=purpose,
                language_code=language_code,
                target_user_id=target_user_id,
            )
            if not result.ok:
                await session.rollback()
                status = 429 if result.error == "rate_limited" else 400
                if result.error == "email_auth_not_configured":
                    status = 503
                return web.json_response(
                    {
                        "ok": False,
                        "error": result.error,
                        "retry_after": result.retry_after,
                    },
                    status=status,
                )
            await session.commit()
            return web.json_response({"ok": True})
        except Exception:
            await session.rollback()
            logger.exception("Failed to send email verification code")
            return _json_error(502, "email_send_failed", "Failed to send email")


def _telegram_id_for_user(user: User) -> Optional[int]:
    if user.telegram_id:
        return int(user.telegram_id)
    if user.user_id and int(user.user_id) > 0:
        return int(user.user_id)
    return None


def _panel_description_for_user(user: User) -> str:
    return panel_description_from_profile(
        user.username,
        user.first_name,
        user.last_name,
    )


def _telegram_photo_url_value(telegram_user: Dict[str, Any]) -> Optional[str]:
    raw_value = telegram_user.get("photo_url")
    if not raw_value:
        return None
    value = str(raw_value).strip()
    return value or None


async def _sync_panel_identity_for_user(
    request: web.Request,
    user: User,
    *,
    expire_at: Optional[datetime] = None,
) -> bool:
    if not user.panel_user_uuid:
        return False
    subscription_service: SubscriptionService = request.app.get("subscription_service")
    if not subscription_service or not subscription_service.panel_service:
        return False

    payload: Dict[str, Any] = {}
    telegram_id = _telegram_id_for_user(user)
    if telegram_id:
        payload["telegramId"] = telegram_id
    if user.email:
        payload["email"] = user.email
    if expire_at is not None:
        if expire_at.tzinfo is None:
            expire_at = expire_at.replace(tzinfo=timezone.utc)
        payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if expire_at > datetime.now(timezone.utc):
            payload["status"] = "ACTIVE"

    try:
        updated_panel_user = await subscription_service.panel_service.update_user_details_on_panel(
            user.panel_user_uuid,
            payload,
            log_response=False,
        )
        if not updated_panel_user or (
            isinstance(updated_panel_user, dict) and updated_panel_user.get("error")
        ):
            logger.warning(
                "Panel identity update returned no success payload for user %s",
                user.user_id,
            )
            return False
        return True
    except Exception as exc:
        logger.warning(
            "Failed to sync linked identities to panel for user %s: %s",
            user.user_id,
            exc,
        )
        return False


async def _delete_merged_source_panel_user(
    request: web.Request,
    *,
    source_panel_uuid: Optional[str],
    final_panel_uuid: Optional[str],
) -> bool:
    if not source_panel_uuid or not final_panel_uuid or source_panel_uuid == final_panel_uuid:
        return True

    subscription_service: SubscriptionService = request.app.get("subscription_service")
    if not subscription_service or not subscription_service.panel_service:
        return False

    try:
        return bool(
            await subscription_service.panel_service.delete_user_from_panel(
                source_panel_uuid,
                log_response=False,
            )
        )
    except Exception as exc:
        logger.warning(
            "Failed to delete merged source panel user %s: %s",
            source_panel_uuid,
            exc,
        )
        return False


async def _sync_merged_panel_identity_for_user(
    request: web.Request,
    user: User,
    *,
    source_panel_uuid: Optional[str],
    final_panel_uuid: Optional[str],
    expire_at: Optional[datetime] = None,
) -> bool:
    # Remnawave keeps email/telegramId unique. Remove the losing panel identity
    # before patching the surviving one so merged accounts can accept both IDs.
    await _delete_merged_source_panel_user(
        request,
        source_panel_uuid=source_panel_uuid,
        final_panel_uuid=final_panel_uuid or user.panel_user_uuid,
    )
    return await _sync_panel_identity_for_user(request, user, expire_at=expire_at)


async def _build_account_merge_notice(
    session: AsyncSession,
    *,
    merged_user: User,
    source_user_id: int,
    source_panel_uuid: Optional[str],
    settings: Settings,
) -> Dict[str, Any]:
    merged_subscription = None
    if merged_user.panel_user_uuid:
        merged_subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            merged_user.user_id,
            merged_user.panel_user_uuid,
        )
    if not merged_subscription:
        merged_subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            merged_user.user_id,
        )

    final_end_date = merged_subscription.end_date if merged_subscription else None
    if final_end_date and final_end_date.tzinfo is None:
        final_end_date = final_end_date.replace(tzinfo=timezone.utc)

    return {
        "merged": True,
        "language": _normalize_language(merged_user.language_code or settings.DEFAULT_LANGUAGE),
        "primary_user_id": int(merged_user.user_id),
        "removed_user_id": int(source_user_id),
        "primary_panel_user_uuid": merged_user.panel_user_uuid,
        "removed_panel_user_uuid": source_panel_uuid,
        "final_end_date": final_end_date.isoformat() if final_end_date else None,
        "final_end_date_text": _format_webapp_datetime(final_end_date),
    }


async def _notify_account_merged(
    request: web.Request,
    settings: Settings,
    *,
    merge_notice: Optional[Dict[str, Any]],
    email: Optional[str],
    telegram_id: Optional[int],
    username: Optional[str],
    first_name: Optional[str],
) -> None:
    if not merge_notice:
        return
    try:
        from bot.services.notification_service import NotificationService

        bot: Bot = request.app["bot"]
        notification_service = NotificationService(
            bot,
            settings,
            request.app.get("i18n"),
        )
        await notification_service.notify_account_merged(
            primary_user_id=int(merge_notice.get("primary_user_id") or 0),
            removed_user_id=int(merge_notice.get("removed_user_id") or 0),
            email=email,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            final_end_date_text=str(merge_notice.get("final_end_date_text") or ""),
            primary_panel_user_uuid=merge_notice.get("primary_panel_user_uuid"),
            removed_panel_user_uuid=merge_notice.get("removed_panel_user_uuid"),
        )
    except Exception:
        logger.exception("Failed to send account merged notification")


def _apply_telegram_profile_to_user(
    user: User,
    telegram_user: Dict[str, Any],
    settings: Settings,
) -> None:
    language_code = _normalize_language(
        telegram_user.get("language_code") or user.language_code or settings.DEFAULT_LANGUAGE
    )

    user.telegram_id = int(telegram_user["id"])
    user.username = sanitize_username(telegram_user.get("username"))
    user.first_name = sanitize_display_name(telegram_user.get("first_name"))
    user.last_name = sanitize_display_name(telegram_user.get("last_name"))
    user.language_code = language_code
    telegram_photo_url = _telegram_photo_url_value(telegram_user)
    if telegram_photo_url:
        user.telegram_photo_url = telegram_photo_url


async def _link_telegram_to_user(
    request: web.Request,
    session: AsyncSession,
    *,
    current_user_id: int,
    telegram_user: Dict[str, Any],
    settings: Settings,
) -> User:
    telegram_id = int(telegram_user["id"])
    current_user = await user_dal.get_user_by_id(session, current_user_id)
    if not current_user:
        raise ValueError("Current user not found.")

    existing_telegram_user = await user_dal.get_user_by_telegram_id(session, telegram_id)
    if not existing_telegram_user:
        existing_telegram_user = await user_dal.get_user_by_id(session, telegram_id)

    if existing_telegram_user and existing_telegram_user.user_id != current_user.user_id:
        if (
            current_user.email
            and existing_telegram_user.email
            and current_user.email != existing_telegram_user.email
        ):
            raise UserMergeConflictError("Telegram account is already linked to a different email.")
        merged_user = await user_dal.merge_users(
            session,
            source_user_id=current_user.user_id,
            target_user_id=existing_telegram_user.user_id,
        )
        _apply_telegram_profile_to_user(merged_user, telegram_user, settings)
        await session.flush()
        return merged_user

    if not existing_telegram_user and int(current_user.user_id) < 0:
        language_code = _normalize_language(
            telegram_user.get("language_code")
            or current_user.language_code
            or settings.DEFAULT_LANGUAGE
        )
        target_user, _ = await user_dal.create_user(
            session,
            {
                "user_id": telegram_id,
                "telegram_id": telegram_id,
                "username": sanitize_username(telegram_user.get("username")),
                "first_name": sanitize_display_name(telegram_user.get("first_name")),
                "last_name": sanitize_display_name(telegram_user.get("last_name")),
                "language_code": language_code,
                "registration_date": current_user.registration_date or datetime.now(timezone.utc),
            },
        )
        target_user.referral_code = None
        await session.flush()
        merged_user = await user_dal.merge_users(
            session,
            source_user_id=current_user.user_id,
            target_user_id=target_user.user_id,
        )
        _apply_telegram_profile_to_user(merged_user, telegram_user, settings)
        await session.flush()
        return merged_user

    if current_user.telegram_id and int(current_user.telegram_id) != telegram_id:
        raise UserMergeConflictError("Current account is already linked to Telegram.")

    _apply_telegram_profile_to_user(current_user, telegram_user, settings)
    await session.flush()
    await _sync_panel_identity_for_user(request, current_user)
    return current_user


def _normalize_referral_param(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None

    value_lower = value.lower()
    if value_lower.startswith("ref_u"):
        value = value[5:]
    elif value_lower.startswith("ref_"):
        value = value[4:]
    elif value and value[0].lower() == "u" and len(value) == 10:
        value = value[1:]

    if not re.fullmatch(r"[A-Za-z0-9]{1,32}", value):
        return None
    return value.upper()


async def _resolve_referrer_id(
    session: AsyncSession,
    raw_referral_param: Optional[str],
    *,
    current_user_id: Optional[int],
) -> Optional[int]:
    normalized = _normalize_referral_param(raw_referral_param)
    if not normalized:
        return None

    ref_user = None
    if normalized.isdigit():
        ref_user = await user_dal.get_user_by_id(session, int(normalized))
    if not ref_user:
        ref_user = await user_dal.get_user_by_referral_code(session, normalized)
    if not ref_user:
        return None
    if current_user_id is not None and int(ref_user.user_id) == int(current_user_id):
        return None
    return int(ref_user.user_id)


async def _apply_referral_to_existing_user(
    request: web.Request,
    session: AsyncSession,
    user: User,
    raw_referral_param: Optional[str],
) -> bool:
    if not raw_referral_param or user.referred_by_id is not None:
        return False

    referred_by_id = await _resolve_referrer_id(
        session,
        raw_referral_param,
        current_user_id=int(user.user_id),
    )
    if not referred_by_id:
        return False

    subscription_service: SubscriptionService = request.app["subscription_service"]
    try:
        is_active_now = await subscription_service.has_active_subscription(
            session,
            int(user.user_id),
        )
    except Exception:
        is_active_now = False
    if is_active_now:
        return False

    user.referred_by_id = referred_by_id
    await session.flush()
    return True


async def _apply_referral_welcome_bonus_if_needed(
    request: web.Request,
    session: AsyncSession,
    user: User,
    raw_referral_param: Optional[str],
) -> Optional[datetime]:
    if not raw_referral_param or not user.referred_by_id:
        return None

    settings: Settings = request.app["settings"]
    referral_welcome_days = max(
        0,
        int(getattr(settings, "REFERRAL_WELCOME_BONUS_DAYS", 0) or 0),
    )
    if referral_welcome_days <= 0:
        return None

    subscription_service: SubscriptionService = request.app["subscription_service"]
    try:
        if await subscription_service.has_active_subscription(session, int(user.user_id)):
            return None
    except Exception:
        pass

    return await subscription_service.extend_active_subscription_days(
        session,
        int(user.user_id),
        referral_welcome_days,
        reason="referral_welcome_bonus",
    )


async def _ensure_user_from_telegram(
    session: AsyncSession,
    telegram_user: Dict[str, Any],
    settings: Settings,
    *,
    referral_param: Optional[str] = None,
) -> User:
    user_id = int(telegram_user["id"])
    language_code = _normalize_language(
        telegram_user.get("language_code") or settings.DEFAULT_LANGUAGE
    )

    update_data = {
        "telegram_id": user_id,
        "username": sanitize_username(telegram_user.get("username")),
        "first_name": sanitize_display_name(telegram_user.get("first_name")),
        "last_name": sanitize_display_name(telegram_user.get("last_name")),
        "language_code": language_code,
    }
    telegram_photo_url = _telegram_photo_url_value(telegram_user)
    if telegram_photo_url:
        update_data["telegram_photo_url"] = telegram_photo_url

    db_user = await user_dal.get_user_by_telegram_id(session, user_id)
    if not db_user:
        db_user = await user_dal.get_user_by_id(session, user_id)
    if not db_user:
        referred_by_id = await _resolve_referrer_id(
            session,
            referral_param or telegram_user.get("start_param"),
            current_user_id=user_id,
        )
        db_user, created = await user_dal.create_user(
            session,
            {
                "user_id": user_id,
                **update_data,
                "referred_by_id": referred_by_id,
                "registration_date": datetime.now(timezone.utc),
            },
        )
        setattr(db_user, "_webapp_created", bool(created))
        return db_user

    changed = {key: value for key, value in update_data.items() if getattr(db_user, key) != value}
    if changed:
        db_user = await user_dal.update_user(session, db_user.user_id, changed) or db_user
    return db_user
