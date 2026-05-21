# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

import hashlib
from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.app.web.webapp.cache_helpers import invalidate_webapp_user_caches
from bot.infra.redis import cache_delete_pattern, redis_key
from bot.utils.ttl_cache import AsyncTTLCache

_ADMIN_USERS_LIST_CACHES: Dict[tuple[int, int], AsyncTTLCache] = {}


async def admin_users_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]

    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    query = (request.query.get("q") or "").strip()
    filter_value = (request.query.get("filter") or "all").lower()
    panel_status = (request.query.get("panel_status") or "all").lower()
    premium_traffic = (request.query.get("premium_traffic") or "all").lower()
    sort_value = (request.query.get("sort") or "registered_desc").lower()

    payload = await _load_admin_users_list_payload(
        settings,
        async_session_factory,
        page=page,
        page_size=page_size,
        query=query,
        filter_value=filter_value,
        panel_status=panel_status,
        premium_traffic=premium_traffic,
        sort_value=sort_value,
    )
    return _ok(payload)


async def _load_admin_users_list_payload(
    settings: Settings,
    async_session_factory: sessionmaker,
    *,
    page: int,
    page_size: int,
    query: str,
    filter_value: str,
    panel_status: str,
    premium_traffic: str,
    sort_value: str,
) -> Dict[str, Any]:
    cache = _admin_users_list_cache(settings)
    cache_key = _admin_users_list_cache_key(
        page=page,
        page_size=page_size,
        query=query,
        filter_value=filter_value,
        panel_status=panel_status,
        premium_traffic=premium_traffic,
        sort_value=sort_value,
    )
    if cache is None:
        return await _load_admin_users_list_payload_uncached(
            async_session_factory,
            page=page,
            page_size=page_size,
            query=query,
            filter_value=filter_value,
            panel_status=panel_status,
            premium_traffic=premium_traffic,
            sort_value=sort_value,
        )
    return await cache.get_or_load(
        cache_key,
        lambda: _load_admin_users_list_payload_uncached(
            async_session_factory,
            page=page,
            page_size=page_size,
            query=query,
            filter_value=filter_value,
            panel_status=panel_status,
            premium_traffic=premium_traffic,
            sort_value=sort_value,
        ),
    )


async def _load_admin_users_list_payload_uncached(
    async_session_factory: sessionmaker,
    *,
    page: int,
    page_size: int,
    query: str,
    filter_value: str,
    panel_status: str,
    premium_traffic: str,
    sort_value: str,
) -> Dict[str, Any]:
    async with async_session_factory() as session:
        users, total = await _filter_and_sort_users(
            session,
            query=query,
            filter_value=filter_value,
            panel_status=panel_status,
            premium_traffic=premium_traffic,
            sort_value=sort_value,
            page=page,
            page_size=page_size,
        )

        statuses = await _bulk_user_statuses(session, [u.user_id for u in users])
        cached_avatar_ids = await _bulk_user_avatar_keys(session, [u.user_id for u in users])
        active_subs = await _bulk_active_subscriptions_for_users(
            session, [u.user_id for u in users]
        )

    serialized = []
    for user in users:
        payload = _serialize_user(user)
        status_payload = statuses.get(user.user_id) or {"status": "bot_only", "end_date": None}
        payload["panel_status"] = status_payload.get("status")
        if status_payload.get("status") == "expired" and status_payload.get("end_date"):
            payload["panel_status_expired_at"] = status_payload["end_date"]
        payload["avatar_url"] = (
            f"/api/admin/users/{user.user_id}/avatar?v={cached_avatar_ids[user.user_id]}"
            if user.user_id in cached_avatar_ids
            else None
        )
        payload["premium_traffic"] = _premium_traffic_list_payload(active_subs.get(user.user_id))
        serialized.append(payload)

    return {
        "users": serialized,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def _admin_users_list_cache(settings: Settings) -> Optional[AsyncTTLCache]:
    ttl_seconds = int(getattr(settings, "ADMIN_USERS_LIST_CACHE_TTL_SECONDS", 3) or 0)
    if ttl_seconds <= 0:
        return None
    cache_key = (id(settings), ttl_seconds)
    cache = _ADMIN_USERS_LIST_CACHES.get(cache_key)
    if cache is None:
        cache = AsyncTTLCache(
            ttl_seconds=ttl_seconds,
            settings=settings,
            namespace="admin:users_list",
        )
        _ADMIN_USERS_LIST_CACHES[cache_key] = cache
    return cache


def _admin_users_list_cache_key(**params: Any) -> str:
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _invalidate_admin_users_list_cache(settings: Settings) -> None:
    for settings_id, _ttl in tuple(_ADMIN_USERS_LIST_CACHES):
        if settings_id == id(settings):
            _ADMIN_USERS_LIST_CACHES[(settings_id, _ttl)].invalidate()
    try:
        await cache_delete_pattern(settings, redis_key(settings, "cache", "admin:users_list", "*"))
    except Exception:
        return


async def _invalidate_after_admin_user_mutation(
    settings: Settings,
    user_id: Optional[int] = None,
    *,
    include_devices: bool = True,
) -> None:
    await _invalidate_admin_users_list_cache(settings)
    if user_id is not None:
        await invalidate_webapp_user_caches(
            settings,
            user_id,
            include_devices=include_devices,
        )


async def _bulk_user_statuses(
    session: AsyncSession, user_ids: List[int]
) -> Dict[int, Dict[str, Optional[str]]]:
    """Return active subscription status for a batch of users.

    Returns the panel status (active/expired/limited/disabled) when an active
    subscription exists, otherwise ``"bot_only"`` when the user is in the bot
    but has no panel subscription.
    """

    if not user_ids:
        return {}
    stmt = (
        select(
            Subscription.user_id,
            Subscription.status_from_panel,
            Subscription.is_active,
            Subscription.end_date,
        )
        .where(Subscription.user_id.in_(user_ids))
        .order_by(Subscription.is_active.desc(), Subscription.end_date.desc().nullslast())
    )
    rows = (await session.execute(stmt)).all()
    out: Dict[int, Dict[str, Optional[str]]] = {}
    for uid, panel_status, is_active, end_date in rows:
        if uid in out:
            continue
        if is_active:
            status = (panel_status or "active").lower()
        else:
            status = (panel_status or "expired").lower()
        out[uid] = {
            "status": status,
            "end_date": end_date.isoformat() if end_date else None,
        }
    for uid in user_ids:
        if uid not in out:
            out[uid] = {"status": "bot_only", "end_date": None}
    return out


async def _bulk_user_avatar_keys(session: AsyncSession, user_ids: List[int]) -> Dict[int, str]:
    """Return ``{user_id: cache_key}`` for users with a cached Telegram avatar.

    The cache key is the row's ``updated_at`` timestamp — used as a
    cache-buster query param so the browser refetches when the avatar
    changes.
    """

    if not user_ids:
        return {}
    stmt = select(UserTelegramAvatar.user_id, UserTelegramAvatar.updated_at).where(
        UserTelegramAvatar.user_id.in_(user_ids)
    )
    rows = (await session.execute(stmt)).all()
    return {int(uid): (updated_at.isoformat() if updated_at else "") for uid, updated_at in rows}


async def admin_user_avatar_route(request: web.Request) -> web.Response:
    """Serve the cached Telegram avatar for any user (admin-only).

    Mirrors ``/api/account/avatar`` but takes a ``user_id`` from the URL
    and uses admin auth. Only the cached blob from
    ``user_telegram_avatars`` is served — refreshing from Telegram is the
    job of the user-facing endpoint, so the admin list never blocks on a
    Telegram round-trip.
    """

    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        avatar = await session.get(UserTelegramAvatar, target_id)

    if not avatar:
        raise web.HTTPNotFound(text="avatar_not_cached")

    etag = (
        f'W/"avatar-{target_id}-{int(avatar.updated_at.timestamp())}"'
        if avatar.updated_at
        else None
    )
    if etag and request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers={"ETag": etag})

    response = web.Response(
        body=bytes(avatar.image_bytes),
        content_type=avatar.content_type or "image/jpeg",
    )
    response.headers["Cache-Control"] = "private, max-age=3600"
    if etag:
        response.headers["ETag"] = etag
    return response


def _ranked_active_subscriptions_sq(now: datetime):
    """Latest active subscription per user (same ordering as subscription_dal)."""

    rn = sa_func.row_number().over(
        partition_by=Subscription.user_id,
        order_by=(
            Subscription.end_date.desc(),
            Subscription.subscription_id.desc(),
        ),
    )
    inner = (
        select(
            Subscription.user_id,
            Subscription.subscription_id,
            Subscription.premium_used_bytes,
            Subscription.premium_baseline_bytes,
            Subscription.premium_topup_balance_bytes,
            Subscription.premium_topup_used_bytes,
            Subscription.premium_bonus_bytes,
            Subscription.premium_unlimited_override,
            rn.label("rn"),
        )
        .where(
            Subscription.is_active.is_(True),
            Subscription.end_date > now,
        )
        .subquery()
    )
    return select(inner).where(inner.c.rn == 1).subquery(name="ranked_active_sub")


async def _bulk_active_subscriptions_for_users(
    session: AsyncSession, user_ids: List[int]
) -> Dict[int, Subscription]:
    """Active subscription row per user (for admin list premium traffic column)."""

    if not user_ids:
        return {}
    now = datetime.now(timezone.utc)
    stmt = (
        select(Subscription)
        .where(
            Subscription.user_id.in_(user_ids),
            Subscription.is_active.is_(True),
            Subscription.end_date > now,
        )
        .order_by(
            Subscription.user_id.asc(),
            Subscription.end_date.desc(),
            Subscription.subscription_id.desc(),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: Dict[int, Subscription] = {}
    for sub in rows:
        uid = int(sub.user_id)
        if uid not in out:
            out[uid] = sub
    return out


async def _filter_and_sort_users(
    session: AsyncSession,
    *,
    query: str = "",
    filter_value: str,
    panel_status: str = "all",
    premium_traffic: str = "all",
    sort_value: str,
    page: int,
    page_size: int,
) -> tuple[List[User], int]:
    """Return paginated users with optional search, filter and sort applied."""

    now = datetime.now(timezone.utc)
    sort_key = (sort_value or "registered_desc").lower()
    pt_filter = (premium_traffic or "all").lower()
    needs_premium_sq = pt_filter != "all" or sort_key in {
        "premium_ratio_asc",
        "premium_ratio_desc",
    }

    stmt = select(User)
    count_stmt = select(sa_func.count(User.user_id))

    sq = None
    ratio_expr = None
    plim_expr = None
    pu_expr = None

    if needs_premium_sq:
        sq = _ranked_active_subscriptions_sq(now)
        stmt = stmt.outerjoin(sq, User.user_id == sq.c.user_id)
        count_stmt = count_stmt.outerjoin(sq, User.user_id == sq.c.user_id)
        pb = sa_func.coalesce(sq.c.premium_bonus_bytes, 0)
        plim_expr = (
            sa_func.coalesce(sq.c.premium_baseline_bytes, 0)
            + sa_func.coalesce(sq.c.premium_topup_balance_bytes, 0)
            + sa_func.coalesce(sq.c.premium_topup_used_bytes, 0)
            + pb
        )
        pu_expr = sa_func.coalesce(sq.c.premium_used_bytes, 0)
        ratio_expr = case(
            (sq.c.user_id.is_(None), None),
            (sq.c.premium_unlimited_override.is_(True), None),
            (plim_expr <= 0, None),
            else_=cast(pu_expr, Float) / cast(plim_expr, Float),
        )

    search_cond = _user_search_condition(query)
    if search_cond is not None:
        stmt = stmt.where(search_cond)
        count_stmt = count_stmt.where(search_cond)

    f = (filter_value or "all").lower()
    if f == "banned":
        cond = User.is_banned.is_(True)
    elif f == "active":
        cond = User.is_banned.is_(False)
    elif f == "tg_linked":
        cond = User.telegram_id.is_not(None)
    elif f == "no_tg":
        cond = User.telegram_id.is_(None)
    elif f == "email_linked":
        cond = User.email.is_not(None)
    elif f == "no_email":
        cond = User.email.is_(None)
    elif f == "panel_linked":
        cond = User.panel_user_uuid.is_not(None)
    else:
        cond = None

    if cond is not None:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    panel_cond = _user_panel_status_condition(panel_status)
    if panel_cond is not None:
        stmt = stmt.where(panel_cond)
        count_stmt = count_stmt.where(panel_cond)

    if needs_premium_sq and sq is not None and plim_expr is not None and pu_expr is not None:
        if pt_filter == "none":
            premium_cond = or_(
                sq.c.user_id.is_(None),
                and_(
                    sq.c.premium_unlimited_override.is_(False),
                    plim_expr <= 0,
                ),
            )
            stmt = stmt.where(premium_cond)
            count_stmt = count_stmt.where(premium_cond)
        elif pt_filter == "unlimited":
            premium_cond = and_(
                sq.c.user_id.isnot(None),
                sq.c.premium_unlimited_override.is_(True),
            )
            stmt = stmt.where(premium_cond)
            count_stmt = count_stmt.where(premium_cond)
        elif pt_filter == "good":
            premium_cond = and_(
                sq.c.user_id.isnot(None),
                sq.c.premium_unlimited_override.is_(False),
                plim_expr > 0,
                (100 * pu_expr) < (85 * plim_expr),
            )
            stmt = stmt.where(premium_cond)
            count_stmt = count_stmt.where(premium_cond)
        elif pt_filter == "warn":
            premium_cond = and_(
                sq.c.user_id.isnot(None),
                sq.c.premium_unlimited_override.is_(False),
                plim_expr > 0,
                (100 * pu_expr) >= (85 * plim_expr),
                pu_expr < plim_expr,
            )
            stmt = stmt.where(premium_cond)
            count_stmt = count_stmt.where(premium_cond)
        elif pt_filter == "critical":
            premium_cond = and_(
                sq.c.user_id.isnot(None),
                sq.c.premium_unlimited_override.is_(False),
                plim_expr > 0,
                pu_expr >= plim_expr,
            )
            stmt = stmt.where(premium_cond)
            count_stmt = count_stmt.where(premium_cond)

    sort_map = {
        "registered_desc": User.registration_date.desc().nullslast(),
        "registered_asc": User.registration_date.asc().nullslast(),
        "name_asc": (
            sa_func.coalesce(User.first_name, User.username, User.email).asc(),
            User.user_id.asc(),
        ),
        "name_desc": (
            sa_func.coalesce(User.first_name, User.username, User.email).desc(),
            User.user_id.desc(),
        ),
        "id_asc": User.user_id.asc(),
        "id_desc": User.user_id.desc(),
    }

    if needs_premium_sq and ratio_expr is not None and sort_key == "premium_ratio_asc":
        stmt = stmt.order_by(ratio_expr.asc().nullslast(), User.user_id.asc())
    elif needs_premium_sq and ratio_expr is not None and sort_key == "premium_ratio_desc":
        stmt = stmt.order_by(ratio_expr.desc().nullslast(), User.user_id.desc())
    else:
        order = sort_map.get(sort_key, sort_map["registered_desc"])
        if isinstance(order, tuple):
            stmt = stmt.order_by(*order)
        else:
            stmt = stmt.order_by(order)

    stmt = stmt.offset(max(page, 0) * max(page_size, 1)).limit(max(page_size, 1))

    users = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return users, int(total)


def _user_panel_status_condition(panel_status: str):
    status = (panel_status or "all").lower()
    if status not in {"active", "expired", "limited"}:
        return None

    normalized_status = sa_func.lower(sa_func.coalesce(Subscription.status_from_panel, ""))
    blank_status = or_(
        Subscription.status_from_panel.is_(None), Subscription.status_from_panel == ""
    )
    if status == "active":
        status_cond = or_(
            normalized_status == "active", blank_status & Subscription.is_active.is_(True)
        )
    elif status == "expired":
        status_cond = or_(
            normalized_status == "expired", blank_status & Subscription.is_active.is_(False)
        )
    else:
        status_cond = normalized_status == "limited"

    return (
        select(Subscription.subscription_id)
        .where(Subscription.user_id == User.user_id, status_cond)
        .exists()
    )


def _user_search_condition(query: str):
    raw = (query or "").strip().lstrip("@")
    if not raw:
        return None

    like = f"%{raw}%"
    conditions = [
        User.username.ilike(like),
        User.first_name.ilike(like),
        User.last_name.ilike(like),
        User.email.ilike(like),
    ]
    if raw.isdigit():
        numeric = int(raw)
        conditions.extend([User.user_id == numeric, User.telegram_id == numeric])

    return or_(*conditions)


async def admin_user_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    settings: Settings = request.app["settings"]

    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found", "User not found")

        active_sub = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        latest_subs_stmt = (
            select(Subscription)
            .where(Subscription.user_id == target_id)
            .order_by(Subscription.start_date.desc().nullslast())
            .limit(20)
        )
        latest_subs = (await session.execute(latest_subs_stmt)).scalars().all()
        total_paid = await payment_dal.get_user_total_paid(session, target_id)
        recent_payments_stmt = (
            select(Payment)
            .where(Payment.user_id == target_id)
            .order_by(Payment.created_at.desc())
            .limit(20)
        )
        recent_payments = (await session.execute(recent_payments_stmt)).scalars().all()
        log_count = await message_log_dal.count_user_message_logs(session, target_id)
        avatar_keys = await _bulk_user_avatar_keys(session, [target_id])

        # Referral links — both the bot deep-link and the webapp deep-link.
        referral_code: Optional[str] = None
        try:
            referral_code = await user_dal.ensure_referral_code(session, user)
            await session.commit()
        except Exception as exc_ref:  # pragma: no cover — defensive
            logger.warning("Failed to ensure referral code for user %s: %s", target_id, exc_ref)
            await session.rollback()

    referral_service: Optional[ReferralService] = request.app.get("referral_service")
    bot_username = request.app.get("bot_username") or ""
    referral_bot_link: Optional[str] = None
    if referral_service and bot_username and referral_code:
        try:
            async with async_session_factory() as session:
                referral_bot_link = await referral_service.generate_referral_link(
                    session, bot_username, target_id
                )
        except Exception as exc_link:  # pragma: no cover
            logger.warning("Failed to build bot referral link for %s: %s", target_id, exc_link)
    referral_webapp_link = _build_admin_webapp_referral_link(
        getattr(settings, "SUBSCRIPTION_MINI_APP_URL", None),
        referral_code,
    )

    # Subscription page URL — the raw panel `subscriptionUrl` that the user
    # imports into their VPN client. May be missing if the user has never
    # been provisioned on the panel.
    subscription_url: Optional[str] = None
    panel_uuid = getattr(user, "panel_user_uuid", None)
    if panel_uuid:
        subscription_service = request.app.get("subscription_service")
        panel_service = getattr(subscription_service, "panel_service", None)
        if panel_service is not None:
            try:
                panel_data = await panel_service.get_user_by_uuid(panel_uuid)
                if panel_data:
                    subscription_url = panel_data.get("subscriptionUrl") or None
            except Exception as exc_panel:  # pragma: no cover
                logger.warning(
                    "Failed to fetch subscriptionUrl for user %s (uuid=%s): %s",
                    target_id,
                    panel_uuid,
                    exc_panel,
                )

    serialized_user = _serialize_user(user)
    serialized_user["avatar_url"] = (
        f"/api/admin/users/{target_id}/avatar?v={avatar_keys[target_id]}"
        if target_id in avatar_keys
        else None
    )

    return _ok(
        {
            "user": serialized_user,
            "active_subscription": _serialize_subscription(active_sub) if active_sub else None,
            "subscriptions": [_serialize_subscription(s) for s in (latest_subs or [])],
            "total_paid": float(total_paid),
            "recent_payments": [_serialize_payment(p) for p in recent_payments],
            "log_count": int(log_count or 0),
            "subscription_url": subscription_url,
            "referral": {
                "code": referral_code,
                "bot_link": referral_bot_link,
                "webapp_link": referral_webapp_link,
            },
        }
    )


async def admin_user_ban_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    payload = await _read_json(request)
    desired = bool(payload.get("banned"))

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
    payload = await _read_json(request)
    text = str(payload.get("text") or "").strip()
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
    payload = await _read_json(request)
    text = str(payload.get("text") or "").strip()
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
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        ok = await user_dal.delete_user_and_relations(session, target_id)
        if not ok:
            await session.rollback()
            return _error(404, "not_found")
        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_delete_user_webapp",
                "content": f"Deleted user_id={target_id}",
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
    panel_service = request.app.get("panel_service")
    subscription_service = request.app.get("subscription_service")
    if panel_service is None or subscription_service is None:
        return _error(503, "service_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")

        active = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        if active:
            await session.delete(active)

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_reset_trial_webapp",
                "content": f"Reset trial for user_id={target_id}",
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
    payload = await _read_json(request)
    subscription_service = request.app.get("subscription_service")

    unlimited = bool(payload.get("unlimited"))
    bonus_bytes_raw = payload.get("bonus_bytes")
    bonus_gb_raw = payload.get("bonus_gb")
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
    """Main (regular) traffic: unlimited-style ceiling + admin bonus GB."""
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)

    unlimited = bool(payload.get("unlimited"))
    regular_bonus_bytes_raw = payload.get("regular_bonus_bytes")
    regular_bonus_gb_raw = payload.get("regular_bonus_gb")
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
    payload = await _read_json(request)

    kind = str(payload.get("kind") or "regular").strip().lower()
    if kind not in {"regular", "premium"}:
        return _error(400, "invalid_kind", "kind must be 'regular' or 'premium'")

    bytes_raw = payload.get("bytes")
    gb_raw = payload.get("gb")
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
    payload = await _read_json(request)
    try:
        days = int(payload.get("days") or 0)
    except (TypeError, ValueError):
        return _error(400, "invalid_days")
    if days <= 0:
        return _error(400, "invalid_days")

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
        )
        if not new_end:
            await session.rollback()
            return _error(500, "extend_failed")

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_extend_subscription_webapp",
                "content": f"+{days}d -> {new_end.isoformat()}",
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
