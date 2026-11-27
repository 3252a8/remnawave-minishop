"""Load the same account summaries as the stock Minishop users table."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_api_impl.common import _premium_traffic_list_payload, _serialize_user
from bot.app.web.admin_api_impl.subscription_plans import (
    admin_subscription_plan,
    admin_tariff_options,
)
from bot.app.web.admin_api_impl.users_common import _bulk_user_avatar_keys
from bot.app.web.admin_api_impl.users_detail import (
    _bulk_active_subscriptions_for_users,
    _bulk_user_payment_summaries,
    _bulk_user_referral_counts,
)
from bot.app.web.admin_api_impl.users_listing import _bulk_user_statuses
from bot.services.partner_common import currency_scale
from config.settings import Settings
from db.dal import partner_dal, user_balance_dal, user_subscription_plans
from db.models import User


async def load_matched_profiles(
    session: AsyncSession, users: Sequence[User], settings: Settings, *, now: datetime
) -> tuple[dict[int, dict[str, object]], dict[str, object]]:
    user_ids = [int(user.user_id) for user in users]
    balance = settings.balance_settings
    currency = str(balance.currency).upper()
    partner_enabled = bool(settings.partner_settings.enabled)
    observed_tariffs = await user_subscription_plans.get_subscription_plan_tariff_keys(
        session, now=now
    )
    metadata: dict[str, object] = {
        "balance_currency": currency,
        "balance_currency_scale": currency_scale(currency),
        "partner_balance_enabled": partner_enabled,
        "user_balance_enabled": bool(balance.enabled),
        "tariff_options": admin_tariff_options(settings, observed_tariffs),
    }
    if not user_ids:
        return {}, metadata

    plans = await user_subscription_plans.get_user_subscription_plans(session, user_ids, now=now)
    statuses = await _bulk_user_statuses(session, user_ids)
    avatars = await _bulk_user_avatar_keys(session, user_ids)
    subscriptions = await _bulk_active_subscriptions_for_users(session, user_ids)
    payments = await _bulk_user_payment_summaries(session, user_ids)
    referrals = await _bulk_user_referral_counts(session, user_ids)
    user_balances = (
        await user_balance_dal.balance_minor_by_user_ids(session, user_ids, currency)
        if balance.enabled
        else {}
    )
    partner_balances = (
        await partner_dal.balance_minor_by_user_ids(session, user_ids, currency)
        if partner_enabled
        else {}
    )

    rows: dict[int, dict[str, object]] = {}
    for user in users:
        user_id = int(user.user_id)
        status = statuses.get(user_id) or {"status": "bot_only", "end_date": None}
        payment = payments.get(user_id) or {}
        rows[user_id] = {
            **_serialize_user(user),
            "subscription_plan": admin_subscription_plan(settings, plans.get(user_id)),
            "panel_status": status["status"],
            "subscription_expires_at": status["end_date"],
            "panel_status_expired_at": status["end_date"]
            if status["status"] == "expired"
            else None,
            "avatar_url": (
                f"/api/admin/users/{user_id}/avatar?v={avatars[user_id]}"
                if user_id in avatars
                else None
            ),
            "premium_traffic": _premium_traffic_list_payload(subscriptions.get(user_id)),
            "payments_total_amount": float(payment.get("total_amount") or 0),
            "payments_count": int(payment.get("count") or 0),
            "payments_currency": payment.get("currency"),
            "invited_users_count": int(referrals.get(user_id) or 0),
            "user_balance_amount_minor": int(user_balances.get(user_id) or 0),
            "partner_balance_amount_minor": int(partner_balances.get(user_id) or 0),
        }
    return rows, metadata
