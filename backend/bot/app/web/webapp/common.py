from typing import TypeVar, cast

from bot.app.web.context import (
    get_bot,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.webapp.cache_helpers import (
    invalidate_webapp_user_caches as _invalidate_user_payload_caches,
)
from bot.middlewares.i18n import (
    is_valid_locale_language_code,
    normalize_locale_language_code,
)

from ._runtime import (
    WEBAPP_TELEGRAM_AVATAR_FETCH_TIMEOUT_SECONDS,
    WEBAPP_TELEGRAM_AVATAR_MAX_BYTES,
    WEBAPP_TELEGRAM_AVATAR_REFRESH_SECONDS,
    Any,
    AsyncSession,
    BaseModel,
    Bot,
    Dict,
    List,
    Optional,
    Settings,
    Tuple,
    User,
    UserTelegramAvatar,
    ValidationError,
    asyncio,
    datetime,
    hashlib,
    io,
    json,
    json_response,
    logger,
    timezone,
    user_dal,
    web,
)

BodyModelT = TypeVar("BodyModelT", bound=BaseModel)


def _json_error(status: int, code: str, message: str) -> web.Response:
    return cast(
        web.Response,
        json_response(
            {"ok": False, "error": code, "message": message},
            status=status,
        ),
    )


async def _invalidate_webapp_user_caches(
    settings: Settings,
    *user_ids: Optional[int],
    include_devices: bool = False,
) -> None:
    await _invalidate_user_payload_caches(settings, *user_ids, include_devices=include_devices)


def _validation_error_response(exc: ValidationError) -> web.Response:
    for error in exc.errors():
        loc = error.get("loc") or ()
        field = str(loc[0]) if loc else ""
        error_type = str(error.get("type") or "")
        message = str(error.get("msg") or "")
        message_lower = message.lower()

        if field == "email":
            if (
                "too_long" in message_lower
                or "too long" in message_lower
                or error_type == "string_too_long"
            ):
                return _json_error(400, "email_too_long", "Email is too long")
            return _json_error(400, "invalid_email", "Invalid email")

        if field in {"description", "comment", "note"} and error_type == "string_too_long":
            return _json_error(400, f"{field}_too_long", f"{field.capitalize()} is too long")

        if field in {"password", "password_confirm"}:
            if error_type == "string_too_short":
                return _json_error(400, "password_too_short", "Password is too short")
            if error_type == "string_too_long":
                return _json_error(400, "password_too_long", "Password is too long")
            return _json_error(400, "invalid_password", "Invalid password")

        if error_type == "string_too_long":
            return _json_error(400, "text_too_long", "Text is too long")

    return _json_error(400, "invalid_request", "Invalid request")


def _validate_model_payload(
    model_cls: type[BaseModel],
    payload: Dict[str, Any],
) -> tuple[Optional[BaseModel], Optional[web.Response]]:
    try:
        return model_cls.model_validate(payload), None
    except ValidationError as exc:
        return None, _validation_error_response(exc)


async def _parse_model_payload(
    request: web.Request,
    model_cls: type[BodyModelT],
) -> BodyModelT:
    return cast(
        BodyModelT,
        await parse_body_or_400(
            request,
            model_cls,
            validation_error_response_factory=_validation_error_response,
        ),
    )


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


def _extract_authenticated_user_id(request: web.Request) -> Optional[int]:
    from bot.app.web.session import extract_authenticated_user_id

    user_id = extract_authenticated_user_id(request)
    return user_id if isinstance(user_id, int) else None


def _require_user_id(request: web.Request) -> int:
    user_id = _extract_authenticated_user_id(request)
    if not user_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"ok": False, "error": "unauthorized"}),
            content_type="application/json",
        )
    return user_id


def _normalize_language(lang: Optional[str]) -> str:
    value = normalize_locale_language_code(lang, prefer_known_base=False)
    return value if is_valid_locale_language_code(value) else "ru"


def _format_webapp_datetime(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.strftime("%d.%m.%Y %H:%M")


def _telegram_id_for_user(user: User) -> Optional[int]:
    telegram_id = getattr(user, "telegram_id", None)
    if telegram_id:
        return int(telegram_id)
    user_id = getattr(user, "user_id", None)
    if user_id and int(user_id) > 0:
        return int(user_id)
    return None


def _telegram_avatar_is_stale(avatar: Optional[UserTelegramAvatar]) -> bool:
    if not avatar or not avatar.updated_at:
        return True
    updated_at = avatar.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    is_stale = (
        datetime.now(timezone.utc) - updated_at
    ).total_seconds() >= WEBAPP_TELEGRAM_AVATAR_REFRESH_SECONDS
    return bool(is_stale)


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
    file_path = file_info.file_path
    if not file_path:
        return None
    destination = io.BytesIO()
    await bot.download_file(file_path, destination=destination)
    body = destination.getvalue()
    if not body or len(body) > WEBAPP_TELEGRAM_AVATAR_MAX_BYTES:
        return None
    return (
        body,
        _telegram_file_content_type(file_path),
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

    bot: Bot = get_bot(request)
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


def _format_remaining(seconds: int, lang: str) -> str:
    if seconds <= 0:
        if lang == "en":
            return "Subscription inactive"
        return "Подписка не активна"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if lang == "en":
        if days > 0:
            return f"{days} d. {hours} h."
        if hours > 0:
            return f"{hours} h. {minutes} min."
        return f"{max(1, minutes)} min."
    if days > 0:
        return f"{days} д. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{max(1, minutes)} мин."


def _coerce_int_or_none(value: Optional[Any]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_bytes(value: Optional[Any], *, zero_as_unlimited: bool = False) -> str:
    if value is None:
        return "N/A"
    try:
        size = float(value)
    except (TypeError, ValueError):
        return str(value)
    if size <= 0 and zero_as_unlimited:
        return "∞"
    if size <= 0:
        size = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"


def _format_months_title(months: int, lang: str) -> str:
    if lang == "en":
        if months == 1:
            return "1 month"
        return f"{months} months"
    if months == 1:
        return "1 месяц"
    if 2 <= months <= 4:
        return f"{months} месяца"
    return f"{months} месяцев"


def _format_number_for_payload(value: Any) -> str:
    numeric = float(value or 0)
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:g}"


def _format_traffic_title(traffic_gb: float, lang: str) -> str:
    return f"{_format_number_for_payload(traffic_gb)} GB"


def _traffic_payment_description(traffic_gb: float, lang: str) -> str:
    if lang == "en":
        return f"Traffic package {_format_traffic_title(traffic_gb, lang)}"
    return f"Пакет трафика {_format_traffic_title(traffic_gb, lang)}"


def _hwid_devices_payment_description(device_count: int, lang: str) -> str:
    if lang == "en":
        return f"HWID device package +{device_count}"
    return f"Докупка устройств HWID +{device_count}"


def _resolve_numeric_option_key(options: Dict[Any, Any], target: float) -> Optional[Any]:
    for key in options:
        try:
            if abs(float(key) - float(target)) < 0.000001:
                return key
        except (TypeError, ValueError):
            continue
    return None


def _payment_description(months: int, lang: str) -> str:
    if lang == "en":
        return f"Subscription for {_format_months_title(months, lang)}"
    return f"Подписка на {_format_months_title(months, lang)}"
