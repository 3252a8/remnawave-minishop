"""SQL query construction for admin user search, filters and pagination."""

from datetime import UTC, datetime

from sqlalchemy import String, and_, case, or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from db.dal.user_subscription_plans import user_subscription_plans_sq
from db.dal.user_subscription_segments import (
    active_subscription_exists_for_user,
    active_subscription_segment_flags_sq,
    expired_subscription_exists_for_user,
    subscription_segment_condition,
)
from db.models import Payment, Subscription, User


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


def _user_payment_summary_sq() -> Subquery:
    return (
        select(
            Payment.user_id.label("user_id"),
            sa_func.coalesce(sa_func.sum(Payment.amount), 0.0).label("payments_total_amount"),
            sa_func.count(Payment.payment_id).label("payments_count"),
        )
        .where(Payment.status == "succeeded", Payment.funding_source == "external")
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


def _user_status_sort_sq() -> Subquery:
    rank = sa_func.row_number().over(
        partition_by=Subscription.user_id,
        order_by=(
            Subscription.is_active.desc(),
            Subscription.end_date.desc().nullslast(),
            Subscription.subscription_id.desc(),
        ),
    )
    inner = select(
        Subscription.user_id,
        Subscription.status_from_panel,
        Subscription.is_active,
        Subscription.end_date,
        rank.label("rank"),
    ).subquery()
    return select(inner).where(inner.c.rank == 1).subquery(name="user_status_sort")


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
    valid_tariff_keys: set[str] | None = None,
    tariff_filter: str = "all",
    now: datetime | None = None,
) -> tuple[list[User], int]:
    """Return paginated users with optional search, filter and sort applied."""

    now = now or datetime.now(UTC)
    sort_key = (sort_value or "registered_desc").lower()
    pt_filter = (premium_traffic or "all").lower()
    needs_premium_sq = pt_filter != "all" or sort_key in {
        "premium_ratio_asc",
        "premium_ratio_desc",
    }

    stmt = select(User)
    count_stmt = select(sa_func.count(User.user_id))

    sq = None
    plim_expr = None
    pu_expr = None
    payment_summary_sq = None
    payment_total_expr = None
    payment_count_expr = None
    referral_count_sq = None
    referral_count_expr = None
    subscription_expiry_sq = None
    subscription_expires_expr = None
    status_sort_sq = None
    status_sort_expr = None

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

    if sort_key in {"status_asc", "status_desc"}:
        status_sort_sq = _user_status_sort_sq()
        stmt = stmt.outerjoin(status_sort_sq, User.user_id == status_sort_sq.c.user_id)
        count_stmt = count_stmt.outerjoin(status_sort_sq, User.user_id == status_sort_sq.c.user_id)
        status_sort_expr = case(
            (User.is_banned.is_(True), "banned"),
            (status_sort_sq.c.user_id.is_(None), "bot_only"),
            (
                and_(
                    status_sort_sq.c.is_active.is_(True),
                    or_(status_sort_sq.c.end_date.is_(None), status_sort_sq.c.end_date > now),
                ),
                sa_func.lower(sa_func.coalesce(status_sort_sq.c.status_from_panel, "active")),
            ),
            (status_sort_sq.c.end_date <= now, "expired"),
            else_=sa_func.lower(sa_func.coalesce(status_sort_sq.c.status_from_panel, "expired")),
        )

    search_cond = _user_search_condition(query)
    if search_cond is not None:
        stmt = stmt.where(search_cond)
        count_stmt = count_stmt.where(search_cond)

    f = (filter_value or "all").lower()
    if f in {"paid", "trial", "free"}:
        segment_flags_sq = active_subscription_segment_flags_sq(now)
        stmt = stmt.join(segment_flags_sq, User.user_id == segment_flags_sq.c.user_id)
        count_stmt = count_stmt.join(segment_flags_sq, User.user_id == segment_flags_sq.c.user_id)
        cond = subscription_segment_condition(f, segment_flags_sq)
    elif f == "active_today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cond = User.registration_date >= today_start
    elif f == "referred":
        cond = User.referred_by_id.is_not(None)
    elif f == "active_subscription":
        cond = active_subscription_exists_for_user(now)
    elif f == "inactive_subscription":
        cond = ~active_subscription_exists_for_user(now)
    elif f == "expired_subscription":
        cond = and_(
            expired_subscription_exists_for_user(now),
            ~active_subscription_exists_for_user(now),
        )
    elif f == "unmapped_tariff":
        unmapped_subscription = aliased(Subscription)
        unmapped_conditions = [
            unmapped_subscription.tariff_key.is_(None),
            sa_func.trim(unmapped_subscription.tariff_key) == "",
        ]
        if valid_tariff_keys is not None:
            unmapped_conditions.append(
                sa_func.trim(unmapped_subscription.tariff_key).not_in(sorted(valid_tariff_keys))
            )
        cond = (
            select(unmapped_subscription.subscription_id)
            .where(
                unmapped_subscription.user_id == User.user_id,
                unmapped_subscription.is_active.is_(True),
                unmapped_subscription.end_date > now,
                or_(*unmapped_conditions),
            )
            .exists()
        )
    elif f == "banned":
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

    if tariff_filter != "all":
        plans_sq = user_subscription_plans_sq(now)
        stmt = stmt.outerjoin(plans_sq, User.user_id == plans_sq.c.user_id)
        count_stmt = count_stmt.outerjoin(plans_sq, User.user_id == plans_sq.c.user_id)
        if tariff_filter == "no_subscription":
            plan_condition = plans_sq.c.user_id.is_(None)
        elif tariff_filter == "trial":
            plan_condition = plans_sq.c.is_trial.is_(True)
        elif tariff_filter == "no_tariff":
            plan_condition = and_(
                plans_sq.c.user_id.is_not(None),
                plans_sq.c.is_trial.is_(False),
                plans_sq.c.tariff_key.is_(None),
            )
        else:
            plan_condition = and_(
                plans_sq.c.is_trial.is_(False),
                plans_sq.c.tariff_key == tariff_filter.removeprefix("tariff:"),
            )
        stmt = stmt.where(plan_condition)
        count_stmt = count_stmt.where(plan_condition)

    panel_cond = _user_panel_status_condition(panel_status, now=now)
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
        "registered_desc": (User.registration_date.desc().nullslast(), User.user_id.desc()),
        "registered_asc": (User.registration_date.asc().nullslast(), User.user_id.asc()),
        "name_asc": (
            sa_func.coalesce(User.first_name, User.username, User.email).asc(),
            User.user_id.asc(),
        ),
        "name_desc": (
            sa_func.coalesce(User.first_name, User.username, User.email).desc(),
            User.user_id.desc(),
        ),
        "id_asc": (User.minishop_id.asc(), User.user_id.asc()),
        "id_desc": (User.minishop_id.desc(), User.user_id.desc()),
    }

    # Keep the historical wire values for bookmarked admin URLs, but the
    # Premium traffic column sorts by the absolute consumed bytes it displays.
    if needs_premium_sq and pu_expr is not None and sort_key == "premium_ratio_asc":
        stmt = stmt.order_by(pu_expr.asc(), User.user_id.asc())
    elif needs_premium_sq and pu_expr is not None and sort_key == "premium_ratio_desc":
        stmt = stmt.order_by(pu_expr.desc(), User.user_id.desc())
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
    elif status_sort_expr is not None and sort_key == "status_asc":
        stmt = stmt.order_by(status_sort_expr.asc().nullslast(), User.user_id.asc())
    elif status_sort_expr is not None and sort_key == "status_desc":
        stmt = stmt.order_by(status_sort_expr.desc().nullslast(), User.user_id.desc())
    else:
        order = sort_map.get(sort_key, sort_map["registered_desc"])
        stmt = stmt.order_by(*order) if isinstance(order, tuple) else stmt.order_by(order)

    stmt = stmt.offset(max(page, 0) * max(page_size, 1)).limit(max(page_size, 1))

    users = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return list(users), int(total)


def _user_panel_status_condition(
    panel_status: str, *, now: datetime | None = None
) -> ColumnElement[bool] | None:
    now = now or datetime.now(UTC)
    status = (panel_status or "all").lower()
    if status not in {"active", "expired", "limited"}:
        return None

    normalized_status = sa_func.lower(sa_func.coalesce(Subscription.status_from_panel, ""))
    blank_status = or_(
        Subscription.status_from_panel.is_(None), Subscription.status_from_panel == ""
    )
    if status == "active":
        status_cond = and_(
            User.is_banned.is_(False),
            Subscription.is_active.is_(True),
            Subscription.end_date > now,
            or_(normalized_status == "active", blank_status),
        )
    elif status == "expired":
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
        status_cond = and_(
            User.is_banned.is_(False),
            Subscription.is_active.is_(True),
            Subscription.end_date > now,
            normalized_status == "limited",
        )

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
        User.minishop_id.ilike(like),
        User.panel_username.ilike(like),
        User.account_id.cast(String).ilike(like),
    ]
    numeric_token = raw.removeprefix("-")
    if numeric_token.isascii() and numeric_token.isdecimal() and len(numeric_token) <= 19:
        numeric = int(raw)
        if -(2**63) <= numeric < 2**63:
            conditions.extend([User.user_id == numeric, User.telegram_id == numeric])

    return or_(*conditions)
