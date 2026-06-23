import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from aiogram import Router

from bot.services.panel_api_service import PanelApiService
from bot.utils.text_sanitizer import panel_description_from_profile
from config.settings import Settings
from db.models import Subscription, User

router = Router(name="admin_sync_router")

# Single-flight guard: panel sync runs concurrently with the bot, but only one
# sync at a time. Overlapping callers (startup, /sync, admin API) return early
# instead of queueing behind the running sync.
_sync_lock = asyncio.Lock()


def _normalize_panel_email(value: Optional[str]) -> Optional[str]:
    email = (value or "").strip().lower()
    return email or None


def _coerce_panel_telegram_id(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logging.warning("Panel user has non-numeric telegramId: %r", value)
        return None


def _normalize_description(value: Optional[str]) -> str:
    return "\n".join((value or "").split()).strip()


def _repair_cp1251_mojibake(value: str) -> str:
    try:
        return value.encode("latin1").decode("cp1251")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _description_variants(value: Optional[str]) -> set[str]:
    normalized = _normalize_description(value)
    variants = {normalized}
    repaired = _normalize_description(_repair_cp1251_mojibake(normalized))
    if repaired:
        variants.add(repaired)
    return variants


def _description_matches(current: Optional[str], desired: str) -> bool:
    return bool(_description_variants(current) & _description_variants(desired))


def _description_contains_email(value: Optional[str], email: Optional[str]) -> bool:
    normalized_email = _normalize_panel_email(email)
    if not normalized_email:
        return False
    return normalized_email in _normalize_description(value).lower()


def _description_without_email(value: Optional[str], email: Optional[str]) -> str:
    normalized_email = _normalize_panel_email(email)
    if not normalized_email:
        return (value or "").strip()

    cleaned_lines = []
    for raw_line in (value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() == normalized_email:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _append_unique(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def _format_counter(counter: Counter[str], *, limit: int = 8) -> str:
    if not counter:
        return "none"
    parts = [f"{key}={value}" for key, value in counter.most_common(limit)]
    if len(counter) > limit:
        parts.append(f"+{len(counter) - limit} more")
    return ", ".join(parts)


def _compact_log_value(value: Any, *, max_len: int = 64) -> str:
    if value is None:
        return "null"
    if value == "":
        return "empty"
    if isinstance(value, datetime):
        text = value.isoformat()
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
        preview = ",".join(str(item) for item in values[:3])
        suffix = ",..." if len(values) > 3 else ""
        text = f"[{len(values)}:{preview}{suffix}]"
    elif isinstance(value, dict):
        keys = list(value.keys())
        preview = ",".join(str(key) for key in keys[:4])
        suffix = ",..." if len(keys) > 4 else ""
        text = f"{{{preview}{suffix}}}"
    else:
        text = str(value)

    text = text.replace("\r", "\\r").replace("\n", "\\n")
    text = " ".join(text.split())
    if len(text) > max_len:
        return f"{text[: max_len - 3]}..."
    return text


def _panel_log_value(field: str, value: Any) -> str:
    if value is _MISSING:
        return "missing"
    if field == "description":
        normalized = _normalize_description(value)
        if not normalized:
            return "len=0"
        preview = _compact_log_value(normalized, max_len=42)
        return f"len={len(normalized)}:{preview}"
    if field == "email":
        return _compact_log_value(_normalize_panel_email(value), max_len=64)
    return _compact_log_value(value)


def _parse_panel_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _safe_panel_telegram_id(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _panel_field_matches(current_value: Any, desired_value: Any, field: str) -> bool:
    if current_value is _MISSING:
        return False
    if field == "description":
        return _description_matches(current_value, str(desired_value or ""))
    if field == "email":
        return _normalize_panel_email(current_value) == _normalize_panel_email(desired_value)
    if field == "telegramId":
        return _safe_panel_telegram_id(current_value) == _safe_panel_telegram_id(desired_value)
    if field == "expireAt":
        current_dt = _parse_panel_datetime(current_value)
        desired_dt = _parse_panel_datetime(desired_value)
        return bool(current_dt and desired_dt and _datetime_matches(current_dt, desired_dt))
    if field == "status":
        return str(current_value or "").upper() == str(desired_value or "").upper()
    return bool(current_value == desired_value)


_MISSING = object()


def _panel_update_changes(
    current_panel_user: Optional[dict[str, Any]],
    update_payload: dict[str, Any],
) -> list[tuple[str, Any, Any]]:
    current_panel_user = current_panel_user or {}
    changes: list[tuple[str, Any, Any]] = []
    for field, desired_value in update_payload.items():
        if field == "uuid":
            continue
        current_value = current_panel_user.get(field, _MISSING)
        if not _panel_field_matches(current_value, desired_value, field):
            changes.append((field, current_value, desired_value))
    return changes


def _format_panel_update_changes(changes: list[tuple[str, Any, Any]]) -> str:
    if not changes:
        return "none"
    formatted = [
        f"{field}:{_panel_log_value(field, old)}->{_panel_log_value(field, new)}"
        for field, old, new in changes[:4]
    ]
    if len(changes) > 4:
        formatted.append(f"+{len(changes) - 4} more")
    return "; ".join(formatted)


def _identity_panel_update_reasons(
    changes: list[tuple[str, Any, Any]],
    *,
    description_has_email: bool,
) -> list[str]:
    reasons: list[str] = []
    if description_has_email:
        reasons.append("remove_email_from_description")
    for field, current_value, _desired_value in changes:
        if current_value is _MISSING:
            _append_unique(reasons, f"{field}_missing")
        elif field == "description":
            _append_unique(reasons, "description_mismatch")
        else:
            _append_unique(reasons, f"{field}_mismatch")
    if not reasons:
        reasons.append("identity_mismatch_without_visible_delta")
    return reasons


def _log_sync_panel_patch(
    *,
    source: str,
    user: Any,
    panel_uuid: str,
    update_payload: dict[str, Any],
    current_panel_user: Optional[dict[str, Any]],
    reasons: list[str],
    panel_view: str = "unknown",
) -> list[str]:
    changes = _panel_update_changes(current_panel_user, update_payload)
    changed_fields = [field for field, _old, _new in changes]
    payload_fields = [field for field in update_payload if field != "uuid"]
    logging.info(
        "Sync panel PATCH: source=%s user_id=%s telegram_id=%s panel_uuid=%s "
        "panel_view=%s reasons=%s fields=%s payload_fields=%s changes=%s",
        source,
        getattr(user, "user_id", None),
        getattr(user, "telegram_id", None),
        panel_uuid,
        panel_view,
        ",".join(reasons),
        ",".join(changed_fields) or "none",
        ",".join(payload_fields) or "none",
        _format_panel_update_changes(changes),
    )
    return changed_fields


def _panel_identity_matches_user(
    panel_user: dict[str, Any],
    user: User,
    desired_description: str,
    *,
    missing_identity_fields_match: bool = True,
) -> bool:
    if desired_description and not _description_matches(
        panel_user.get("description"),
        desired_description,
    ):
        return False

    if user.email:
        if "email" not in panel_user:
            return missing_identity_fields_match
        panel_email = _normalize_panel_email(panel_user.get("email"))
        if panel_email != user.email.strip().lower():
            return False

    if user.telegram_id:
        if "telegramId" not in panel_user:
            return missing_identity_fields_match
        panel_telegram_id = _coerce_panel_telegram_id(panel_user.get("telegramId"))
        if panel_telegram_id != int(user.telegram_id):
            return False

    return True


def _panel_identity_needs_full_fetch(panel_user: dict[str, Any], user: User) -> bool:
    if user.email:
        if "email" not in panel_user:
            return True
        if not _normalize_panel_email(panel_user.get("email")):
            return True
    if user.telegram_id:
        if "telegramId" not in panel_user:
            return True
        if _coerce_panel_telegram_id(panel_user.get("telegramId")) is None:
            return True
    return False


def _panel_identity_needs_legacy_description_cleanup(
    panel_user: dict[str, Any],
    user: User,
    desired_description: str,
) -> bool:
    if not user.email:
        return False
    current_description = panel_user.get("description")
    if _description_contains_email(current_description, user.email):
        return False
    if not desired_description:
        return not _normalize_description(current_description)
    return _description_matches(current_description, desired_description)


async def _panel_identity_view_for_comparison(
    panel_service: PanelApiService,
    panel_uuid: str,
    panel_user: dict[str, Any],
    user: User,
    desired_description: str = "",
) -> tuple[dict[str, Any], bool]:
    """Return the most reliable panel user view available for identity comparison.

    Remnawave list responses may omit identity fields. When that happens, fetch
    the concrete user by UUID before deciding whether the panel really needs a
    repair PATCH.
    """

    needs_full_fetch = _panel_identity_needs_full_fetch(panel_user, user)
    if not needs_full_fetch and _panel_identity_needs_legacy_description_cleanup(
        panel_user,
        user,
        desired_description,
    ):
        needs_full_fetch = True

    if not needs_full_fetch:
        return panel_user, True
    try:
        full_panel_user = await panel_service.get_user_by_uuid(panel_uuid)
    except Exception:
        logging.exception(
            "Sync: failed to fetch full panel user %s for identity comparison",
            panel_uuid,
        )
        return panel_user, True
    if not full_panel_user:
        return panel_user, True
    return full_panel_user, False


def _panel_identity_fields_update_payload(user: User) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if user.email:
        payload["email"] = user.email
    if user.telegram_id:
        payload["telegramId"] = user.telegram_id
    return payload


def _panel_description_for_user(user: User) -> str:
    return str(panel_description_from_profile(user.username, user.first_name, user.last_name))


def _datetime_matches(current: Optional[datetime], desired: datetime) -> bool:
    if current is None:
        return False
    current_dt = current if current.tzinfo else current.replace(tzinfo=timezone.utc)
    desired_dt = desired if desired.tzinfo else desired.replace(tzinfo=timezone.utc)
    delta = current_dt.astimezone(timezone.utc) - desired_dt.astimezone(timezone.utc)
    return abs(delta.total_seconds()) < 1


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _panel_expire_at(panel_user: dict[str, Any]) -> Optional[datetime]:
    raw_value = panel_user.get("expireAt")
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _panel_subscription_uuid(panel_user: dict[str, Any]) -> Optional[str]:
    value = panel_user.get("subscriptionUuid") or panel_user.get("shortUuid")
    return str(value) if value else None


def _should_update_lifetime_used_traffic(
    existing_user: User,
    lifetime_used: int,
    *,
    now: datetime,
    settings: Settings,
    is_duplicate_panel_identity: bool = False,
) -> bool:
    if is_duplicate_panel_identity:
        return False

    current_value = existing_user.lifetime_used_traffic_bytes
    if current_value == lifetime_used:
        return False
    if current_value is None:
        return True

    try:
        min_delta_bytes = max(
            0,
            int(getattr(settings, "PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES", 0) or 0),
        )
    except (TypeError, ValueError):
        min_delta_bytes = 0
    if min_delta_bytes and abs(int(lifetime_used) - int(current_value or 0)) >= min_delta_bytes:
        return True

    try:
        min_interval_seconds = max(
            0,
            int(getattr(settings, "PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS", 0) or 0),
        )
    except (TypeError, ValueError):
        min_interval_seconds = 0
    if min_interval_seconds <= 0:
        return True

    last_synced_at = getattr(existing_user, "lifetime_used_traffic_synced_at", None)
    if not last_synced_at:
        return True

    return (_as_utc(now) - _as_utc(last_synced_at)).total_seconds() >= min_interval_seconds


def _subscription_update_delta(
    subscription: Subscription, desired: dict[str, Any]
) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key, desired_value in desired.items():
        current_value = getattr(subscription, key)
        if key == "end_date":
            if not _datetime_matches(current_value, desired_value):
                delta[key] = desired_value
        elif current_value != desired_value:
            delta[key] = desired_value
    return delta
