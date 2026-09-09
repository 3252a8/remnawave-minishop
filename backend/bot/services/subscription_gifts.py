from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.checkout_addons import checkout_addon_grants
from bot.services.subscription_order_terms import gift_tariff, read_subscription_terms
from bot.services.trial_days import paid_subscription_period_start
from config.subscription_periods import add_period_days
from config.tariffs_config import Tariff
from db.dal import gift_dal, message_log_dal, payment_dal, subscription_dal, user_dal
from db.gift_models import SubscriptionGift
from db.models import Payment, Subscription

if TYPE_CHECKING:
    from bot.services.subscription_service_impl.core import SubscriptionService


def is_gift_sale(sale_mode: object) -> bool:
    return "gift" in str(sale_mode or "").split("|")[1:]


def gift_payment_method_available(method: str) -> bool:
    from bot.payment_providers import get_provider_spec

    spec = get_provider_spec(method)
    return bool(spec and spec.create_webapp_payment and not spec.manages_recurring)


def gift_url(base_url: str, token: str) -> str:
    parsed = urlsplit(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/?{urlencode({'gift': token})}"


class GiftError(ValueError):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def activation_conflict(
    gift: SubscriptionGift,
    payment: Payment,
    sub: Subscription | None,
    configured_tariff: Tariff | None = None,
    default_traffic_strategy: str = "NO_RESET",
) -> str:
    from bot.services.subscription_service_impl.entitlement_helpers import subscription_is_trial

    if sub is None:
        return ""
    if subscription_is_trial(sub):
        return ""
    if sub.auto_renew_enabled:
        return "gift_recurring_conflict"
    # Preserve paid time and quotas. A different plan can be redeemed after
    # expiry; there is deliberately no expiry on the gift itself.
    if str(sub.tariff_key or "") != str(payment.tariff_key or ""):
        return "gift_tariff_conflict"
    current = gift_tariff(sub) or configured_tariff
    terms = read_subscription_terms(payment)
    if current is not None and terms is not None and terms.tariff is not None:
        fields = {
            "billing_model",
            "monthly_gb",
            "premium_monthly_gb",
            "premium_unlimited",
            "traffic_limit_strategy",
            "premium_traffic_limit_strategy",
            "hwid_device_limit",
            "squad_uuids",
            "premium_squad_uuids",
        }
        # A reused key with changed entitlements is not the same plan. Wait for
        # existing paid time to end instead of replacing either set of terms.
        current = current.model_copy(
            update={
                "hwid_device_limit": current.hwid_device_limit
                if current.hwid_device_limit is not None
                else sub.hwid_device_limit,
                "traffic_limit_strategy": current.traffic_limit_strategy
                or default_traffic_strategy,
            }
        )
        if current.model_dump(include=fields) != terms.tariff.model_dump(include=fields):
            return "gift_tariff_conflict"
    return ""


async def claim_gift(
    session: AsyncSession,
    *,
    token: str,
    user_id: int,
    service: SubscriptionService,
) -> SubscriptionGift:
    from bot.services.subscription_service_impl.entitlement_helpers import subscription_is_trial

    gift = await gift_dal.by_token(session, token)
    if gift is None:
        raise GiftError("gift_not_found", 404)
    # Always lock payment -> gift -> recipient, also used by reversal.
    payment = await payment_dal.get_payment_by_db_id_for_update(session, int(gift.payment_id))
    gift = await gift_dal.by_payment(session, int(gift.payment_id), lock=True)
    if gift is None or payment is None or payment.status != "succeeded" or gift.status == "revoked":
        raise GiftError("gift_unavailable")
    if gift.purchaser_id == user_id and gift.status == "ready":
        raise GiftError("gift_own")
    if gift.status in {"activating", "activated"} and gift.recipient_id != user_id:
        raise GiftError("gift_used")
    if gift.status == "activated":
        return gift
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None or user.is_banned:
        raise GiftError("access_denied", 403)
    pending = await gift_dal.activating_for_user(session, user_id)
    if pending is not None and pending.gift_id != gift.gift_id:
        raise GiftError("gift_other_activation_pending")
    active = await subscription_dal.get_active_subscription_by_user_id_for_update(session, user_id)
    catalog = service.settings.tariffs_config
    conflict = activation_conflict(
        gift,
        payment,
        active,
        catalog.get(payment.tariff_key) if catalog else None,
        service.settings.USER_TRAFFIC_STRATEGY,
    )
    if gift.status == "ready" and conflict:
        raise GiftError(conflict)
    terms = read_subscription_terms(payment)
    if terms is None:
        raise GiftError("gift_unavailable")
    if gift.status == "ready":
        start = paid_subscription_period_start(
            datetime.now(UTC),
            active,
            service._subscription_billing_model(active),
            subscription_is_trial(active) if active else False,
            checkout_addon_grants(payment.checkout_bundle_snapshot).trial_days_strategy,
        )
        gift.activation_end_at = add_period_days(start, terms.duration_days)
        gift.recipient_id = user_id
        gift.status = "activating"
        gift.activation_attempted_at = datetime.now(UTC)
        payment_id = int(payment.payment_id)
        # Bind the recipient before contacting the external panel. A timeout
        # must never let another account consume a partially delivered gift.
        await session.commit()
        payment = await payment_dal.get_payment_by_db_id_for_update(session, payment_id)
        gift = await gift_dal.by_payment(session, payment_id, lock=True)
        if (
            payment is None
            or gift is None
            or payment.status != "succeeded"
            or gift.status == "revoked"
        ):
            raise GiftError("gift_unavailable")
        if gift.recipient_id != user_id:
            raise GiftError("gift_used")
        if gift.status == "activated":
            return gift
        await user_dal.lock_user_by_id(session, user_id)
    result: dict[str, Any] | None = await service.activate_subscription(
        session,
        user_id,
        int(payment.subscription_duration_months or 0),
        float(
            payment.checkout_total_amount
            if payment.checkout_total_amount is not None
            else payment.amount
        ),
        int(payment.payment_id),
        provider="gift",
        sale_mode=str(payment.sale_mode),
        tariff_key=payment.tariff_key,
        authoritative_end_at=gift.activation_end_at,
    )
    if not result or not result.get("end_date"):
        await session.rollback()
        raise GiftError("gift_activation_retry", 502)
    gift.status = "activated"
    gift.activated_at = datetime.now(UTC)
    gift.activation_end_at = result["end_date"]
    await message_log_dal.create_message_log_no_commit(
        session,
        {
            "user_id": user_id,
            "target_user_id": gift.purchaser_id,
            "event_type": "gift_activated",
            "is_admin_event": True,
            "content": f"gift_id={gift.gift_id} payment_id={gift.payment_id} "
            f"purchaser_id={gift.purchaser_id} recipient_id={user_id}",
        },
    )
    await session.flush()
    await session.commit()
    return gift
