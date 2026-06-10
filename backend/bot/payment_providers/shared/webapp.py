from __future__ import annotations

import logging
from typing import Optional

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_dal
from db.models import Payment

from .common import mark_payment_failed_creation, payment_failed, payment_link_response


async def finalize_webapp_link_payment(
    *,
    session: AsyncSession,
    payment: Payment,
    api_success: bool,
    payment_url: Optional[str],
    provider_payment_id: Optional[str] = None,
    new_status: Optional[str] = None,
    log_prefix: str,
) -> web.Response:
    """The trailing "persist id → return link or fail" used by every link-style webapp creator.

    Mirrors :func:`render_link_or_fail` but for the webapp HTTP context: instead
    of editing a Telegram message it returns either ``payment_link_response``
    or ``payment_failed``. Provider modules just call:

        payment = await create_webapp_payment_record(ctx, ...)
        success, data = await service.create_xxx(...)
        return await finalize_webapp_link_payment(
            session=ctx.session,
            payment=payment,
            api_success=success,
            payment_url=first_value(data, "url", "payment_url"),
            provider_payment_id=first_value(data, "id"),
            log_prefix="Wata",
        )
    """
    # Reuse logic needs both a provider id and a redirect URL; persisting only
    # the id creates orphan records that match find_recent but fail verification.
    if api_success and provider_payment_id and payment_url:
        try:
            await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                str(provider_payment_id),
                new_status or payment.status,
                provider_payment_url=payment_url,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logging.exception(
                "%s: failed to persist provider payment id for payment %s.",
                log_prefix,
                payment.payment_id,
            )

    if not payment_url:
        try:
            await mark_payment_failed_creation(session, payment.payment_id)
        except Exception:
            await session.rollback()
            logging.exception(
                "%s: failed to mark payment %s as failed_creation.",
                log_prefix,
                payment.payment_id,
            )
        return payment_failed()

    return payment_link_response(payment_url=payment_url, payment_id=payment.payment_id)
