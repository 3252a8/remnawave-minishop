import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.context import (
    get_optional_subscription_service,
)
from bot.infra.auto_renew import (
    managed_recurring_service_for,
    stop_provider_managed_recurrence,
)
from bot.payment_providers.shared import service_manages_recurrence
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.text_sanitizer import sanitize_display_name, sanitize_username
from config.settings import Settings
from db.dal import subscription_dal, user_dal
from db.dal.user_dal import UserMergeConflictError
from db.models import User

from .auth_common import (
    _telegram_photo_url_value,
)
from .common import (
    _format_webapp_datetime,
    _normalize_language,
    _telegram_id_for_user,
)

logger = logging.getLogger(__name__)


async def _sync_panel_identity_for_user(
    request: web.Request,
    user: User,
    *,
    expire_at: datetime | None = None,
) -> bool:
    if not getattr(user, "panel_user_uuid", None):
        return False
    subscription_service: SubscriptionService | None = get_optional_subscription_service(request)
    if not subscription_service or not subscription_service.panel_service:
        return False

    payload: dict[str, Any] = {}
    telegram_id = _telegram_id_for_user(user)
    if telegram_id:
        payload["telegramId"] = telegram_id
    if user.email:
        payload["email"] = user.email
    if expire_at is not None:
        if expire_at.tzinfo is None:
            expire_at = expire_at.replace(tzinfo=UTC)
        payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if expire_at > datetime.now(UTC):
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
    source_panel_uuid: str | None,
    final_panel_uuid: str | None,
) -> bool:
    if not source_panel_uuid or not final_panel_uuid or source_panel_uuid == final_panel_uuid:
        return True

    subscription_service: SubscriptionService | None = get_optional_subscription_service(request)
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


async def _merge_users_for_web(
    request: web.Request,
    session: AsyncSession,
    *,
    source_user_id: int,
    target_user_id: int,
    reason: str,
    send_user_email: bool,
) -> User:
    """Merge two users while keeping at most one recurring billing agreement."""

    subscription_service: SubscriptionService | None = get_optional_subscription_service(request)

    async def cancel_source_recurring(
        merge_session: AsyncSession,
        user_id: int,
        subscription: Any,
        managed_providers: tuple[str, ...],
    ) -> bool:
        try:
            for provider in managed_providers:
                managed_service = managed_recurring_service_for(
                    subscription_service,
                    provider,
                )
                if not service_manages_recurrence(managed_service):
                    return False
                if not await stop_provider_managed_recurrence(
                    subscription_service,
                    merge_session,
                    user_id=user_id,
                    provider=provider,
                ):
                    return False
            if subscription is not None:
                await subscription_dal.set_auto_renew(
                    merge_session,
                    int(subscription.subscription_id),
                    False,
                    stop_reason="account_merged",
                )
            return True
        except Exception:
            logger.exception(
                "Failed to cancel recurring billing before merging user %s",
                user_id,
            )
            return False

    return await user_dal.merge_users(
        session,
        source_user_id=source_user_id,
        target_user_id=target_user_id,
        reason=reason,
        send_user_email=send_user_email,
        cancel_source_recurring=cancel_source_recurring,
    )


async def _sync_merged_panel_identity_for_user(
    request: web.Request,
    user: User,
    *,
    source_panel_uuid: str | None,
    final_panel_uuid: str | None,
    expire_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> bool:
    # Remnawave keeps email/telegramId unique. Remove the losing panel identity
    # before patching the surviving one so merged accounts can accept both IDs.
    removed = await _delete_merged_source_panel_user(
        request,
        source_panel_uuid=source_panel_uuid,
        final_panel_uuid=final_panel_uuid or getattr(user, "panel_user_uuid", None),
    )
    if not removed:
        logger.warning(
            "Merged source panel user %s could not be removed; continuing entitlement sync",
            source_panel_uuid,
        )

    subscription_service: SubscriptionService = get_optional_subscription_service(request)
    sync_entitlements = getattr(
        subscription_service,
        "sync_main_traffic_limit_to_panel",
        None,
    )
    if session is not None and callable(sync_entitlements):
        synced = await sync_entitlements(session, int(user.user_id))
        await session.commit()
        if synced:
            return removed
    identity_synced = await _sync_panel_identity_for_user(request, user, expire_at=expire_at)
    return removed and identity_synced


async def _build_account_merge_notice(
    session: AsyncSession,
    *,
    merged_user: User,
    source_user_id: int,
    source_panel_uuid: str | None,
    settings: Settings,
) -> dict[str, Any]:
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
        final_end_date = final_end_date.replace(tzinfo=UTC)

    primary_panel_uuid = merged_user.panel_user_uuid
    removed_panel_uuid = source_panel_uuid
    if source_panel_uuid and source_panel_uuid == primary_panel_uuid:
        removed_panel_uuid = None

    return {
        "merged": True,
        "language": _normalize_language(merged_user.language_code or settings.DEFAULT_LANGUAGE),
        "primary_user_id": int(merged_user.user_id),
        "removed_user_id": int(source_user_id),
        "primary_panel_user_uuid": primary_panel_uuid,
        "removed_panel_user_uuid": removed_panel_uuid,
        "final_end_date": final_end_date.isoformat() if final_end_date else None,
        "final_end_date_text": _format_webapp_datetime(final_end_date),
    }


def _apply_telegram_profile_to_user(
    user: User,
    telegram_user: dict[str, Any],
    settings: Settings,
) -> None:
    language_code = _normalize_language(
        user.language_code or telegram_user.get("language_code") or settings.DEFAULT_LANGUAGE
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
    telegram_user: dict[str, Any],
    settings: Settings,
    merge_reason: str = "telegram_link",
    merge_send_user_email: bool = False,
) -> User:
    telegram_id = int(telegram_user["id"])
    current_user = await user_dal.lock_user_by_id(session, current_user_id)
    if not current_user:
        raise ValueError("Current user not found.")

    existing_telegram_user = await user_dal.get_user_by_telegram_id(session, telegram_id)
    if existing_telegram_user and existing_telegram_user.user_id != current_user.user_id:
        raise UserMergeConflictError(
            "Telegram identity belongs to another account; explicit merge is required.",
            message_key="account_merge_telegram_conflict",
            code="account_merge_telegram_conflict",
        )

    if current_user.telegram_id and int(current_user.telegram_id) != telegram_id:
        raise UserMergeConflictError(
            "Current account is already linked to Telegram.",
            message_key="account_merge_telegram_conflict",
            code="account_merge_telegram_conflict",
        )

    _apply_telegram_profile_to_user(current_user, telegram_user, settings)
    await session.flush()
    await _sync_panel_identity_for_user(request, current_user)
    return current_user
