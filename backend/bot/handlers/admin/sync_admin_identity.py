import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from db.dal import subscription_dal, user_dal
from db.models import Subscription, User

from .sync_admin_common import (
    _as_utc,
    _coerce_panel_telegram_id,
    _log_sync_panel_patch,
    _normalize_panel_email,
    _panel_expire_at,
    _panel_identity_fields_update_payload,
    _panel_subscription_uuid,
    _subscription_update_delta,
)


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
    existing_user: User,
    email_from_panel: Optional[str],
    panel_uuid: str,
) -> tuple[User, bool]:
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
                    reason="panel_sync",
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
            reason="panel_sync",
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
