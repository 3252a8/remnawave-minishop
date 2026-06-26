import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aiohttp import web
from sqlalchemy import Float, and_, case, cast, or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, sessionmaker
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from bot.app.web.context import (
    get_bot_username,
    get_optional_subscription_service,
    get_referral_service,
    get_session_factory,
    get_settings,
)
from bot.services.referral_service import ReferralService
from config.settings import Settings
from db.dal import message_log_dal, payment_dal, subscription_dal, user_dal
from db.models import Payment, Subscription, User, UserTelegramAvatar

from .auth import _require_admin_user_id
from .common import (
    _build_admin_webapp_referral_link,
    _error,
    _ok,
    _panel_user_connection_activity,
    _serialize_payment,
    _serialize_subscription,
)
from .schemas import AdminUserTrialOut
from .users_common import _bulk_user_avatar_keys, _serialize_admin_user_with_avatar

logger = logging.getLogger(__name__)


async def admin_user_avatar_route(request: web.Request) -> web.Response:
    """Serve the cached Telegram avatar for any user (admin-only).

    Mirrors ``/api/account/avatar`` but takes a ``user_id`` from the URL
    and uses admin auth. Only the cached blob from
    ``user_telegram_avatars`` is served вЂ” refreshing from Telegram is the
    job of the user-facing endpoint, so the admin list never blocks on a
    Telegram round-trip.
    """

    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    async_session_factory: sessionmaker = get_session_factory(request)
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


def _ranked_active_subscriptions_sq(now: datetime) -> Subquery:
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


def _user_payment_summary_sq() -> Subquery:
    return (
        select(
            Payment.user_id.label("user_id"),
            sa_func.coalesce(sa_func.sum(Payment.amount), 0.0).label("payments_total_amount"),
            sa_func.count(Payment.payment_id).label("payments_count"),
        )
        .where(Payment.status == "succeeded")
        .group_by(Payment.user_id)
        .subquery(name="user_payment_summary")
    )


def _user_referral_count_sq() -> Subquery:
    referred_user = aliased(User)
    return (
        select(
            referred_user.referred_by_id.label("user_id"),
            sa_func.count(referred_user.user_id).label("invited_users_count"),
        )
        .where(referred_user.referred_by_id.is_not(None))
        .group_by(referred_user.referred_by_id)
        .subquery(name="user_referral_count")
    )


def _user_subscription_expiry_sq() -> Subquery:
    return (
        select(
            Subscription.user_id.label("user_id"),
            sa_func.max(Subscription.end_date).label("subscription_expires_at"),
        )
        .group_by(Subscription.user_id)
        .subquery(name="user_subscription_expiry")
    )


async def _bulk_user_payment_summaries(
    session: AsyncSession,
    user_ids: List[int],
) -> Dict[int, Dict[str, Any]]:
    if not user_ids:
        return {}

    stmt = (
        select(
            Payment.user_id,
            sa_func.coalesce(sa_func.sum(Payment.amount), 0.0),
            sa_func.count(Payment.payment_id),
            sa_func.max(Payment.currency),
        )
        .where(Payment.user_id.in_(user_ids), Payment.status == "succeeded")
        .group_by(Payment.user_id)
    )
    rows = (await session.execute(stmt)).all()
    return {
        int(user_id): {
            "total_amount": float(total_amount or 0),
            "count": int(payments_count or 0),
            "currency": currency,
        }
        for user_id, total_amount, payments_count, currency in rows
    }


async def _bulk_user_referral_counts(
    session: AsyncSession,
    user_ids: List[int],
) -> Dict[int, int]:
    if not user_ids:
        return {}

    referred_user = aliased(User)
    stmt = (
        select(referred_user.referred_by_id, sa_func.count(referred_user.user_id))
        .where(referred_user.referred_by_id.in_(user_ids))
        .group_by(referred_user.referred_by_id)
    )
    rows = (await session.execute(stmt)).all()
    return {int(user_id): int(count or 0) for user_id, count in rows}


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
    payment_summary_sq = None
    payment_total_expr = None
    payment_count_expr = None
    referral_count_sq = None
    referral_count_expr = None
    subscription_expiry_sq = None
    subscription_expires_expr = None

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

    if sort_key in {
        "payments_total_asc",
        "payments_total_desc",
        "payments_count_asc",
        "payments_count_desc",
    }:
        payment_summary_sq = _user_payment_summary_sq()
        stmt = stmt.outerjoin(payment_summary_sq, User.user_id == payment_summary_sq.c.user_id)
        count_stmt = count_stmt.outerjoin(
            payment_summary_sq,
            User.user_id == payment_summary_sq.c.user_id,
        )
        payment_total_expr = sa_func.coalesce(payment_summary_sq.c.payments_total_amount, 0.0)
        payment_count_expr = sa_func.coalesce(payment_summary_sq.c.payments_count, 0)

    if sort_key in {"invited_users_count_asc", "invited_users_count_desc"}:
        referral_count_sq = _user_referral_count_sq()
        stmt = stmt.outerjoin(referral_count_sq, User.user_id == referral_count_sq.c.user_id)
        count_stmt = count_stmt.outerjoin(
            referral_count_sq,
            User.user_id == referral_count_sq.c.user_id,
        )
        referral_count_expr = sa_func.coalesce(referral_count_sq.c.invited_users_count, 0)

    if sort_key in {"subscription_expires_at_asc", "subscription_expires_at_desc"}:
        subscription_expiry_sq = _user_subscription_expiry_sq()
        stmt = stmt.outerjoin(
            subscription_expiry_sq,
            User.user_id == subscription_expiry_sq.c.user_id,
        )
        count_stmt = count_stmt.outerjoin(
            subscription_expiry_sq,
            User.user_id == subscription_expiry_sq.c.user_id,
        )
        subscription_expires_expr = subscription_expiry_sq.c.subscription_expires_at

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
    elif payment_total_expr is not None and sort_key == "payments_total_asc":
        stmt = stmt.order_by(payment_total_expr.asc(), User.user_id.asc())
    elif payment_total_expr is not None and sort_key == "payments_total_desc":
        stmt = stmt.order_by(payment_total_expr.desc(), User.user_id.desc())
    elif payment_count_expr is not None and sort_key == "payments_count_asc":
        stmt = stmt.order_by(payment_count_expr.asc(), User.user_id.asc())
    elif payment_count_expr is not None and sort_key == "payments_count_desc":
        stmt = stmt.order_by(payment_count_expr.desc(), User.user_id.desc())
    elif referral_count_expr is not None and sort_key == "invited_users_count_asc":
        stmt = stmt.order_by(referral_count_expr.asc(), User.user_id.asc())
    elif referral_count_expr is not None and sort_key == "invited_users_count_desc":
        stmt = stmt.order_by(referral_count_expr.desc(), User.user_id.desc())
    elif subscription_expires_expr is not None and sort_key == "subscription_expires_at_asc":
        stmt = stmt.order_by(subscription_expires_expr.asc().nullslast(), User.user_id.asc())
    elif subscription_expires_expr is not None and sort_key == "subscription_expires_at_desc":
        stmt = stmt.order_by(subscription_expires_expr.desc().nullslast(), User.user_id.desc())
    else:
        order = sort_map.get(sort_key, sort_map["registered_desc"])
        if isinstance(order, tuple):
            stmt = stmt.order_by(*order)
        else:
            stmt = stmt.order_by(order)

    stmt = stmt.offset(max(page, 0) * max(page_size, 1)).limit(max(page_size, 1))

    users = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return list(users), int(total)


def _user_panel_status_condition(panel_status: str) -> ColumnElement[bool] | None:
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
        now = datetime.now(timezone.utc)
        expired_subs = aliased(Subscription)
        active_subs = aliased(Subscription)
        expired_status = sa_func.lower(sa_func.coalesce(expired_subs.status_from_panel, ""))
        expired_blank_status = or_(
            expired_subs.status_from_panel.is_(None),
            expired_subs.status_from_panel == "",
        )
        expired_condition = or_(
            expired_status == "expired",
            expired_blank_status & expired_subs.is_active.is_(False),
            expired_subs.end_date <= now,
        )
        expired_exists = (
            select(expired_subs.subscription_id)
            .where(expired_subs.user_id == User.user_id, expired_condition)
            .exists()
        )
        active_exists = (
            select(active_subs.subscription_id)
            .where(
                active_subs.user_id == User.user_id,
                active_subs.is_active.is_(True),
                active_subs.end_date > now,
            )
            .exists()
        )
        return and_(expired_exists, ~active_exists)
    else:
        status_cond = normalized_status == "limited"

    return (
        select(Subscription.subscription_id)
        .where(Subscription.user_id == User.user_id, status_cond)
        .exists()
    )


def _user_search_condition(query: str) -> ColumnElement[bool] | None:
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


def _serialize_trial_summary(user: User, trial_subs: List[Subscription]) -> Dict[str, Any]:
    return AdminUserTrialOut.from_orm_trial(user, trial_subs).model_dump(mode="json")


async def admin_user_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    settings: Settings = get_settings(request)

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
        trial_subs_stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == target_id,
                sa_func.lower(sa_func.coalesce(Subscription.provider, "")) == "trial",
            )
            .order_by(Subscription.start_date.asc().nullslast(), Subscription.end_date.asc())
        )
        trial_subs = (await session.execute(trial_subs_stmt)).scalars().all()
        total_paid = await payment_dal.get_user_total_paid(session, target_id)
        recent_payments_stmt = (
            select(Payment)
            .where(Payment.user_id == target_id)
            .order_by(Payment.created_at.desc())
            .limit(20)
        )
        recent_payments = (await session.execute(recent_payments_stmt)).scalars().all()
        log_count = await message_log_dal.count_user_message_logs(session, target_id)
        inviter = await user_dal.get_referrer_for_user(session, user)
        invitees_total = await user_dal.count_users_referred_by(session, target_id)
        avatar_user_ids = [target_id]
        if inviter is not None:
            avatar_user_ids.append(int(inviter.user_id))
        avatar_keys = await _bulk_user_avatar_keys(session, avatar_user_ids)

        # Referral links вЂ” both the bot deep-link and the webapp deep-link.
        referral_code: Optional[str] = None
        try:
            referral_code = await user_dal.ensure_referral_code(session, user)
            await session.commit()
        except Exception as exc_ref:  # pragma: no cover вЂ” defensive
            logger.warning("Failed to ensure referral code for user %s: %s", target_id, exc_ref)
            await session.rollback()

    referral_service: Optional[ReferralService] = get_referral_service(request)
    bot_username = get_bot_username(request)
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
        settings.SUBSCRIPTION_MINI_APP_URL,
        referral_code,
    )

    # Subscription page URL вЂ” the raw panel `subscriptionUrl` that the user
    # imports into their VPN client. May be missing if the user has never
    # been provisioned on the panel.
    subscription_url: Optional[str] = None
    last_vpn_connected_at: Optional[str] = None
    vpn_connection_status = "unknown"
    panel_uuid = getattr(user, "panel_user_uuid", None) or getattr(
        active_sub,
        "panel_user_uuid",
        None,
    )
    if panel_uuid:
        subscription_service = get_optional_subscription_service(request)
        panel_service = getattr(subscription_service, "panel_service", None)
        if panel_service is not None:
            try:
                panel_data = await panel_service.get_user_by_uuid(panel_uuid)
                if panel_data:
                    subscription_url = panel_data.get("subscriptionUrl") or None
                    vpn_activity = _panel_user_connection_activity(panel_data)
                    vpn_connection_status = str(vpn_activity.get("status") or "unknown")
                    last_vpn_connected_at = vpn_activity.get("last_connected_at")
            except Exception as exc_panel:  # pragma: no cover
                logger.warning(
                    "Failed to fetch panel details for user %s (uuid=%s): %s",
                    target_id,
                    panel_uuid,
                    exc_panel,
                )

    serialized_user = _serialize_admin_user_with_avatar(user, avatar_keys)
    serialized_inviter = (
        _serialize_admin_user_with_avatar(inviter, avatar_keys) if inviter is not None else None
    )
    trial_payload = _serialize_trial_summary(user, trial_subs)

    return _ok(
        {
            "user": serialized_user,
            "active_subscription": _serialize_subscription(active_sub) if active_sub else None,
            "subscriptions": [_serialize_subscription(s) for s in (latest_subs or [])],
            "trial": trial_payload,
            "total_paid": float(total_paid),
            "recent_payments": [_serialize_payment(p) for p in recent_payments],
            "log_count": int(log_count or 0),
            "subscription_url": subscription_url,
            "last_vpn_connected_at": last_vpn_connected_at,
            "vpn_connection_status": vpn_connection_status,
            "referral": {
                "code": referral_code,
                "bot_link": referral_bot_link,
                "webapp_link": referral_webapp_link,
                "inviter": serialized_inviter,
                "invitees_total": int(invitees_total or 0),
            },
        }
    )


async def admin_user_referrals_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found", "User not found")

        inviter = await user_dal.get_referrer_for_user(session, user)
        invitees_total = await user_dal.count_users_referred_by(session, target_id)
        invitees = await user_dal.get_users_referred_by(
            session,
            target_id,
            limit=page_size,
            offset=page * page_size,
        )
        avatar_user_ids = [target_id, *(int(u.user_id) for u in invitees)]
        if inviter is not None:
            avatar_user_ids.append(int(inviter.user_id))
        avatar_keys = await _bulk_user_avatar_keys(session, avatar_user_ids)

    return _ok(
        {
            "user": _serialize_admin_user_with_avatar(user, avatar_keys),
            "inviter": _serialize_admin_user_with_avatar(inviter, avatar_keys)
            if inviter is not None
            else None,
            "invitees": [
                _serialize_admin_user_with_avatar(invitee, avatar_keys) for invitee in invitees
            ],
            "total": int(invitees_total or 0),
            "page": page,
            "page_size": page_size,
        }
    )
