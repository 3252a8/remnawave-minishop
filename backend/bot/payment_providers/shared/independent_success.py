"""Dispatch purchases which do not activate a Core subscription."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .gift_success import resolve_gift_payment

if TYPE_CHECKING:
    from .success import PaymentSuccessOutcome, PaymentSuccessRequest


async def resolve_independent_payment(
    req: PaymentSuccessRequest,
) -> tuple[bool, PaymentSuccessOutcome | None]:
    from bot.plugins.extensions.payment_finalization import finalize

    from .common import sale_mode_base

    if sale_mode_base(req.sale_mode) == "extension":
        return True, await finalize(req)
    return await resolve_gift_payment(req)
