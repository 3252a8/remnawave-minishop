import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

from aiogram import Bot, Router, types
from aiogram.filters import Command
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.notification_service import NotificationService
from bot.services.panel_api_service import PanelApiService
from bot.utils.text_sanitizer import panel_description_from_profile
from config.settings import Settings
from db.dal import panel_sync_dal, subscription_dal, user_dal
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
    return current_value == desired_value


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
    return panel_description_from_profile(
        user.username,
        user.first_name,
        user.last_name,
    )


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
    existing_user,
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


async def _prefetch_sync_indexes(
    session: AsyncSession, panel_users_data: list[dict[str, Any]]
) -> dict[str, Any]:
    telegram_ids: set[int] = set()
    panel_uuids: set[str] = set()
    emails: set[str] = set()
    panel_subscription_uuids: set[str] = set()
    panel_uuids_by_telegram_id: dict[int, set[str]] = {}

    for panel_user in panel_users_data:
        telegram_id = _coerce_panel_telegram_id(panel_user.get("telegramId"))
        panel_uuid = panel_user.get("uuid")
        if telegram_id:
            telegram_ids.add(telegram_id)
            if panel_uuid:
                panel_uuids_by_telegram_id.setdefault(telegram_id, set()).add(str(panel_uuid))
        if panel_uuid:
            panel_uuids.add(panel_uuid)
        email = _normalize_panel_email(panel_user.get("email"))
        if email:
            emails.add(email)
        panel_subscription_uuid = panel_user.get("subscriptionUuid") or panel_user.get("shortUuid")
        if panel_subscription_uuid:
            panel_subscription_uuids.add(panel_subscription_uuid)

    users_by_telegram_id: dict[int, User] = {}
    users_by_user_id: dict[int, User] = {}
    users_by_panel_uuid: dict[str, User] = {}
    users_by_email: dict[str, User] = {}

    user_filters = []
    if telegram_ids:
        user_filters.append(User.telegram_id.in_(telegram_ids))
        user_filters.append(User.user_id.in_(telegram_ids))
    if panel_uuids:
        user_filters.append(User.panel_user_uuid.in_(panel_uuids))
    if emails:
        user_filters.append(func.lower(User.email).in_(emails))
    if user_filters:
        result = await session.execute(select(User).where(or_(*user_filters)))
        for user in result.scalars().unique().all():
            if user.telegram_id is not None:
                users_by_telegram_id[int(user.telegram_id)] = user
            users_by_user_id[int(user.user_id)] = user
            if user.panel_user_uuid:
                users_by_panel_uuid[user.panel_user_uuid] = user
            if user.email:
                users_by_email[user.email.strip().lower()] = user

    subscriptions_by_panel_uuid: dict[str, Subscription] = {}
    if panel_subscription_uuids:
        result = await session.execute(
            select(Subscription).where(
                Subscription.panel_subscription_uuid.in_(panel_subscription_uuids)
            )
        )
        subscriptions_by_panel_uuid = {
            str(sub.panel_subscription_uuid): sub
            for sub in result.scalars().unique().all()
            if sub.panel_subscription_uuid
        }

    active_subscriptions_by_user_panel: dict[tuple[int, str], Subscription] = {}
    if panel_uuids:
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.panel_user_uuid.in_(panel_uuids),
                Subscription.is_active.is_(True),
                Subscription.end_date > datetime.now(timezone.utc),
            )
            .order_by(Subscription.end_date.desc())
        )
        for sub in result.scalars().unique().all():
            active_subscriptions_by_user_panel.setdefault(
                (int(sub.user_id), sub.panel_user_uuid), sub
            )

    return {
        "users_by_telegram_id": users_by_telegram_id,
        "users_by_user_id": users_by_user_id,
        "users_by_panel_uuid": users_by_panel_uuid,
        "users_by_email": users_by_email,
        "subscriptions_by_panel_uuid": subscriptions_by_panel_uuid,
        "active_subscriptions_by_user_panel": active_subscriptions_by_user_panel,
        "panel_uuids_by_telegram_id": panel_uuids_by_telegram_id,
    }


def _extract_lifetime_used_traffic_bytes(panel_user_data: dict) -> Optional[int]:
    user_traffic = panel_user_data.get("userTraffic") or {}
    raw_value = (
        user_traffic.get("lifetimeUsedTrafficBytes") if isinstance(user_traffic, dict) else None
    )
    if raw_value is None:
        raw_value = panel_user_data.get("lifetimeUsedTrafficBytes")

    try:
        if raw_value is None:
            return None
        return int(raw_value)
    except (TypeError, ValueError):
        return None


async def _bind_panel_email_to_user(
    session: AsyncSession,
    *,
    existing_user,
    email_from_panel: Optional[str],
    panel_uuid: str,
) -> tuple[object, bool]:
    """Bind panel email to a local user without violating the unique email index.

    Panel email is treated as verified because it comes from the operator-managed
    panel. If the same email already belongs to an email-only local account for
    this panel user, merge that account into the Telegram/local user.
    """
    if not email_from_panel:
        return existing_user, False

    if existing_user.email == email_from_panel:
        if not existing_user.email_verified_at:
            existing_user.email_verified_at = datetime.now(timezone.utc)
            return existing_user, True
        return existing_user, False

    user_with_email = await user_dal.get_user_by_email(session, email_from_panel)
    if user_with_email and user_with_email.user_id != existing_user.user_id:
        can_merge_email_identity = (
            not user_with_email.telegram_id
            and user_with_email.panel_user_uuid in (None, panel_uuid)
            and (not existing_user.email or existing_user.email == email_from_panel)
        )
        if can_merge_email_identity:
            try:
                merged_user = await user_dal.merge_users(
                    session,
                    source_user_id=user_with_email.user_id,
                    target_user_id=existing_user.user_id,
                )
                if not merged_user.email:
                    merged_user.email = email_from_panel
                if not merged_user.email_verified_at:
                    merged_user.email_verified_at = datetime.now(timezone.utc)
                logging.info(
                    "Merged email-only user %s into user %s while binding panel email %s for panel UUID %s.",  # noqa: E501
                    user_with_email.user_id,
                    merged_user.user_id,
                    email_from_panel,
                    panel_uuid,
                )
                return merged_user, True
            except Exception as merge_error:
                logging.warning(
                    "Could not merge email-only user %s into user %s for panel email %s: %s",
                    user_with_email.user_id,
                    existing_user.user_id,
                    email_from_panel,
                    merge_error,
                )
                return existing_user, False

        logging.warning(
            "Panel email %s for panel UUID %s is already linked to local user %s; "
            "skipping email binding for user %s.",
            email_from_panel,
            panel_uuid,
            user_with_email.user_id,
            existing_user.user_id,
        )
        return existing_user, False

    existing_user.email = email_from_panel
    existing_user.email_verified_at = datetime.now(timezone.utc)
    logging.info(
        "Bound panel email %s to local user %s for panel UUID %s.",
        email_from_panel,
        existing_user.user_id,
        panel_uuid,
    )
    return existing_user, True


async def _merge_local_duplicate_panel_user_if_needed(
    session: AsyncSession,
    *,
    existing_user,
    duplicate_panel_uuid: str,
):
    duplicate_local_user = await user_dal.get_user_by_panel_uuid(session, duplicate_panel_uuid)
    if not duplicate_local_user or duplicate_local_user.user_id == existing_user.user_id:
        return existing_user, True

    try:
        merged_user = await user_dal.merge_users(
            session,
            source_user_id=duplicate_local_user.user_id,
            target_user_id=existing_user.user_id,
        )
        logging.info(
            "Sync: merged local duplicate user %s into %s for duplicate panel UUID %s.",
            duplicate_local_user.user_id,
            merged_user.user_id,
            duplicate_panel_uuid,
        )
        return merged_user, True
    except Exception as exc:
        logging.warning(
            "Sync: could not merge local duplicate user %s into %s for panel UUID %s: %s",
            duplicate_local_user.user_id,
            existing_user.user_id,
            duplicate_panel_uuid,
            exc,
        )
        return existing_user, False


def _panel_identity_payload_with_expiry(
    user,
    *,
    expire_at: datetime,
) -> dict[str, Any]:
    payload = _panel_identity_fields_update_payload(user)
    payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if expire_at > datetime.now(timezone.utc):
        payload["status"] = "ACTIVE"
    return payload


async def _absorb_duplicate_panel_identity(
    session: AsyncSession,
    *,
    panel_service: PanelApiService,
    existing_user,
    keep_panel_uuid: str,
    keep_panel_user: Optional[dict[str, Any]],
    duplicate_panel_user: dict[str, Any],
    settings: Settings,
    subscriptions_by_panel_uuid: dict[str, Subscription],
    active_subscriptions_by_user_panel: dict[tuple[int, str], Subscription],
) -> dict[str, int | bool]:
    duplicate_panel_uuid = str(duplicate_panel_user.get("uuid") or "")
    if not duplicate_panel_uuid:
        return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}

    subscriptions_created = 0
    subscriptions_updated = 0
    panel_patches = 0
    now = datetime.now(timezone.utc)
    duplicate_expire_at = _panel_expire_at(duplicate_panel_user)
    duplicate_status = str(duplicate_panel_user.get("status") or "").upper()
    duplicate_is_active = bool(
        duplicate_expire_at and duplicate_status == "ACTIVE" and duplicate_expire_at > now
    )

    keep_subscription_uuid = _panel_subscription_uuid(keep_panel_user or {})
    target_sub = (
        subscriptions_by_panel_uuid.get(keep_subscription_uuid) if keep_subscription_uuid else None
    )
    if not target_sub:
        target_sub = active_subscriptions_by_user_panel.get(
            (int(existing_user.user_id), keep_panel_uuid)
        )

    final_end_date: Optional[datetime] = None
    if duplicate_is_active and duplicate_expire_at:
        source_remaining = max(timedelta(0), duplicate_expire_at - now)
        if target_sub:
            target_end = _as_utc(target_sub.end_date)
            base_end = target_end if target_end > now else now
            final_end_date = base_end + source_remaining
            update_payload: dict[str, Any] = {
                "user_id": int(existing_user.user_id),
                "panel_user_uuid": keep_panel_uuid,
                "end_date": final_end_date,
                "is_active": True,
                "status_from_panel": "ACTIVE_EXTENDED_BY_PANEL_DUPLICATE_MERGE",
            }
            if keep_subscription_uuid:
                update_payload["panel_subscription_uuid"] = keep_subscription_uuid
            update_delta = _subscription_update_delta(target_sub, update_payload)
            if update_delta:
                await subscription_dal.update_subscription(
                    session,
                    target_sub.subscription_id,
                    update_delta,
                )
                for key, value in update_delta.items():
                    setattr(target_sub, key, value)
                subscriptions_updated += 1
        elif keep_subscription_uuid:
            final_end_date = now + (duplicate_expire_at - now)
            created_sub = await subscription_dal.upsert_subscription(
                session,
                {
                    "user_id": int(existing_user.user_id),
                    "panel_user_uuid": keep_panel_uuid,
                    "panel_subscription_uuid": keep_subscription_uuid,
                    "start_date": None,
                    "end_date": final_end_date,
                    "duration_months": None,
                    "is_active": True,
                    "status_from_panel": "ACTIVE_EXTENDED_BY_PANEL_DUPLICATE_MERGE",
                    "traffic_limit_bytes": getattr(settings, "user_traffic_limit_bytes", 0),
                    "auto_renew_enabled": False,
                },
            )
            subscriptions_by_panel_uuid[keep_subscription_uuid] = created_sub
            active_subscriptions_by_user_panel[
                (int(created_sub.user_id), created_sub.panel_user_uuid)
            ] = created_sub
            subscriptions_created += 1

    duplicate_subscription_uuid = _panel_subscription_uuid(duplicate_panel_user)
    duplicate_sub = (
        subscriptions_by_panel_uuid.get(duplicate_subscription_uuid)
        if duplicate_subscription_uuid
        else None
    )
    if duplicate_sub and duplicate_sub is not target_sub:
        await subscription_dal.update_subscription(
            session,
            duplicate_sub.subscription_id,
            {
                "user_id": int(existing_user.user_id),
                "is_active": False,
                "skip_notifications": True,
                "status_from_panel": "MERGED_PANEL_DUPLICATE",
            },
        )
        duplicate_sub.user_id = int(existing_user.user_id)
        duplicate_sub.is_active = False
        duplicate_sub.skip_notifications = True
        duplicate_sub.status_from_panel = "MERGED_PANEL_DUPLICATE"
        subscriptions_updated += 1
    elif not duplicate_sub:
        await session.execute(
            update(Subscription)
            .where(Subscription.panel_user_uuid == duplicate_panel_uuid)
            .values(
                user_id=int(existing_user.user_id),
                is_active=False,
                skip_notifications=True,
                status_from_panel="MERGED_PANEL_DUPLICATE",
            )
        )

    if final_end_date:
        panel_payload = _panel_identity_payload_with_expiry(existing_user, expire_at=final_end_date)
        _log_sync_panel_patch(
            source="duplicate_panel_merge",
            user=existing_user,
            panel_uuid=keep_panel_uuid,
            update_payload=panel_payload,
            current_panel_user=keep_panel_user,
            reasons=["duplicate_panel_merge_extend"],
            panel_view="list",
        )
        panel_patches += 1
        await panel_service.update_user_details_on_panel(
            keep_panel_uuid,
            panel_payload,
            log_response=False,
        )

    deleted = await panel_service.delete_user_from_panel(
        duplicate_panel_uuid,
        log_response=False,
    )
    if deleted:
        logging.info(
            "Sync: absorbed duplicate panel UUID %s into kept panel UUID %s for user %s.",
            duplicate_panel_uuid,
            keep_panel_uuid,
            existing_user.user_id,
        )
    else:
        logging.warning(
            "Sync: failed to delete duplicate panel UUID %s after absorbing it into %s.",
            duplicate_panel_uuid,
            keep_panel_uuid,
        )

    return {
        "resolved": bool(deleted),
        "subscriptions_created": subscriptions_created,
        "subscriptions_updated": subscriptions_updated,
        "panel_patches": panel_patches,
    }


async def perform_sync(
    panel_service: PanelApiService,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
) -> dict:
    """Single-flight entry point — skips when another sync is already running."""
    if _sync_lock.locked():
        logging.info("perform_sync: skipped because another sync is already in progress")
        return {
            "status": "skipped",
            "details": "Another sync run is already in progress.",
            "errors": [],
            "users_processed": 0,
            "subs_synced": 0,
        }
    async with _sync_lock:
        return await _perform_sync_impl(
            panel_service=panel_service,
            session=session,
            settings=settings,
            i18n_instance=i18n_instance,
        )


async def _perform_sync_impl(
    panel_service: PanelApiService,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
) -> dict:
    """
    Perform panel synchronization and return results
    Returns dict with status, details, and sync statistics
    """
    panel_records_checked = 0
    users_found_in_db = 0
    users_updated = 0
    subscriptions_synced_count = 0
    sync_errors = []

    # Additional counters for detailed logging
    users_without_telegram_id = 0
    users_not_found_in_db = 0
    users_created = 0
    users_uuid_updated = 0
    subscriptions_created = 0
    subscriptions_updated = 0
    local_update_reason_counts: Counter[str] = Counter()
    panel_patch_reason_counts: Counter[str] = Counter()
    panel_patch_field_counts: Counter[str] = Counter()
    panel_patch_count = 0

    try:
        panel_users_data = await panel_service.get_all_panel_users()

        if panel_users_data is None:
            error_msg = "Failed to fetch users from panel or panel API issue."
            sync_errors.append(error_msg)
            await panel_sync_dal.update_panel_sync_status(session, "failed", error_msg)
            await session.commit()
            return {"status": "failed", "details": error_msg, "errors": sync_errors}

        if not panel_users_data:
            status_msg = "No users found in the panel to sync."
            await panel_sync_dal.update_panel_sync_status(session, "success", status_msg, 0, 0)
            await session.commit()
            return {
                "status": "success",
                "details": status_msg,
                "users_synced": 0,
                "subs_synced": 0,
            }

        total_panel_users = len(panel_users_data)
        logging.info(f"Starting sync for {total_panel_users} panel users.")
        sync_indexes = await _prefetch_sync_indexes(session, panel_users_data)
        users_by_telegram_id = sync_indexes["users_by_telegram_id"]
        users_by_user_id = sync_indexes["users_by_user_id"]
        users_by_panel_uuid = sync_indexes["users_by_panel_uuid"]
        users_by_email = sync_indexes["users_by_email"]
        subscriptions_by_panel_uuid = sync_indexes["subscriptions_by_panel_uuid"]
        active_subscriptions_by_user_panel = sync_indexes["active_subscriptions_by_user_panel"]
        panel_uuids_by_telegram_id = sync_indexes["panel_uuids_by_telegram_id"]
        panel_users_by_uuid = {
            str(panel_user["uuid"]): panel_user
            for panel_user in panel_users_data
            if panel_user.get("uuid")
        }

        for panel_user_dict in panel_users_data:
            try:
                panel_records_checked += 1
                panel_uuid = panel_user_dict.get("uuid")
                panel_user_dict.get("subscriptionUuid") or panel_user_dict.get("shortUuid")
                telegram_id_from_panel = _coerce_panel_telegram_id(
                    panel_user_dict.get("telegramId")
                )
                email_from_panel = _normalize_panel_email(panel_user_dict.get("email"))

                if not panel_uuid:
                    sync_errors.append(f"Panel user missing UUID: {panel_user_dict}")
                    logging.warning(f"Skipping panel user without UUID: {panel_user_dict}")
                    continue

                # Track users without telegram ID
                if not telegram_id_from_panel:
                    users_without_telegram_id += 1

                # Try to find existing user in local DB
                existing_user = None

                # First, try to find by telegram ID if available
                if telegram_id_from_panel:
                    existing_user = users_by_telegram_id.get(
                        telegram_id_from_panel
                    ) or users_by_user_id.get(telegram_id_from_panel)
                    if existing_user:
                        logging.debug(f"Found user by telegramId {telegram_id_from_panel}")

                # If not found by telegram ID, try to find by panel UUID.
                # The panel UUID is the strongest local link for subscription sync.
                if not existing_user:
                    existing_user = users_by_panel_uuid.get(panel_uuid)
                    if existing_user:
                        logging.debug(
                            f"Found user by panel UUID {panel_uuid}, telegramId: {existing_user.user_id}"  # noqa: E501
                        )
                        # Update telegram ID if it was missing in panel data but we have local user
                        if (
                            telegram_id_from_panel
                            and existing_user.user_id != telegram_id_from_panel
                        ):
                            logging.warning(
                                f"TelegramId mismatch: panel={telegram_id_from_panel}, local={existing_user.user_id}"  # noqa: E501
                            )

                # Finally, fall back to email. This mainly catches panel users that
                # were first imported as email-only identities.
                if not existing_user and email_from_panel:
                    existing_user = users_by_email.get(email_from_panel)
                    if existing_user:
                        logging.debug(f"Found user by email {email_from_panel}")

                if not existing_user:
                    users_not_found_in_db += 1
                    if telegram_id_from_panel:
                        # Create new user if they have telegram_id
                        try:
                            user_data = {
                                "user_id": telegram_id_from_panel,
                                "telegram_id": telegram_id_from_panel,
                                "email": email_from_panel,
                                "email_verified_at": (
                                    datetime.now(timezone.utc) if email_from_panel else None
                                ),
                                "username": None,  # Username will be updated when user interacts with bot  # noqa: E501
                                "first_name": None,  # Panel doesn't provide this info
                                "last_name": None,  # Panel doesn't provide this info
                                "language_code": "ru",  # Default language
                                "panel_user_uuid": panel_uuid,
                                "is_banned": False,
                                "referred_by_id": None,
                            }

                            new_user, was_created = await user_dal.create_user(session, user_data)
                            if was_created:
                                users_created += 1
                                logging.info(
                                    f"Created new user {telegram_id_from_panel} from panel sync with UUID {panel_uuid}"  # noqa: E501
                                )

                            existing_user = new_user
                            users_by_user_id[int(new_user.user_id)] = new_user
                            if new_user.telegram_id is not None:
                                users_by_telegram_id[int(new_user.telegram_id)] = new_user
                            users_by_panel_uuid[panel_uuid] = new_user
                            if email_from_panel:
                                users_by_email[email_from_panel] = new_user

                        except Exception as e_create:
                            sync_errors.append(
                                f"Error creating user {telegram_id_from_panel}: {str(e_create)}"
                            )
                            logging.error(
                                f"Error creating user {telegram_id_from_panel}: {e_create}"
                            )
                            continue
                    elif email_from_panel:
                        try:
                            new_user, was_created = await user_dal.create_email_user(
                                session,
                                email=email_from_panel,
                                language_code="ru",
                            )
                            new_user.panel_user_uuid = panel_uuid
                            if was_created:
                                users_created += 1
                                logging.info(
                                    f"Created new email user {new_user.user_id} from panel sync with UUID {panel_uuid}"  # noqa: E501
                                )
                            existing_user = new_user
                            users_by_user_id[int(new_user.user_id)] = new_user
                            users_by_panel_uuid[panel_uuid] = new_user
                            users_by_email[email_from_panel] = new_user
                        except Exception as e_create_email:
                            sync_errors.append(
                                f"Error creating email user {email_from_panel}: {str(e_create_email)}"  # noqa: E501
                            )
                            logging.error(
                                f"Error creating email user {email_from_panel}: {e_create_email}"
                            )
                            continue
                    else:
                        logging.debug(
                            f"Panel user with UUID {panel_uuid} (no telegramId) not found in local DB - skipping"  # noqa: E501
                        )
                        continue

                # User found in local DB
                users_found_in_db += 1
                user_was_updated = False
                user_update_reasons: list[str] = []

                # Get the actual user_id for subscription operations
                actual_user_id = existing_user.user_id
                is_duplicate_panel_identity = False

                # Update panel UUID if different
                if existing_user.panel_user_uuid != panel_uuid:
                    linked_uuid = existing_user.panel_user_uuid
                    linked_uuid_still_present = bool(
                        telegram_id_from_panel
                        and linked_uuid
                        and str(linked_uuid)
                        in panel_uuids_by_telegram_id.get(telegram_id_from_panel, set())
                    )
                    linked_uuid_present_on_panel = bool(
                        linked_uuid and str(linked_uuid) in panel_users_by_uuid
                    )
                    panel_uuid_owner = users_by_panel_uuid.get(panel_uuid)
                    if (
                        panel_uuid_owner
                        and panel_uuid_owner.user_id != existing_user.user_id
                        and not linked_uuid_still_present
                    ):
                        if linked_uuid_present_on_panel:
                            msg = (
                                f"Panel UUID {panel_uuid} for user {actual_user_id} is already "
                                f"linked to local user {panel_uuid_owner.user_id}, while current "
                                f"local panel UUID {linked_uuid} still exists on panel."
                            )
                            sync_errors.append(msg)
                            logging.warning("Sync: %s", msg)
                            continue

                        previous_panel_uuid = existing_user.panel_user_uuid
                        previous_owner_user_id = panel_uuid_owner.user_id
                        previous_owner_email = panel_uuid_owner.email
                        previous_owner_telegram_id = panel_uuid_owner.telegram_id
                        (
                            existing_user,
                            can_merge_panel_uuid_owner,
                        ) = await _merge_local_duplicate_panel_user_if_needed(
                            session,
                            existing_user=existing_user,
                            duplicate_panel_uuid=panel_uuid,
                        )
                        if not can_merge_panel_uuid_owner:
                            logging.warning(
                                "Sync: panel UUID %s is already linked to local user %s; "
                                "skipping reassignment to user %s because local merge failed.",
                                panel_uuid,
                                previous_owner_user_id,
                                actual_user_id,
                            )
                            continue

                        existing_user.panel_user_uuid = panel_uuid
                        actual_user_id = existing_user.user_id
                        user_was_updated = True
                        _append_unique(
                            user_update_reasons,
                            "panel_uuid_reassigned_after_local_merge",
                        )
                        users_uuid_updated += 1
                        if previous_panel_uuid:
                            users_by_panel_uuid.pop(str(previous_panel_uuid), None)
                        users_by_panel_uuid[panel_uuid] = existing_user
                        users_by_user_id.pop(int(previous_owner_user_id), None)
                        users_by_user_id[int(existing_user.user_id)] = existing_user
                        if previous_owner_telegram_id is not None:
                            users_by_telegram_id.pop(int(previous_owner_telegram_id), None)
                        if existing_user.telegram_id is not None:
                            users_by_telegram_id[int(existing_user.telegram_id)] = existing_user
                        if previous_owner_email:
                            users_by_email.pop(previous_owner_email.strip().lower(), None)
                        if existing_user.email:
                            users_by_email[existing_user.email.strip().lower()] = existing_user
                        logging.info(
                            "Sync: merged local user %s owning panel UUID %s into user %s "
                            "and reassigned stale local panel UUID %s.",
                            previous_owner_user_id,
                            panel_uuid,
                            actual_user_id,
                            previous_panel_uuid,
                        )
                    if linked_uuid_still_present:
                        is_duplicate_panel_identity = True
                        (
                            existing_user,
                            can_absorb_duplicate_panel_user,
                        ) = await _merge_local_duplicate_panel_user_if_needed(
                            session,
                            existing_user=existing_user,
                            duplicate_panel_uuid=panel_uuid,
                        )
                        if not can_absorb_duplicate_panel_user:
                            logging.warning(
                                "Sync: duplicate panel users share telegramId %s; keeping local panel UUID %s and skipping duplicate panel UUID %s because local duplicate merge failed.",  # noqa: E501
                                telegram_id_from_panel,
                                linked_uuid,
                                panel_uuid,
                            )
                            continue
                        actual_user_id = existing_user.user_id
                        users_by_panel_uuid[linked_uuid] = existing_user
                        if existing_user.telegram_id is not None:
                            users_by_telegram_id[int(existing_user.telegram_id)] = existing_user
                        users_by_user_id[int(existing_user.user_id)] = existing_user
                        if existing_user.email:
                            users_by_email[existing_user.email.strip().lower()] = existing_user
                        merge_result = await _absorb_duplicate_panel_identity(
                            session,
                            panel_service=panel_service,
                            existing_user=existing_user,
                            keep_panel_uuid=str(linked_uuid),
                            keep_panel_user=panel_users_by_uuid.get(str(linked_uuid)),
                            duplicate_panel_user=panel_user_dict,
                            settings=settings,
                            subscriptions_by_panel_uuid=subscriptions_by_panel_uuid,
                            active_subscriptions_by_user_panel=(active_subscriptions_by_user_panel),
                        )
                        subscriptions_created += int(merge_result["subscriptions_created"])
                        subscriptions_updated += int(merge_result["subscriptions_updated"])
                        subscriptions_synced_count += int(
                            merge_result["subscriptions_created"]
                        ) + int(merge_result["subscriptions_updated"])
                        merge_panel_patches = int(merge_result.get("panel_patches", 0))
                        if merge_panel_patches:
                            panel_patch_count += merge_panel_patches
                            panel_patch_reason_counts[
                                "duplicate_panel_merge_extend"
                            ] += merge_panel_patches
                        if merge_result["resolved"]:
                            users_updated += 1
                            users_uuid_updated += 1
                            local_update_reason_counts.update(
                                ["duplicate_panel_identity_resolved"]
                            )
                            panel_uuids_by_telegram_id.get(telegram_id_from_panel, set()).discard(
                                str(panel_uuid)
                            )
                            users_by_panel_uuid.pop(str(panel_uuid), None)
                            logging.info(
                                "Sync local update: user_id=%s telegram_id=%s panel_uuid=%s "
                                "reasons=%s",
                                actual_user_id,
                                existing_user.telegram_id,
                                linked_uuid,
                                "duplicate_panel_identity_resolved",
                            )
                        logging.warning(
                            "Sync: duplicate panel users share telegramId %s; kept local panel UUID %s and processed duplicate panel UUID %s.",  # noqa: E501
                            telegram_id_from_panel,
                            linked_uuid,
                            panel_uuid,
                        )
                        continue
                    elif existing_user.panel_user_uuid != panel_uuid:
                        existing_user.panel_user_uuid = panel_uuid
                        user_was_updated = True
                        _append_unique(user_update_reasons, "panel_uuid_synced")
                        users_uuid_updated += 1
                        users_by_panel_uuid[panel_uuid] = existing_user
                        logging.info(f"Updated panel UUID for user {actual_user_id}: {panel_uuid}")
                if not is_duplicate_panel_identity:
                    existing_user, email_was_bound = await _bind_panel_email_to_user(
                        session,
                        existing_user=existing_user,
                        email_from_panel=email_from_panel,
                        panel_uuid=panel_uuid,
                    )
                    if email_was_bound:
                        user_was_updated = True
                        _append_unique(user_update_reasons, "email_bound_from_panel")
                        if email_from_panel:
                            users_by_email[email_from_panel] = existing_user
                    if (
                        telegram_id_from_panel
                        and existing_user.telegram_id != telegram_id_from_panel
                    ):
                        existing_user.telegram_id = telegram_id_from_panel
                        user_was_updated = True
                        _append_unique(user_update_reasons, "telegram_id_bound_from_panel")
                        users_by_telegram_id[telegram_id_from_panel] = existing_user

                lifetime_used = _extract_lifetime_used_traffic_bytes(panel_user_dict)
                if lifetime_used is not None and _should_update_lifetime_used_traffic(
                    existing_user,
                    lifetime_used,
                    now=datetime.now(timezone.utc),
                    settings=settings,
                    is_duplicate_panel_identity=is_duplicate_panel_identity,
                ):
                    existing_user.lifetime_used_traffic_bytes = lifetime_used
                    existing_user.lifetime_used_traffic_synced_at = datetime.now(timezone.utc)
                    user_was_updated = True
                    _append_unique(user_update_reasons, "lifetime_traffic_synced")

                # Keep structural identity fields in panel and clean legacy email from
                # description. Plain description text is intentionally not canonical.
                try:
                    if panel_uuid and existing_user and not is_duplicate_panel_identity:
                        description_text = _panel_description_for_user(existing_user)
                        desired_description = description_text.strip()
                        (
                            panel_user_for_identity,
                            missing_identity_fields_match,
                        ) = await _panel_identity_view_for_comparison(
                            panel_service,
                            panel_uuid,
                            panel_user_dict,
                            existing_user,
                            desired_description,
                        )
                        current_description = panel_user_for_identity.get("description")
                        description_has_email = _description_contains_email(
                            current_description,
                            existing_user.email,
                        )
                        identity_matches = _panel_identity_matches_user(
                            panel_user_for_identity,
                            existing_user,
                            "",
                            missing_identity_fields_match=missing_identity_fields_match,
                        )
                        panel_payload = _panel_identity_fields_update_payload(existing_user)
                        if description_has_email:
                            panel_payload["description"] = _description_without_email(
                                current_description,
                                existing_user.email,
                            )
                        if description_has_email or not identity_matches:
                            panel_changes = _panel_update_changes(
                                panel_user_for_identity,
                                panel_payload,
                            )
                            panel_reasons = _identity_panel_update_reasons(
                                panel_changes,
                                description_has_email=description_has_email,
                            )
                            changed_fields = _log_sync_panel_patch(
                                source="identity_sync",
                                user=existing_user,
                                panel_uuid=panel_uuid,
                                update_payload=panel_payload,
                                current_panel_user=panel_user_for_identity,
                                reasons=panel_reasons,
                                panel_view=(
                                    "list"
                                    if missing_identity_fields_match
                                    else "full_fetch"
                                ),
                            )
                            panel_patch_count += 1
                            panel_patch_reason_counts.update(panel_reasons)
                            panel_patch_field_counts.update(changed_fields)
                            await panel_service.update_user_details_on_panel(
                                panel_uuid,
                                panel_payload,
                            )
                except Exception as e_desc:
                    logging.warning(
                        f"Sync: Failed to update panel identity for panel user {panel_uuid} (tg {actual_user_id}): {e_desc}"  # noqa: E501
                    )

                # Sync subscription data
                panel_expire_at_iso = panel_user_dict.get("expireAt")
                panel_status = panel_user_dict.get("status", "UNKNOWN")

                if panel_expire_at_iso:
                    try:
                        panel_expire_at = datetime.fromisoformat(
                            panel_expire_at_iso.replace("Z", "+00:00")
                        )

                        # Prefer syncing by concrete subscription UUID (shortUuid/subscriptionUuid)
                        subscription_uuid_from_panel = panel_user_dict.get(
                            "subscriptionUuid"
                        ) or panel_user_dict.get("shortUuid")

                        if subscription_uuid_from_panel:
                            # Если панель говорит, что подписка ACTIVE — сначала деактивируем все другие активные  # noqa: E501
                            if panel_status == "ACTIVE":
                                await session.execute(
                                    update(Subscription)
                                    .where(
                                        Subscription.panel_user_uuid == panel_uuid,
                                        Subscription.is_active.is_(True),
                                        or_(
                                            Subscription.panel_subscription_uuid
                                            != subscription_uuid_from_panel,
                                            Subscription.panel_subscription_uuid.is_(None),
                                        ),
                                    )
                                    .values(
                                        is_active=False,
                                        status_from_panel="INACTIVE",
                                    )
                                )

                            # Try to find subscription by its panel_subscription_uuid first (idempotent)  # noqa: E501
                            existing_sub_by_uuid = subscriptions_by_panel_uuid.get(
                                subscription_uuid_from_panel
                            )

                            if existing_sub_by_uuid:
                                update_payload = {
                                    "user_id": actual_user_id,
                                    "panel_user_uuid": panel_uuid,
                                    "end_date": panel_expire_at,
                                    "is_active": panel_status == "ACTIVE",
                                    "status_from_panel": panel_status,
                                }
                                update_delta = _subscription_update_delta(
                                    existing_sub_by_uuid, update_payload
                                )
                                if update_delta:
                                    # Atomic update of changed relevant fields
                                    await subscription_dal.update_subscription(
                                        session,
                                        existing_sub_by_uuid.subscription_id,
                                        update_delta,
                                    )
                                    subscriptions_updated += 1
                                    user_was_updated = True
                                    _append_unique(user_update_reasons, "subscription_updated")
                                subscriptions_synced_count += 1
                                logging.debug(
                                    f"Synced existing subscription {existing_sub_by_uuid.subscription_id} "  # noqa: E501
                                    f"for user {actual_user_id}: expires {panel_expire_at}, status {panel_status}"  # noqa: E501
                                )
                            else:
                                # Create a new subscription only when we have a concrete subscription UUID  # noqa: E501
                                sub_payload = {
                                    "user_id": actual_user_id,
                                    "panel_user_uuid": panel_uuid,
                                    "panel_subscription_uuid": subscription_uuid_from_panel,
                                    # Do not guess precise start_date from panel; keep nullable
                                    "start_date": None,
                                    "end_date": panel_expire_at,
                                    "duration_months": None,
                                    "is_active": panel_status == "ACTIVE",
                                    "status_from_panel": panel_status,
                                    "traffic_limit_bytes": settings.user_traffic_limit_bytes,
                                    "auto_renew_enabled": False,
                                }
                                created_sub = await subscription_dal.upsert_subscription(
                                    session, sub_payload
                                )
                                subscriptions_by_panel_uuid[subscription_uuid_from_panel] = (
                                    created_sub
                                )
                                if created_sub.is_active and created_sub.end_date > datetime.now(
                                    timezone.utc
                                ):
                                    active_subscriptions_by_user_panel[
                                        (int(created_sub.user_id), created_sub.panel_user_uuid)
                                    ] = created_sub
                                subscriptions_synced_count += 1
                                subscriptions_created += 1
                                user_was_updated = True
                                _append_unique(user_update_reasons, "subscription_created")
                                logging.debug(
                                    f"Created subscription {created_sub.subscription_id} "
                                    f"for user {actual_user_id} by panel_sub_uuid {subscription_uuid_from_panel}"  # noqa: E501
                                )
                        else:
                            # No subscription UUID from panel: only update an already active subscription for this user/panel UUID  # noqa: E501
                            active_sub = active_subscriptions_by_user_panel.get(
                                (actual_user_id, panel_uuid)
                            )
                            if active_sub:
                                update_payload = {
                                    "end_date": panel_expire_at,
                                    "is_active": panel_status == "ACTIVE",
                                    "status_from_panel": panel_status,
                                }
                                update_delta = _subscription_update_delta(
                                    active_sub, update_payload
                                )
                                if update_delta:
                                    await subscription_dal.update_subscription(
                                        session,
                                        active_sub.subscription_id,
                                        update_delta,
                                    )
                                    subscriptions_updated += 1
                                    user_was_updated = True
                                    _append_unique(user_update_reasons, "subscription_updated")
                                subscriptions_synced_count += 1
                                logging.debug(
                                    f"Updated active subscription {active_sub.subscription_id} "
                                    f"for user {actual_user_id}: expires {panel_expire_at}, status {panel_status}"  # noqa: E501
                                )
                            else:
                                # Without a concrete subscription UUID we avoid creating new records to keep sync idempotent  # noqa: E501
                                logging.debug(
                                    f"No subscriptionUuid for panel user {panel_uuid}; skipped creation for user {actual_user_id}"  # noqa: E501
                                )

                    except Exception as e:
                        sync_errors.append(
                            f"Error syncing subscription for user {actual_user_id}: {str(e)}"
                        )
                        logging.error(f"Error syncing subscription for user {actual_user_id}: {e}")

                if user_was_updated:
                    users_updated += 1
                    if not user_update_reasons:
                        user_update_reasons.append("unspecified")
                    local_update_reason_counts.update(user_update_reasons)
                    logging.info(
                        "Sync local update: user_id=%s telegram_id=%s panel_uuid=%s reasons=%s",
                        actual_user_id,
                        existing_user.telegram_id,
                        panel_uuid,
                        ",".join(user_update_reasons),
                    )

            except Exception as e_user:
                sync_errors.append(
                    f"Error processing panel user {panel_user_dict.get('uuid', 'unknown')}: {str(e_user)}"  # noqa: E501
                )
                logging.error(f"Error syncing user: {e_user}")

        # Update sync status
        status = "completed_with_errors" if sync_errors else "completed"
        # Build additional stats
        default_lang = settings.DEFAULT_LANGUAGE
        additional_stats = ""
        if users_without_telegram_id > 0:
            additional_stats += i18n_instance.gettext(
                default_lang,
                "admin_sync_no_telegram_id",
                count=users_without_telegram_id,
            )
        if users_not_found_in_db > 0:
            additional_stats += i18n_instance.gettext(
                default_lang,
                "admin_sync_not_found_in_db",
                count=users_not_found_in_db,
            )
        if sync_errors:
            additional_stats += i18n_instance.gettext(
                default_lang, "admin_sync_errors", count=len(sync_errors)
            )

        # Build full details using localization
        details = i18n_instance.gettext(
            default_lang,
            "admin_sync_details",
            panel_records_checked=panel_records_checked,
            users_found_in_db=users_found_in_db,
            users_created=users_created,
            users_updated=users_updated,
            subscriptions_synced_count=subscriptions_synced_count,
            subscriptions_created=subscriptions_created,
            subscriptions_updated=subscriptions_updated,
            additional_stats=additional_stats,
        )

        await panel_sync_dal.update_panel_sync_status(
            session,
            status,
            details,
            panel_records_checked,
            subscriptions_synced_count,
        )
        await session.commit()

        # Detailed logging summary
        logging.info("Sync completed - Summary:")
        logging.info(f"  Panel records checked: {panel_records_checked}")
        logging.info(f"  Users without telegramId: {users_without_telegram_id}")
        logging.info(f"  Users not found in local DB: {users_not_found_in_db}")
        logging.info(f"  Users found in local DB: {users_found_in_db}")
        logging.info(f"  Users created: {users_created}")
        logging.info(f"  Users with UUID updated: {users_uuid_updated}")
        logging.info(f"  Users updated overall: {users_updated}")
        logging.info("  Local update reasons: %s", _format_counter(local_update_reason_counts))
        logging.info(f"  Panel PATCHes from sync: {panel_patch_count}")
        logging.info("  Panel PATCH reasons: %s", _format_counter(panel_patch_reason_counts))
        logging.info("  Panel PATCH fields: %s", _format_counter(panel_patch_field_counts))
        logging.info(f"  Subscriptions total synced: {subscriptions_synced_count}")
        logging.info(f"  Subscriptions created: {subscriptions_created}")
        logging.info(f"  Subscriptions updated: {subscriptions_updated}")
        logging.info(f"  Sync errors: {len(sync_errors)}")

        return {
            "status": status,
            "details": details,
            "users_processed": panel_records_checked,
            "users_synced": users_found_in_db,
            "users_created": users_created,
            "subs_synced": subscriptions_synced_count,
            "errors": sync_errors,
        }

    except Exception as e_sync_global:
        await session.rollback()
        logging.error(f"Global error during sync: {e_sync_global}", exc_info=True)
        error_detail = f"Unexpected error during sync: {str(e_sync_global)}"

        await panel_sync_dal.update_panel_sync_status(
            session,
            "failed",
            error_detail,
            panel_records_checked,
            subscriptions_synced_count,
        )

        return {
            "status": "failed",
            "details": error_detail,
            "errors": [str(e_sync_global)],
        }


@router.message(Command("sync"))
async def sync_command_handler(
    message_event: Union[types.Message, types.CallbackQuery],
    bot: Bot,
    settings: Settings,
    i18n_data: dict,
    panel_service: PanelApiService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        logging.error("i18n missing in sync_command_handler")

        if isinstance(message_event, types.Message):
            await message_event.answer("Language error.")
        elif isinstance(message_event, types.CallbackQuery):
            await message_event.answer("Language error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    target_chat_id = (
        message_event.chat.id
        if isinstance(message_event, types.Message)
        else (message_event.message.chat.id if message_event.message else None)
    )
    if not target_chat_id:
        logging.error("Sync handler: could not determine target_chat_id.")
        if isinstance(message_event, types.CallbackQuery):
            await message_event.answer("Error initiating sync.", show_alert=True)
        return

    if isinstance(message_event, types.Message):
        await message_event.answer(_("sync_started_simple"))

    logging.info(f"Admin ({message_event.from_user.id}) triggered panel sync.")

    # Use the extracted perform_sync function
    try:
        sync_result = await perform_sync(panel_service, session, settings, i18n)

        status = sync_result.get("status")
        details = sync_result.get("details", "No details available")
        errors = sync_result.get("errors", [])

        # Simple confirmation message to admin
        if status == "failed":
            await bot.send_message(target_chat_id, _("sync_failed_simple"))
        elif status == "completed_with_errors":
            await bot.send_message(
                target_chat_id,
                _("sync_errors_simple", errors_count=len(errors)),
            )
        else:
            await bot.send_message(target_chat_id, _("sync_success_simple"))

        # Send notification to log channel with proper thread handling
        try:
            notification_service = NotificationService(bot, settings, i18n)
            await notification_service.notify_panel_sync(
                status,
                details,
                sync_result.get("users_processed", 0),
                sync_result.get("subs_synced", 0),
            )
        except Exception as e_notification:
            logging.error(f"Failed to send sync notification: {e_notification}")

    except Exception as e_sync_global:
        logging.error(f"Global error during /sync command: {e_sync_global}", exc_info=True)
        await bot.send_message(target_chat_id, _("sync_critical_error"))

        # Send notification to log channel about failure
        try:
            notification_service = NotificationService(bot, settings, i18n)
            await notification_service.notify_panel_sync("failed", str(e_sync_global), 0, 0)
        except Exception as e_notification:
            logging.error(f"Failed to send sync failure notification: {e_notification}")


@router.message(Command("syncstatus"))
async def sync_status_command_handler(
    message: types.Message, i18n_data: dict, settings: Settings, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        await message.answer("Language error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    status_record_model = await panel_sync_dal.get_panel_sync_status(session)
    response_text = ""
    if status_record_model:
        last_time_val = status_record_model.last_sync_time
        last_time_str = last_time_val.strftime("%Y-%m-%d %H:%M:%S UTC") if last_time_val else "N/A"

        details_val = status_record_model.details
        details_str = details_val or "N/A"

        response_text = (
            f"<b>{_('admin_stats_last_sync_header')}</b>\n"
            f"  {_('admin_stats_sync_time')}: {last_time_str}\n"
            f"  {_('admin_stats_sync_status')}: {status_record_model.status}\n"
            f"  {_('admin_stats_sync_users_processed')}: {status_record_model.users_processed_from_panel}\n"  # noqa: E501
            f"  {_('admin_stats_sync_subs_synced')}: {status_record_model.subscriptions_synced}\n"
            f"  {_('admin_stats_sync_details_label')}: {details_str}"
        )
    else:
        response_text = _("admin_sync_status_never_run")

    await message.answer(response_text, parse_mode="HTML")
