# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

from bot.app.web.webapp.cache_helpers import (
    invalidate_webapp_user_caches as _invalidate_user_payload_caches,
)
from bot.middlewares.i18n import (
    is_valid_locale_language_code,
    normalize_locale_language_code,
)


async def _read_json(request: web.Request) -> Dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _json_error(status: int, code: str, message: str) -> web.Response:
    return web.json_response(
        {"ok": False, "error": code, "message": message},
        status=status,
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


def _normalize_language(lang: Optional[str]) -> str:
    value = normalize_locale_language_code(lang, prefer_known_base=False)
    return value if is_valid_locale_language_code(value) else "ru"


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
