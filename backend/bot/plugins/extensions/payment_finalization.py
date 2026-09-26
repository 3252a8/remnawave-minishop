"""Extension orders bypass subscription activation after canonical payment verification."""

from __future__ import annotations

from typing import TYPE_CHECKING

from db.dal import payment_dal

from .commerce import accept_payment

if TYPE_CHECKING:
    from bot.payment_providers.shared.success import PaymentSuccessOutcome, PaymentSuccessRequest


async def finalize(req: PaymentSuccessRequest) -> PaymentSuccessOutcome:
    from bot.payment_providers.shared.success import PaymentSuccessOutcome

    order = await accept_payment(req.session, req.payment)
    await payment_dal.update_payment_status_by_db_id(
        req.session, int(req.payment.payment_id), "succeeded"
    )
    await req.session.commit()
    return PaymentSuccessOutcome(
        activation={"status": "success", "extension_order_id": str(order.id)},
        referral_bonus=None,
        final_end_date=None,
        applied_referee_bonus_days=0,
        applied_promo_bonus_days=0,
        db_user=req.db_user,
        language=str(getattr(req.db_user, "language_code", None) or req.settings.DEFAULT_LANGUAGE),
    )
