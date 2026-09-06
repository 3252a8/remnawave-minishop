from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.grants import GrantContext, resolve_effective_grant
from bot.services.payment_promo import consume_payment_promo, load_payment_promo_effects
from bot.services.subscription_order_terms import read_subscription_terms
from config.subscription_periods import add_period_days
from db.dal import gift_dal, message_log_dal
from db.gift_models import SubscriptionGift
from db.models import Payment


async def gift_activation_bonuses(
    session: AsyncSession, payment_id: int, user_id: int, provider: str
) -> tuple[int, float, float]:
    if provider != "gift":
        return 0, 0.0, 0.0
    gift = await gift_dal.by_payment(session, payment_id)
    if gift is None or gift.recipient_id != user_id or gift.status != "activating":
        raise ValueError("Gift has not been reserved by this recipient")
    return (
        int(gift.bonus_days or 0),
        float(gift.regular_bonus_gb or 0),
        float(gift.premium_bonus_gb or 0),
    )


async def issue_paid_gift(session: AsyncSession, payment: Payment) -> SubscriptionGift:
    gift = await gift_dal.issue(session, payment)
    terms = read_subscription_terms(payment)
    if terms is None:
        raise ValueError("Gift is missing its immutable subscription terms")
    if payment.promo_code_id:
        promo, effects = await load_payment_promo_effects(session, payment)
        if promo is None or effects is None:
            raise ValueError("Gift is missing its promo terms")
        start = datetime.now(UTC)
        grant = resolve_effective_grant(
            GrantContext(
                sale_mode_base="subscription",
                tariff_key=payment.tariff_key,
                base_period_days=terms.duration_days,
                months=payment.subscription_duration_months,
                charged_gb=None,
                scope="regular",
                promo=effects,
                period_start=start,
                base_period_end=add_period_days(start, terms.duration_days),
                duration_days=terms.duration_days,
            )
        )
        await consume_payment_promo(
            session=session,
            user_id=int(payment.user_id),
            promo_model=promo,
            effects=effects,
            payment_id=int(payment.payment_id),
            payment=payment,
            sale_mode_base="subscription",
            months=payment.subscription_duration_months,
            traffic_gb=None,
            granted_days=grant.extra_days,
            granted_regular_traffic_gb=effects.regular_traffic_gb or None,
            granted_premium_traffic_gb=effects.premium_traffic_gb or None,
        )
        gift.bonus_days = grant.extra_days
        gift.regular_bonus_gb = effects.regular_traffic_gb
        gift.premium_bonus_gb = effects.premium_traffic_gb
    bundle = json.loads(payment.checkout_bundle_snapshot or "{}")
    email = str(bundle.get("gift_recipient_email") or "").strip()
    if email:
        gift.recipient_email = email
        gift.delivery_status = "pending"
    await message_log_dal.create_message_log_no_commit(
        session,
        {
            "user_id": payment.user_id,
            "target_user_id": payment.user_id,
            "event_type": "gift_purchased",
            "is_admin_event": True,
            "content": f"gift_id={gift.gift_id} payment_id={payment.payment_id} "
            f"tariff={payment.tariff_key} "
            f"duration_days={terms.duration_days} bonus_days={gift.bonus_days} "
            f"amount={payment.amount} "
            f"currency={payment.currency} provider={payment.provider}",
        },
    )
    await session.flush()
    return gift
