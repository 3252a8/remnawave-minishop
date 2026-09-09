"""Atomic revocation of an unused paid gift and optional balance refund."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.partner_common import amount_to_minor, currency_scale
from bot.services.user_balance_service import UserBalanceError, UserBalanceService
from db.dal import gift_dal, payment_dal, promo_code_dal
from db.gift_models import SubscriptionGift


class GiftRevokeError(RuntimeError):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


async def revoke_paid_gift(
    session: AsyncSession,
    *,
    gift_id: int,
    actor_admin_id: int,
    reason: str,
    restore_promo_usage: bool,
    refund_to_balance: bool,
    without_reason: bool = False,
) -> SubscriptionGift:
    normalized_reason = reason.strip()
    if not without_reason and len(normalized_reason) < 3:
        raise GiftRevokeError("invalid_gift_revoke_reason", 400)
    # Match activation's lock order: payment, gift, then purchaser balance.
    initial = await session.get(SubscriptionGift, gift_id)
    if initial is None:
        raise GiftRevokeError("gift_not_found", 404)
    payment = await payment_dal.get_payment_by_db_id_for_update(session, int(initial.payment_id))
    gift = await gift_dal.by_payment(session, int(initial.payment_id), lock=True)
    if payment is None or gift is None:
        raise GiftRevokeError("gift_not_found", 404)
    payment_status = str(payment.status).strip().lower()
    if gift.status == "revoked":
        if payment_status == "reversed":
            return gift
        if payment_status != "succeeded":
            raise GiftRevokeError("gift_revoke_unavailable")
        payment.reversed_at = datetime.now(UTC)
        payment.reversed_by_admin_id = actor_admin_id
        payment.reversal_note = normalized_reason
        await session.flush()
        updated = await payment_dal.update_payment_status_by_db_id(
            session,
            int(payment.payment_id),
            "reversed",
        )
        if updated is None:
            raise GiftRevokeError("gift_not_found", 404)
        return gift
    if gift.status != "ready" or payment_status != "succeeded":
        raise GiftRevokeError("gift_revoke_unavailable")
    amount = (
        payment.checkout_total_amount
        if payment.checkout_total_amount is not None
        else payment.amount
    )
    currency = str(payment.currency or "").strip().upper()
    if amount_to_minor(amount, scale=currency_scale(currency)) <= 0:
        raise GiftRevokeError("gift_revoke_unavailable")
    purchaser_id = int(gift.purchaser_id or payment.user_id or 0)
    if purchaser_id <= 0:
        raise GiftRevokeError("gift_purchaser_not_found")
    if refund_to_balance:
        try:
            await UserBalanceService.credit_gift_refund(
                session,
                gift_id=int(gift.gift_id),
                purchaser_id=purchaser_id,
                amount=amount,
                currency=currency,
                actor_admin_id=actor_admin_id,
                reason=normalized_reason,
            )
        except UserBalanceError as exc:
            raise GiftRevokeError(exc.code, exc.status) from exc
    if restore_promo_usage and payment.promo_code_id:
        payment.promo_usage_restored = await promo_code_dal.release_promo_activation(
            session,
            int(payment.promo_code_id),
            int(payment.user_id),
            payment_id=int(payment.payment_id),
        )
    gift.status = "revoked"
    payment.reversed_at = datetime.now(UTC)
    payment.reversed_by_admin_id = actor_admin_id
    payment.reversal_note = normalized_reason
    await session.flush()
    updated = await payment_dal.update_payment_status_by_db_id(
        session,
        int(payment.payment_id),
        "reversed",
    )
    if updated is None:
        raise GiftRevokeError("gift_not_found", 404)
    return gift
