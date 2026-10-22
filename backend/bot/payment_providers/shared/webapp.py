from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_dal
from db.models import Payment

from .common import (
    mark_payment_failed_creation,
    payment_creation_failure_metadata,
    payment_failed,
    payment_link_response,
    payment_provider_unavailable,
)

logger = logging.getLogger(__name__)


def _short_repr(value: Any, *, max_length: int = 2000) -> str:
    text = repr(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


async def finalize_webapp_link_payment(
    *,
    session: AsyncSession,
    payment: Payment,
    api_success: bool,
    payment_url: str | None,
    provider_payment_id: str | None = None,
    provider_response: Any | None = None,
    checkout_expires_at: datetime | None = None,
    new_status: str | None = None,
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
    provider_id_stored = True
    if api_success and provider_payment_id and payment_url:
        try:
            updated = await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                str(provider_payment_id),
                new_status or payment.status,
                provider_payment_url=payment_url,
                checkout_expires_at=checkout_expires_at,
            )
            if updated is None:
                raise LookupError(
                    f"payment {payment.payment_id} disappeared before provider update"
                )
            await session.commit()
        except Exception:
            provider_id_stored = False
            await session.rollback()
            logger.exception(
                "%s: failed to persist provider payment id for payment %s.",
                log_prefix,
                payment.payment_id,
            )

    if not api_success or not payment_url or not provider_payment_id or not provider_id_stored:
        provider_unavailable = payment_provider_unavailable(
            provider_response,
            api_success=api_success,
            payment_url=payment_url,
            provider_payment_id=provider_payment_id,
        )
        logger.error(
            "%s: WebApp payment creation failed for payment %s "
            "(user_id=%s, api_success=%s, has_payment_url=%s, "
            "has_provider_payment_id=%s, provider_response=%s).",
            log_prefix,
            getattr(payment, "payment_id", None),
            getattr(payment, "user_id", None),
            api_success,
            bool(payment_url),
            bool(provider_payment_id),
            _short_repr(provider_response),
        )
        try:
            failure_metadata = payment_creation_failure_metadata(
                provider_response,
                api_success=api_success,
            )
            if not provider_id_stored:
                failure_metadata["failure_kind"] = "provider_correlation_persist_failed"
            if provider_unavailable:
                failure_metadata["suppress_failure_notification"] = True
            await mark_payment_failed_creation(
                session,
                payment.payment_id,
                **failure_metadata,
            )
        except Exception:
            await session.rollback()
            logger.exception(
                "%s: failed to mark payment %s as failed_creation.",
                log_prefix,
                payment.payment_id,
            )
        return payment_failed(provider_unavailable=provider_unavailable)

    return payment_link_response(payment_url=payment_url, payment_id=payment.payment_id)
