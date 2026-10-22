import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_compat import numeric_panel_user_id
from db.dal import user_dal
from db.models import Subscription, User

from .sync_admin_common import (
    _coerce_panel_telegram_id,
    _normalize_panel_email,
)

logger = logging.getLogger(__name__)


def _is_uuid_reference(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _select_existing_subscription_for_panel_sync(
    *,
    user_id: int,
    panel_uuid: str,
    panel_subscription_uuid: str,
    previous_panel_uuid: str | None,
    subscriptions_by_panel_uuid: dict[str, Subscription],
    active_subscriptions_by_user_panel: dict[tuple[int, str], Subscription],
    subscriptions_by_user_panel: dict[tuple[int, str], Subscription],
    numeric_generation: bool = False,
    subscriptions_by_user: dict[int, dict[str, Subscription]] | None = None,
) -> Subscription | None:
    existing = subscriptions_by_panel_uuid.get(panel_subscription_uuid)
    if existing is not None:
        return existing

    active = active_subscriptions_by_user_panel.get((user_id, panel_uuid))
    if active is not None and not active.panel_subscription_uuid:
        return active
    if previous_panel_uuid:
        return subscriptions_by_user_panel.get((user_id, previous_panel_uuid))
    if not numeric_generation or numeric_panel_user_id(panel_uuid) is None:
        return None

    # An older worker could update the user reference without updating the
    # subscription link. Only adopt the explicit UUID -> short-link transition;
    # a different existing short link still represents a distinct subscription.
    current = active or subscriptions_by_user_panel.get((user_id, panel_uuid))
    if current is not None:
        if _is_uuid_reference(str(current.panel_subscription_uuid or "")) and not (
            _is_uuid_reference(panel_subscription_uuid)
        ):
            return current
        return None

    # The user may already have a numeric reference while its subscriptions
    # still have the old UUID. Multiple panel identities are ambiguous and must
    # retain their separate subscription records.
    owned = (subscriptions_by_user or {}).get(user_id, {})
    if len(owned) == 1:
        old_panel_uuid, subscription = next(iter(owned.items()))
        if _is_uuid_reference(old_panel_uuid):
            return active_subscriptions_by_user_panel.get((user_id, old_panel_uuid)) or subscription
    return None


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
    panel_usernames: set[str] = set()
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
        username = str(panel_user.get("username") or "").strip()
        if username:
            panel_usernames.add(username)
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
    if panel_usernames:
        user_filters.extend(
            (User.panel_username.in_(panel_usernames), User.minishop_id.in_(panel_usernames))
        )
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
    subscriptions_by_user: dict[int, dict[str, Subscription]] = {}
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
            subscriptions_by_user.setdefault(int(sub.user_id), {}).setdefault(
                str(sub.panel_user_uuid), sub
            )
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
        "subscriptions_by_user": subscriptions_by_user,
        "numeric_generation": bool(panel_uuids)
        and all(numeric_panel_user_id(value) is not None for value in panel_uuids),
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
