from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ._runtime import (
    AdminUserBanBody,
    AdminUserExtendBody,
    AdminUserHwidDeviceLimitBody,
    AdminUserMessageBody,
    AdminUserPremiumOverrideBody,
    AdminUserRegularTrafficOverrideBody,
    AdminUserTariffBody,
    AdminUserTrafficGrantBody,
    MessageContent,
    Optional,
    Settings,
    User,
    get_queue_manager,
    logger,
    message_log_dal,
    parse_body_or_400,
    send_message_via_queue,
    sessionmaker,
    subscription_dal,
    user_dal,
    web,
)
from .auth import _require_admin_user_id
from .common import (
    _error,
    _ok,
    _serialize_subscription,
    _serialize_user,
)
from .users_listing import (
    _invalidate_after_admin_user_mutation,
    _resolve_admin_period_tariff_key,
)


async def admin_user_ban_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserBanBody)
    desired = bool(body.banned)

    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")
        user.is_banned = bool(desired)
        await session.commit()
        await session.refresh(user)
    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({"user": _serialize_user(user)})


async def admin_user_message_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserMessageBody)
    text = str(body.text or "").strip()
    if not text:
        return _error(400, "empty_text")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        target_user = await user_dal.get_user_by_id(session, target_id)
        if not target_user or not target_user.telegram_id:
            return _error(404, "no_telegram_account")

        try:
            await send_message_via_queue(
                queue_manager,
                int(target_user.telegram_id),
                MessageContent(content_type="text", text=text),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.warning("Admin direct message failed: %s", exc)
            return _error(502, "send_failed", str(exc))

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_direct_message_webapp",
                "content": text[:4000],
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )

    return _ok({})


async def admin_user_message_preview_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    admin_telegram_id = request.get("admin_telegram_id")
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserMessageBody)
    text = str(body.text or "").strip()
    if not text:
        return _error(400, "empty_text")
    if not admin_telegram_id:
        return _error(403, "admin_telegram_unavailable")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    try:
        await send_message_via_queue(
            queue_manager,
            int(admin_telegram_id),
            MessageContent(content_type="text", text=text),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning("Admin direct message preview failed: %s", exc)
        return _error(502, "preview_failed", str(exc))

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_direct_message_preview_webapp",
                "content": text[:4000],
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )

    return _ok({})


def _admin_user_display_name_for_message(user: User) -> str:
    full = " ".join(
        part
        for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
        if part
    ).strip()
    return (
        full
        or (f"@{user.username}" if getattr(user, "username", None) else None)
        or getattr(user, "email", None)
        or f"User #{user.user_id}"
    )


async def admin_user_telegram_profile_link_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    admin_telegram_id = request.get("admin_telegram_id")
    if not admin_telegram_id:
        return _error(403, "admin_telegram_unavailable")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    async with async_session_factory() as session:
        target_user = await user_dal.get_user_by_id(session, target_id)
        if not target_user:
            return _error(404, "not_found")
        if not target_user.telegram_id:
            return _error(404, "no_telegram_account")

        admin_user = await user_dal.get_user_by_id(session, actor_id)
        lang = (
            getattr(admin_user, "language_code", None)
            or getattr(settings, "DEFAULT_LANGUAGE", None)
            or "ru"
        )

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_profile_link_webapp",
                "content": f"Requested Telegram profile link for user_id={target_id}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()

    i18n_instance = request.app.get("i18n")
    translate = (
        (lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs))
        if i18n_instance is not None
        else (lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    )
    target_name = _admin_user_display_name_for_message(target_user)
    telegram_id = int(target_user.telegram_id)
    profile_url = f"tg://user?id={telegram_id}"
    message_text = translate(
        "admin_user_profile_link_message",
        name=html_escape(target_name),
        user_id=target_user.user_id,
        telegram_id=telegram_id,
    )
    if message_text == "admin_user_profile_link_message":
        message_text = (
            f"Профиль пользователя: <b>{html_escape(target_name)}</b>\n"
            f"User ID: <code>{target_user.user_id}</code>\n"
            f"Telegram ID: <code>{telegram_id}</code>\n\n"
            "Нажмите кнопку ниже, чтобы открыть профиль в Telegram."
        )

    button_text = translate("user_card_open_profile_button")
    if button_text == "user_card_open_profile_button":
        button_text = "👤 Открыть профиль"

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=button_text, url=profile_url)]]
    )

    try:
        await send_message_via_queue(
            queue_manager,
            int(admin_telegram_id),
            MessageContent(content_type="text", text=message_text),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=markup,
        )
    except Exception as exc:
        logger.warning("Admin profile link message enqueue failed: %s", exc)
        return _error(502, "send_failed", str(exc))

    return _ok({"queued": True})


async def admin_user_delete_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])

    settings: Settings = request.app["settings"]
    panel_service = request.app.get("panel_service")
    if panel_service is None:
        subscription_service = request.app.get("subscription_service")
        panel_service = getattr(subscription_service, "panel_service", None)
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")

        panel_user_uuids = await user_dal.get_panel_user_uuids_for_user(
            session,
            target_id,
            user=user,
        )
        if panel_user_uuids and panel_service is None:
            await session.rollback()
            return _error(503, "panel_service_unavailable")

        for panel_uuid in panel_user_uuids:
            try:
                panel_deleted = await panel_service.delete_user_from_panel(
                    panel_uuid,
                    log_response=False,
                )
            except Exception as exc:
                logger.warning(
                    "Admin webapp failed to delete panel user %s for user %s: %s",
                    panel_uuid,
                    target_id,
                    exc,
                )
                await session.rollback()
                return _error(502, "panel_delete_failed", str(exc))

            if not panel_deleted:
                await session.rollback()
                return _error(
                    502,
                    "panel_delete_failed",
                    f"Failed to delete panel user {panel_uuid}",
                )

        ok = await user_dal.delete_user_and_relations(session, target_id)
        if not ok:
            await session.rollback()
            return _error(404, "not_found")
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": actor_id if actor_id != target_id else None,
                "event_type": "admin_delete_user_webapp",
                "content": (
                    f"Deleted user_id={target_id}; "
                    f"panel_uuids={','.join(panel_user_uuids) or 'none'}"
                ),
                "is_admin_event": True,
            },
        )
        await session.commit()
    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({})


async def admin_user_reset_trial_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")

        reset_at = await user_dal.mark_trial_eligibility_reset(session, target_id)
        if reset_at is None:
            await session.rollback()
            return _error(404, "not_found")

        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_reset_trial_webapp",
                "content": f"Reset trial eligibility for user_id={target_id}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({})


async def admin_user_premium_override_route(request: web.Request) -> web.Response:
    """Premium-squad traffic overrides only (unlimited toggle + bonus GB)."""
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    body = await parse_body_or_400(request, AdminUserPremiumOverrideBody)
    subscription_service = request.app.get("subscription_service")

    unlimited = bool(body.unlimited)
    bonus_bytes_raw = body.bonus_bytes
    bonus_gb_raw = body.bonus_gb
    if bonus_bytes_raw is None and bonus_gb_raw is None:
        bonus_bytes = 0
    elif bonus_bytes_raw is not None:
        try:
            bonus_bytes = int(bonus_bytes_raw)
        except (TypeError, ValueError):
            return _error(400, "invalid_bonus", "bonus_bytes must be an integer")
    else:
        try:
            bonus_bytes = int(round(float(bonus_gb_raw) * (1024**3)))
        except (TypeError, ValueError):
            return _error(400, "invalid_bonus", "bonus_gb must be a number")

    if bonus_bytes < 0:
        return _error(400, "invalid_bonus", "bonus must be non-negative")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if not active:
            return _error(404, "no_active_subscription")

        active.premium_unlimited_override = bool(unlimited)
        active.premium_bonus_bytes = int(bonus_bytes)
        if active.premium_unlimited_override:
            active.premium_is_limited = False

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_premium_override_webapp",
                "content": (f"unlimited={bool(unlimited)} bonus_bytes={int(bonus_bytes)}"),
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
        await session.refresh(active)

        if subscription_service is not None:
            await subscription_service.sync_premium_squad_access_to_panel(session, target_id)
            await session.commit()
            await session.refresh(active)

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({"subscription": _serialize_subscription(active)})


async def admin_user_regular_traffic_override_route(request: web.Request) -> web.Response:
    """Main (regular) traffic: native unlimited panel limit + admin bonus GB."""
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    body = await parse_body_or_400(request, AdminUserRegularTrafficOverrideBody)

    unlimited = bool(body.unlimited)
    regular_bonus_bytes_raw = body.regular_bonus_bytes
    regular_bonus_gb_raw = body.regular_bonus_gb
    if regular_bonus_bytes_raw is None and regular_bonus_gb_raw is None:
        regular_bonus_bytes = 0
    elif regular_bonus_bytes_raw is not None:
        try:
            regular_bonus_bytes = int(regular_bonus_bytes_raw)
        except (TypeError, ValueError):
            return _error(400, "invalid_regular_bonus", "regular_bonus_bytes must be an integer")
    else:
        try:
            regular_bonus_bytes = int(round(float(regular_bonus_gb_raw) * (1024**3)))
        except (TypeError, ValueError):
            return _error(400, "invalid_regular_bonus", "regular_bonus_gb must be a number")

    if regular_bonus_bytes < 0:
        return _error(400, "invalid_regular_bonus", "regular bonus must be non-negative")

    subscription_service = request.app.get("subscription_service")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if not active:
            return _error(404, "no_active_subscription")

        active.regular_unlimited_override = bool(unlimited)
        active.regular_bonus_bytes = int(regular_bonus_bytes)

        if subscription_service is not None:
            await subscription_service.sync_main_traffic_limit_to_panel(session, target_id)

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_regular_traffic_override_webapp",
                "content": (
                    f"unlimited={bool(unlimited)} regular_bonus_bytes={int(regular_bonus_bytes)}"
                ),
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
        await session.refresh(active)

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({"subscription": _serialize_subscription(active)})


async def admin_user_hwid_device_limit_route(request: web.Request) -> web.Response:
    """Override the user's base HWID device limit.

    ``hwid_device_limit == 0`` means unlimited; ``NULL`` means the tariff/.env
    default is used. Purchased extra devices remain tracked separately and are
    added when syncing the effective panel limit.
    """
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    body = await parse_body_or_400(request, AdminUserHwidDeviceLimitBody)

    unlimited = bool(body.unlimited)
    use_default = bool(body.use_default or body.reset_to_default)
    limit_raw = body.hwid_device_limit if body.hwid_device_limit is not None else body.limit

    if unlimited:
        hwid_device_limit: Optional[int] = 0
    elif use_default or limit_raw is None or limit_raw == "":
        hwid_device_limit = None
    else:
        try:
            hwid_device_limit = int(limit_raw)
        except (TypeError, ValueError):
            return _error(
                400,
                "invalid_hwid_device_limit",
                "hwid_device_limit must be a non-negative integer",
            )
        if hwid_device_limit < 0 or hwid_device_limit > 1_000_000:
            return _error(
                400,
                "invalid_hwid_device_limit",
                "hwid_device_limit must be an integer from 0 to 1000000",
            )

    subscription_service = request.app.get("subscription_service")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if not active:
            return _error(404, "no_active_subscription")

        active.hwid_device_limit = hwid_device_limit

        effective_limit = None
        if subscription_service is not None:
            effective_limit = await subscription_service.sync_hwid_device_limit_to_panel(
                session, target_id
            )

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_hwid_device_limit_webapp",
                "content": (
                    f"hwid_device_limit={hwid_device_limit!r} "
                    f"effective_hwid_device_limit={effective_limit!r}"
                ),
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()
        await session.refresh(active)

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({"subscription": _serialize_subscription(active)})


async def admin_user_traffic_grant_route(request: web.Request) -> web.Response:
    """Credit regular or premium traffic to a user without a payment.

    Body: ``{"kind": "regular" | "premium", "gb": float}`` (alternatively
    ``"bytes": int``). Mirrors the same effect as a user-purchased top-up:
    the chosen balance grows, panel limit/squads are refreshed, and an entry
    is added to ``traffic_topups`` with ``kind="admin_topup"`` or
    ``kind="admin_premium_topup"`` and ``payment_id=NULL``.
    """
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    body = await parse_body_or_400(request, AdminUserTrafficGrantBody)

    kind = str(body.kind or "regular").strip().lower()
    if kind not in {"regular", "premium"}:
        return _error(400, "invalid_kind", "kind must be 'regular' or 'premium'")

    bytes_raw = body.bytes
    gb_raw = body.gb
    if bytes_raw is None and gb_raw is None:
        return _error(400, "missing_amount", "either 'gb' or 'bytes' is required")
    try:
        if bytes_raw is not None:
            grant_bytes = int(bytes_raw)
            gb_value = grant_bytes / (1024**3)
        else:
            gb_value = float(gb_raw)
            grant_bytes = int(round(gb_value * (1024**3)))
    except (TypeError, ValueError):
        return _error(400, "invalid_amount", "amount must be a positive number")
    if gb_value <= 0 or grant_bytes <= 0:
        return _error(400, "invalid_amount", "amount must be positive")

    subscription_service = request.app.get("subscription_service")
    if subscription_service is None:
        return _error(503, "subscription_service_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if not active:
            return _error(404, "no_active_subscription")

        if kind == "regular":
            result = await subscription_service.admin_grant_topup(session, target_id, gb_value)
        else:
            result = await subscription_service.admin_grant_premium_topup(
                session, target_id, gb_value
            )
        if not result:
            await session.rollback()
            return _error(
                422,
                "grant_failed",
                "Unable to credit traffic (missing tariff/squads or panel error)",
            )

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_traffic_grant_webapp",
                "content": f"kind={kind} bytes={grant_bytes}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()

        refreshed = await subscription_dal.get_active_subscription_by_user_id(session, target_id)

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok(
        {
            "subscription": _serialize_subscription(refreshed) if refreshed else None,
            "grant": {
                "kind": kind,
                "granted_bytes": grant_bytes,
                "granted_gb": gb_value,
            },
        }
    )


async def admin_user_extend_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    body = await parse_body_or_400(request, AdminUserExtendBody)
    try:
        days = int(body.days or 0)
    except (TypeError, ValueError):
        return _error(400, "invalid_days")
    if days <= 0:
        return _error(400, "invalid_days")
    extend_hwid_devices = body.extend_hwid_devices
    extend_hwid_devices = True if extend_hwid_devices is None else bool(extend_hwid_devices)
    tariff_key, tariff_error = _resolve_admin_period_tariff_key(
        settings,
        body.tariff_key,
        allow_legacy_without_tariffs=True,
    )
    if tariff_error:
        return _error(400, tariff_error)

    subscription_service = request.app.get("subscription_service")
    if subscription_service is None:
        return _error(503, "subscription_service_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        new_end = await subscription_service.extend_active_subscription_days(
            session,
            target_id,
            days,
            "admin_extend_subscription_webapp",
            extend_hwid_devices=extend_hwid_devices,
            **({"tariff_key": tariff_key} if tariff_key else {}),
        )
        if not new_end:
            await session.rollback()
            return _error(500, "extend_failed")

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_extend_subscription_webapp",
                "content": (
                    f"+{days}d -> {new_end.isoformat()} "
                    f"(hwid={'yes' if extend_hwid_devices else 'no'} "
                    f"tariff={tariff_key or 'legacy'})"
                ),
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()

        refreshed = await subscription_dal.get_active_subscription_by_user_id(session, target_id)

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok(
        {
            "subscription": _serialize_subscription(refreshed) if refreshed else None,
        }
    )


async def admin_user_tariff_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    body = await parse_body_or_400(request, AdminUserTariffBody)
    tariff_key, tariff_error = _resolve_admin_period_tariff_key(
        settings,
        body.tariff_key,
    )
    if tariff_error:
        return _error(400, tariff_error)
    if not tariff_key:
        return _error(400, "tariff_required")

    subscription_service = request.app.get("subscription_service")
    if subscription_service is None:
        return _error(503, "subscription_service_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if not active:
            return _error(404, "no_active_subscription")

        result = await subscription_service.switch_tariff_without_payment(
            session,
            target_id,
            tariff_key,
            "admin_assign",
        )
        if not result:
            await session.rollback()
            return _error(500, "tariff_change_failed")

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_change_tariff_webapp",
                "content": f"tariff={tariff_key}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()

        refreshed = await subscription_dal.get_active_subscription_by_user_id(session, target_id)

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok(
        {
            "subscription": _serialize_subscription(refreshed) if refreshed else None,
        }
    )
