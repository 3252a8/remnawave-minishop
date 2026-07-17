from datetime import datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from ..models import Subscription, User


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
