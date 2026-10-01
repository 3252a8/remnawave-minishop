import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from db.advisory_locks import commit_subscription_background_sync_batch
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

logger = logging.getLogger(__name__)


async def _create_panel_user(
    session: AsyncSession,
    *,
    panel_uuid: str,
    panel_username: str | None,
    panel_origin: str | None,
    telegram_id: int | None,
    email: str | None,
    language_code: str,
) -> tuple[User, bool]:
    """Import a new panel account without treating panel email as verified."""
    user_data = {
        "panel_user_uuid": panel_uuid,
        "panel_username": panel_username,
        "panel_origin": panel_origin,
        "telegram_id": telegram_id,
        "email": email,
        "language_code": language_code,
    }
    # A concurrent registration can win a unique email/Telegram constraint.
    # Keep that failure local to this panel record instead of aborting the batch.
    async with session.begin_nested():
        return await user_dal.create_user(session, user_data, registered_via="panel_sync")


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
    if panel_uuids:
        user_filters.append(User.panel_user_uuid.in_(panel_uuids))
    if emails:
        user_filters.append(func.lower(User.email).in_(emails))
    if user_filters:
        result = await session.execute(
            select(User).where(or_(*user_filters)).execution_options(populate_existing=True)
        )
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
            select(Subscription)
            .where(Subscription.panel_subscription_uuid.in_(panel_subscription_uuids))
            .execution_options(populate_existing=True)
        )
        subscriptions_by_panel_uuid = {
            str(sub.panel_subscription_uuid): sub
            for sub in result.scalars().unique().all()
            if sub.panel_subscription_uuid
        }

    active_subscriptions_by_user_panel: dict[tuple[int, str], Subscription] = {}
    subscriptions_by_user_panel: dict[tuple[int, str], Subscription] = {}
    resolved_user_ids = {int(user.user_id) for user in users_by_user_id.values()}
    if panel_uuids or resolved_user_ids:
        identity_filters = []
        if panel_uuids:
            identity_filters.append(Subscription.panel_user_uuid.in_(panel_uuids))
        if resolved_user_ids:
            # During Remnawave 2.x -> 3.x upgrades, the panel's current numeric
            # user refs do not match the UUID refs persisted locally yet. User
            # identity (Telegram/email) still lets us prefetch those rows and
            # relink them instead of creating duplicate subscriptions.
            identity_filters.append(Subscription.user_id.in_(resolved_user_ids))
        result = await session.execute(
            select(Subscription)
            .where(
                or_(*identity_filters),
            )
            .distinct(Subscription.user_id, Subscription.panel_user_uuid, Subscription.is_active)
            .order_by(
                Subscription.user_id,
                Subscription.panel_user_uuid,
                Subscription.is_active,
                Subscription.end_date.desc(),
            )
            .execution_options(populate_existing=True)
        )
        for sub in sorted(
            result.scalars().unique().all(), key=lambda row: row.end_date, reverse=True
        ):
            subscriptions_by_user_panel.setdefault((int(sub.user_id), sub.panel_user_uuid), sub)
            if not sub.is_active or sub.end_date <= datetime.now(UTC):
                continue
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
        "subscriptions_by_user_panel": subscriptions_by_user_panel,
        "panel_uuids_by_telegram_id": panel_uuids_by_telegram_id,
    }


def _extract_lifetime_used_traffic_bytes(panel_user_data: dict) -> int | None:
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
    email_from_panel: str | None,
    panel_uuid: str,
) -> tuple[User, bool]:
    """Panel metadata is not proof of control over an email address."""
    del session
    if email_from_panel and existing_user.email != email_from_panel:
        logger.warning(
            "Panel email for UUID %s differs from confirmed local email; manual review required.",
            panel_uuid,
        )
    return existing_user, False


async def _merge_local_duplicate_panel_user_if_needed(
    session: AsyncSession,
    *,
    existing_user: User,
    duplicate_panel_uuid: str,
) -> tuple[User, bool]:
    duplicate_local_user = await user_dal.get_user_by_panel_uuid(session, duplicate_panel_uuid)
    if not duplicate_local_user or duplicate_local_user.user_id == existing_user.user_id:
        return existing_user, True

    logger.warning(
        "Sync: panel UUID %s belongs to another local account %s; "
        "explicit two-account merge required.",
        duplicate_panel_uuid,
        duplicate_local_user.user_id,
    )
    return existing_user, False


def _panel_identity_payload_with_expiry(
    user: User,
    *,
    expire_at: datetime,
) -> dict[str, Any]:
    payload = _panel_identity_fields_update_payload(user)
    payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if expire_at > datetime.now(UTC):
        payload["status"] = "ACTIVE"
    return payload


async def _absorb_duplicate_panel_identity(
    session: AsyncSession,
    *,
    panel_service: PanelApiService,
    existing_user: User,
    keep_panel_uuid: str,
    keep_panel_user: dict[str, Any] | None,
    duplicate_panel_user: dict[str, Any],
    settings: Settings,
    subscriptions_by_panel_uuid: dict[str, Subscription],
    active_subscriptions_by_user_panel: dict[tuple[int, str], Subscription],
) -> dict[str, int | bool]:
    duplicate_panel_uuid = str(duplicate_panel_user.get("uuid") or "")
    keep_subscription_uuid = _panel_subscription_uuid(keep_panel_user or {})
    duplicate_subscription_uuid = _panel_subscription_uuid(duplicate_panel_user)
    if (
        not duplicate_panel_uuid
        or not keep_subscription_uuid
        or not duplicate_subscription_uuid
        or duplicate_panel_uuid == keep_panel_uuid
        or duplicate_subscription_uuid == keep_subscription_uuid
    ):
        return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}

    await user_dal.lock_user_entitlement(session, int(existing_user.user_id))
    subscriptions_created = 0
    subscriptions_updated = 0
    panel_patches = 0
    now = datetime.now(UTC)
    duplicate_expire_at = _panel_expire_at(duplicate_panel_user)
    duplicate_status = str(duplicate_panel_user.get("status") or "").upper()
    duplicate_is_active = bool(
        duplicate_expire_at and duplicate_status == "ACTIVE" and duplicate_expire_at > now
    )

    target_sub = (
        subscriptions_by_panel_uuid.get(keep_subscription_uuid) if keep_subscription_uuid else None
    )
    if not target_sub:
        target_sub = active_subscriptions_by_user_panel.get(
            (int(existing_user.user_id), keep_panel_uuid)
        )
    duplicate_sub = subscriptions_by_panel_uuid.get(duplicate_subscription_uuid)
    if target_sub is not None and target_sub is duplicate_sub:
        return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}
    for subscription in (target_sub, duplicate_sub):
        if subscription is not None:
            await session.refresh(subscription)
            if int(subscription.user_id) != int(existing_user.user_id):
                return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}

    final_end_date: datetime | None = None
    already_transferred = bool(
        duplicate_sub and duplicate_sub.status_from_panel == "MERGED_PANEL_DUPLICATE"
    )
    has_transferred_period = bool(
        already_transferred and duplicate_sub and _as_utc(duplicate_sub.end_date) > now
    )
    if has_transferred_period or (
        not already_transferred and duplicate_is_active and duplicate_expire_at
    ):
        keep_end = _panel_expire_at(keep_panel_user or {}) or now
        base_end = max(now, keep_end, _as_utc(target_sub.end_date) if target_sub else now)
        if already_transferred and duplicate_sub:
            final_end_date = max(base_end, _as_utc(duplicate_sub.end_date))
        elif duplicate_expire_at:
            final_end_date = base_end + max(timedelta(0), duplicate_expire_at - now)
        if target_sub:
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
        else:
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
                    "traffic_limit_bytes": settings.user_traffic_limit_bytes,
                    "auto_renew_enabled": False,
                },
            )
            subscriptions_by_panel_uuid[keep_subscription_uuid] = created_sub
            active_subscriptions_by_user_panel[
                (int(created_sub.user_id), created_sub.panel_user_uuid)
            ] = created_sub
            subscriptions_created += 1
            target_sub = created_sub

    # The inactive source row is the durable transfer receipt. Its end date
    # records the resulting expiry, so retries cannot add the same period twice,
    # even if a subsequent panel snapshot temporarily restores an older expiry.
    transfer_end_date = final_end_date or now
    source_payload = {
        "user_id": int(existing_user.user_id),
        "is_active": False,
        "skip_notifications": True,
        "status_from_panel": "MERGED_PANEL_DUPLICATE",
        "end_date": transfer_end_date,
    }
    if duplicate_sub and duplicate_sub is not target_sub:
        await subscription_dal.update_subscription(
            session,
            duplicate_sub.subscription_id,
            source_payload,
        )
        for key, value in source_payload.items():
            setattr(duplicate_sub, key, value)
        subscriptions_updated += 1
    elif not duplicate_sub:
        duplicate_sub = await subscription_dal.upsert_subscription(
            session,
            {
                **source_payload,
                "panel_user_uuid": duplicate_panel_uuid,
                "panel_subscription_uuid": duplicate_subscription_uuid,
                "auto_renew_enabled": False,
            },
        )
        subscriptions_by_panel_uuid[duplicate_subscription_uuid] = duplicate_sub
        subscriptions_created += 1

    # Persist the receipt before any external mutation. Reacquire the same
    # locks and reread the target so a concurrent payment is never overwritten.
    await commit_subscription_background_sync_batch(session)
    await user_dal.lock_user_entitlement(session, int(existing_user.user_id))
    if final_end_date and target_sub:
        await session.refresh(target_sub)
        final_end_date = max(final_end_date, _as_utc(target_sub.end_date))

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
        updated = await panel_service.update_user_details_on_panel(
            keep_panel_uuid,
            panel_payload,
            log_response=False,
        )
        if not updated:
            return {
                "resolved": False,
                "subscriptions_created": subscriptions_created,
                "subscriptions_updated": subscriptions_updated,
                "panel_patches": panel_patches,
            }
        if keep_panel_user is not None:
            keep_panel_user.update(panel_payload)

    deleted = await panel_service.delete_user_from_panel(
        duplicate_panel_uuid,
        log_response=False,
    )
    if deleted:
        logger.info(
            "Sync: absorbed duplicate panel UUID %s into kept panel UUID %s for user %s.",
            duplicate_panel_uuid,
            keep_panel_uuid,
            existing_user.user_id,
        )
    else:
        logger.warning(
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
