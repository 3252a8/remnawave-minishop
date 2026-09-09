from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_payment_service,
    get_session_factory,
    get_settings,
)
from bot.payment_providers.registry import get_provider_spec
from bot.payment_providers.shared.common import detached_payment_snapshot
from config.settings import Settings
from db.dal import payment_dal

from .assets import _enforce_webapp_rate_limit
from .auth import _require_user_id
from .billing_status import refresh_payment_status_for_request
from .common import _invalidate_webapp_user_caches, _json_error
from .response_helpers import json_response

logger = logging.getLogger(__name__)

_PENDING_STATUSES = frozenset(
    {
        "active",
        "created",
        "new",
        "open",
        "process",
        "processing",
        "underpaid",
        "waiting_for_capture",
    }
)
_CANCELED_STATUSES = frozenset({"canceled", "cancelled", "failed", "failed_creation"})


def _is_pending_payment(payment: Any) -> bool:
    status = str(getattr(payment, "status", "") or "").strip().lower()
    return status == "pending" or status.startswith("pending_") or status in _PENDING_STATUSES


def _provider_payment_id(payment: Any) -> str:
    return str(
        getattr(payment, "provider_payment_id", None)
        or getattr(payment, "yookassa_payment_id", None)
        or ""
    ).strip()


async def _cancel_provider_checkout(request: web.Request, payment: Any) -> bool | None:
    """Return ``None`` when the provider has no confirmed checkout cancellation."""

    provider = str(getattr(payment, "provider", "") or "").strip().lower()
    provider_payment_id = _provider_payment_id(payment)
    spec = get_provider_spec(provider)
    if spec is None or not spec.service_key or not provider_payment_id:
        return None

    service = get_payment_service(request, spec.service_key)
    if service is None or not getattr(service, "configured", False):
        return False

    cancel = getattr(service, "cancel_pending_checkout", None)
    if not callable(cancel) and provider == "yookassa":
        cancel = getattr(service, "cancel_payment", None)
    if not callable(cancel):
        cancel = getattr(service, "cancel_pending_bill", None)
    if not callable(cancel):
        return None

    try:
        result = await cancel(provider_payment_id)
    except Exception:
        logger.exception(
            "Provider %s failed to cancel customer checkout %s.",
            provider,
            getattr(payment, "payment_id", None),
        )
        return False
    if isinstance(result, tuple):
        return bool(result and result[0])
    return bool(result)


def _terminal_cancel_response(payment: Any) -> web.Response | None:
    status = str(getattr(payment, "status", "") or "").strip().lower()
    if status in _CANCELED_STATUSES:
        return json_response(
            {
                "ok": True,
                "payment_id": int(payment.payment_id),
                "status": status,
            }
        )
    if status == "succeeded":
        return _json_error(409, "payment_completed", "Payment is already completed")
    if not _is_pending_payment(payment):
        return _json_error(409, "payment_not_pending", "Payment is no longer pending")
    return None


async def cancel_payment_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    try:
        payment_id = int(request.match_info["payment_id"])
    except (KeyError, TypeError, ValueError):
        return _json_error(400, "invalid_payment", "Invalid payment id")

    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="payments_cancel",
    )
    if rate_limit_response:
        return rate_limit_response

    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            payment = await payment_dal.get_payment_by_db_id(session, payment_id)
            if payment is None or int(payment.user_id) != int(user_id):
                return _json_error(404, "not_found", "Payment not found")

            payment = await refresh_payment_status_for_request(request, session, payment)
            terminal_response = _terminal_cancel_response(payment)
            if terminal_response is not None:
                await session.rollback()
                return terminal_response
            if getattr(payment, "promo_code_id", None) is None:
                await session.rollback()
                return _json_error(
                    409,
                    "payment_has_no_promo",
                    "Payment does not reserve a promo code",
                )

            payment_snapshot = detached_payment_snapshot(payment)
            await session.rollback()
            provider_canceled = await _cancel_provider_checkout(request, payment_snapshot)
            if provider_canceled is None:
                return _json_error(
                    409,
                    "payment_cancel_unavailable",
                    "This payment provider cannot cancel the checkout immediately",
                )
            if not provider_canceled:
                return _json_error(
                    502,
                    "payment_cancel_provider_failed",
                    "The payment provider did not confirm the cancellation",
                )

            updated, _transitioned = await payment_dal.transition_provider_payment_to_terminal(
                session,
                payment_id,
                _provider_payment_id(payment_snapshot),
                "canceled",
                failure_kind="customer_canceled_checkout",
                provider_cancellation_party="customer",
                provider_cancellation_reason="customer_requested_promo_reuse",
                suppress_failure_notification=True,
            )
            if updated is None:
                await session.rollback()
                return _json_error(404, "not_found", "Payment not found")
            updated_status = str(updated.status or "").strip().lower()
            if updated_status == "succeeded":
                await session.rollback()
                return _json_error(409, "payment_completed", "Payment is already completed")
            if updated_status not in _CANCELED_STATUSES:
                await session.rollback()
                return _json_error(409, "payment_not_pending", "Payment is no longer pending")

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("WebApp payment cancellation failed for payment %s", payment_id)
            return _json_error(500, "payment_cancel_failed", "Payment cancellation failed")

    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True, "payment_id": payment_id, "status": "canceled"})
