from datetime import datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from ..models import Subscription, User


def active_subscription_exists_for_user(now: datetime) -> ColumnElement[bool]:
    """Match users counted by the dashboard as having an active subscription."""

    active_subs = aliased(Subscription)
    return (
        select(active_subs.subscription_id)
        .where(
            active_subs.user_id == User.user_id,
            active_subs.is_active.is_(True),
            active_subs.end_date > now,
        )
        .exists()
    )


def expired_subscription_exists_for_user(now: datetime) -> ColumnElement[bool]:
    """Match a user's expired subscription history using dashboard semantics."""

    expired_subs = aliased(Subscription)
    normalized_status = func.lower(func.coalesce(expired_subs.status_from_panel, ""))
    blank_status = or_(
        expired_subs.status_from_panel.is_(None),
        expired_subs.status_from_panel == "",
    )
    expired_condition = or_(
        normalized_status == "expired",
        blank_status & expired_subs.is_active.is_(False),
        expired_subs.end_date <= now,
    )

    return (
        select(expired_subs.subscription_id)
        .where(expired_subs.user_id == User.user_id, expired_condition)
        .exists()
    )


def active_subscription_segment_flags_sq(now: datetime) -> Subquery:
    """Return one row per user with paid, trial, and free subscription flags."""

    provider_value = func.lower(func.coalesce(Subscription.provider, ""))
    panel_status_value = func.upper(func.coalesce(Subscription.status_from_panel, ""))
    trial_subscription_condition = or_(
        provider_value == "trial",
        panel_status_value == "TRIAL",
    )
    paid_subscription_condition = and_(
        provider_value != "",
        provider_value != "trial",
        panel_status_value != "TRIAL",
    )
    free_subscription_condition = and_(
        provider_value == "",
        panel_status_value != "TRIAL",
    )

    return (
        select(
            Subscription.user_id.label("user_id"),
            func.max(case((paid_subscription_condition, 1), else_=0)).label(
                "has_paid_subscription"
            ),
            func.max(case((trial_subscription_condition, 1), else_=0)).label(
                "has_trial_subscription"
            ),
            func.max(case((free_subscription_condition, 1), else_=0)).label(
                "has_free_subscription"
            ),
        )
        .join(User, Subscription.user_id == User.user_id)
        .where(
            Subscription.is_active.is_(True),
            Subscription.end_date > now,
        )
        .group_by(Subscription.user_id)
        .subquery(name="active_subscription_segment_flags")
    )


def subscription_segment_condition(segment: str, flags_sq: Subquery) -> ColumnElement[bool]:
    """Apply the dashboard's exclusive paid → trial → free segment priority."""

    if segment == "paid":
        return flags_sq.c.has_paid_subscription == 1
    if segment == "trial":
        return and_(
            flags_sq.c.has_paid_subscription == 0,
            flags_sq.c.has_trial_subscription == 1,
        )
    if segment == "free":
        return and_(
            flags_sq.c.has_paid_subscription == 0,
            flags_sq.c.has_trial_subscription == 0,
            flags_sq.c.has_free_subscription == 1,
        )
    raise ValueError(f"Unknown subscription segment: {segment}")
