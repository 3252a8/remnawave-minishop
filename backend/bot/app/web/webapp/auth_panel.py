from bot.app.web.context import (
    get_optional_subscription_service,
)

from ._runtime import (
    Any,
    AsyncSession,
    Dict,
    Optional,
    Settings,
    SubscriptionService,
    User,
    UserMergeConflictError,
    datetime,
    logger,
    sanitize_display_name,
    sanitize_username,
    subscription_dal,
    timezone,
    user_dal,
    web,
)
from .auth_common import (
    _telegram_photo_url_value,
)
from .common import (
    _format_webapp_datetime,
    _normalize_language,
    _telegram_id_for_user,
)


async def _sync_panel_identity_for_user(
    request: web.Request,
    user: User,
    *,
    expire_at: Optional[datetime] = None,
) -> bool:
    if not user.panel_user_uuid:
        return False
    subscription_service: SubscriptionService = get_optional_subscription_service(request)
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

    subscription_service: SubscriptionService = get_optional_subscription_service(request)
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


def _apply_telegram_profile_to_user(
    user: User,
    telegram_user: Dict[str, Any],
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
    telegram_user: Dict[str, Any],
    settings: Settings,
    merge_reason: str = "telegram_link",
    merge_send_user_email: bool = False,
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
            reason=merge_reason,
            send_user_email=merge_send_user_email,
        )
        _apply_telegram_profile_to_user(merged_user, telegram_user, settings)
        await session.flush()
        return merged_user

    if not existing_telegram_user and int(current_user.user_id) < 0:
        language_code = _normalize_language(
            current_user.language_code
            or telegram_user.get("language_code")
            or settings.DEFAULT_LANGUAGE
        )
        # Technical intermediate row for the link+merge below — the person is
        # an existing user, so this must not look like a new registration.
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
            registered_via=None,
        )
        target_user.referral_code = None
        await session.flush()
        merged_user = await user_dal.merge_users(
            session,
            source_user_id=current_user.user_id,
            target_user_id=target_user.user_id,
            reason=merge_reason,
            send_user_email=merge_send_user_email,
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
