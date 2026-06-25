from bot.app.web.context import (
    get_settings,
)

from ._runtime import (
    WEBAPP_CSRF_COOKIE_NAME,
    WEBAPP_SESSION_COOKIE_NAME,
    WEBAPP_TELEGRAM_OAUTH_STATE_COOKIE_NAME,
    Any,
    Dict,
    List,
    Optional,
    Settings,
    User,
    base64,
    create_signed_telegram_oauth_state,
    hashlib,
    hmac,
    ipaddress,
    is_disposable_email,
    json_response,
    panel_description_from_profile,
    parse_ip_entries,
    re,
    secrets,
    urlsplit,
    verify_signed_telegram_oauth_state,
    web,
)


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
    settings: Settings = get_settings(request)
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
    response = json_response(response_payload)
    _set_webapp_auth_cookies(response, settings, token, csrf_value)
    return response


def _user_has_linked_telegram(user: User) -> bool:
    return bool(getattr(user, "telegram_id", None))


def _email_only_telegram_required_reason(
    settings: Settings,
    user: User,
    *,
    without_telegram_enabled_attr: str,
) -> Optional[str]:
    if _user_has_linked_telegram(user):
        return None
    if is_disposable_email(getattr(user, "email", None), settings):
        return "disposable_email"
    if not bool(getattr(settings, without_telegram_enabled_attr, True)):
        return "telegram_required"
    return None


def _trial_telegram_required_reason(settings: Settings, user: User) -> Optional[str]:
    return _email_only_telegram_required_reason(
        settings,
        user,
        without_telegram_enabled_attr="TRIAL_WITHOUT_TELEGRAM_ENABLED",
    )


def _referral_welcome_telegram_required_reason(
    settings: Settings,
    user: User,
) -> Optional[str]:
    return _email_only_telegram_required_reason(
        settings,
        user,
        without_telegram_enabled_attr="REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
    )


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


def _remnashop_referral_compat_enabled(settings: Optional[Settings]) -> bool:
    if settings is None:
        return False
    return bool(settings.compatibility_settings.remnashop_referral_code_compat_enabled)


def _strip_referral_param_prefix(
    raw: Optional[str],
    *,
    preserve_current_u_prefix: bool,
) -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    value_lower = value.lower()
    if value_lower.startswith("ref_u") and not preserve_current_u_prefix:
        value = value[5:]
    elif value_lower.startswith("ref_"):
        value = value[4:]
    return value


def _normalize_referral_param(raw: Optional[str]) -> Optional[str]:
    value = _strip_referral_param_prefix(raw, preserve_current_u_prefix=False)
    if not value:
        return None

    if value and value[0].lower() == "u" and len(value) == 10:
        value = value[1:]

    if not re.fullmatch(r"[A-Za-z0-9]{1,32}", value):
        return None
    return value.upper()


def _referral_param_lookup_candidates(
    raw: Optional[str],
    *,
    remnashop_compat: bool,
) -> List[str]:
    if not remnashop_compat:
        normalized = _normalize_referral_param(raw)
        return [normalized] if normalized else []

    value = _strip_referral_param_prefix(raw, preserve_current_u_prefix=True)
    if not value or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
        return []

    candidates = [value]
    if value and value[0].lower() == "u":
        candidates.append(value[1:])

    unique: List[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique
