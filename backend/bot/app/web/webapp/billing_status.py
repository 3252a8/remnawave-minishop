from bot.app.web.webapp.auth import _require_user_id
from bot.app.web.webapp.common import (
    _json_error,
)
from bot.infra import events
from bot.infra.event_payloads import PaymentCanceledPayload

from ._runtime import (
    Any,
    AsyncSession,
    Dict,
    Payment,
    logger,
    payment_dal,
    sessionmaker,
    web,
)


def _yookassa_payment_payload_for_processing(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    if not isinstance(normalized.get("amount"), dict):
        amount_value = normalized.get("amount_value")
        amount_currency = normalized.get("amount_currency")
        if amount_value is not None or amount_currency:
            normalized["amount"] = {
                "value": str(amount_value if amount_value is not None else 0),
                "currency": amount_currency or "RUB",
            }
    return normalized


def _payment_status_can_be_refreshed(payment: Payment) -> bool:
    normalized = str(getattr(payment, "status", "") or "").lower()
    if normalized == "succeeded":
        return False
    if normalized in {"failed", "canceled", "cancelled", "failed_creation"}:
        return False
    return normalized.startswith("pending") or normalized in {"waiting_for_capture", "created"}


async def _refresh_yookassa_payment_status(
    request: web.Request,
    session: AsyncSession,
    payment: Payment,
) -> Payment:
    if str(getattr(payment, "provider", "") or "").lower() != "yookassa":
        return payment
    if not _payment_status_can_be_refreshed(payment):
        return payment

    yookassa_payment_id = payment.yookassa_payment_id or payment.provider_payment_id
    yookassa_service = request.app.get("yookassa_service")
    if (
        not yookassa_payment_id
        or not yookassa_service
        or not getattr(yookassa_service, "configured", False)
        or not hasattr(yookassa_service, "get_payment_info")
    ):
        return payment

    try:
        provider_payload = await yookassa_service.get_payment_info(yookassa_payment_id)
    except Exception:
        logger.exception("Failed to refresh YooKassa payment %s status", payment.payment_id)
        return payment

    if not provider_payload:
        return payment

    provider_payload = _yookassa_payment_payload_for_processing(provider_payload)
    provider_status = str(provider_payload.get("status") or "").lower()
    if provider_status == "succeeded" and provider_payload.get("paid") is True:
        from bot.payment_providers.yookassa import (
            emit_yookassa_success_events,
            payment_processing_lock,
            process_successful_payment,
        )

        async with payment_processing_lock:
            current = await payment_dal.get_payment_by_db_id(session, payment.payment_id)
            if not current:
                return payment
            if current.status == "succeeded":
                return current
            try:
                event_payload = await process_successful_payment(
                    session,
                    request.app["bot"],
                    provider_payload,
                    request.app["i18n"],
                    request.app["settings"],
                    request.app["panel_service"],
                    request.app["subscription_service"],
                    request.app["referral_service"],
                    request.app.get("lknpd_service"),
                )
                await session.commit()
                if event_payload:
                    await emit_yookassa_success_events(event_payload)
            except Exception:
                await session.rollback()
                logger.exception(
                    "Failed to process refreshed YooKassa payment %s",
                    payment.payment_id,
                )
                return current
            return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or current

    if provider_status in {"canceled", "cancelled"}:
        from bot.payment_providers.yookassa import (
            payment_processing_lock,
            process_cancelled_payment,
        )

        async with payment_processing_lock:
            current = await payment_dal.get_payment_by_db_id(session, payment.payment_id)
            if not current:
                return payment
            if not _payment_status_can_be_refreshed(current):
                return current
            try:
                event_payload = await process_cancelled_payment(
                    session,
                    request.app["bot"],
                    provider_payload,
                    request.app["i18n"],
                    request.app["settings"],
                )
                await session.commit()
                if event_payload:
                    await events.emit_model(
                        PaymentCanceledPayload.model_validate(event_payload),
                        exclude_unset=True,
                    )
            except Exception:
                await session.rollback()
                logger.exception(
                    "Failed to process refreshed cancelled YooKassa payment %s",
                    payment.payment_id,
                )
                return current
            return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or current

    return payment


async def _refresh_wata_payment_status(
    request: web.Request,
    session: AsyncSession,
    payment: Payment,
) -> Payment:
    provider = str(getattr(payment, "provider", "") or "").strip().lower()
    if provider not in {"wata", "wata_crypto"}:
        return payment
    if not _payment_status_can_be_refreshed(payment):
        return payment

    wata_service = request.app.get("wata_service")
    if (
        not wata_service
        or not getattr(wata_service, "configured", False)
        or not hasattr(wata_service, "refresh_payment_status")
    ):
        return payment

    try:
        return await wata_service.refresh_payment_status(session, payment)
    except Exception:
        logger.exception("Failed to refresh Wata payment %s status", payment.payment_id)
        return payment


async def payment_status_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    try:
        payment_id = int(request.match_info["payment_id"])
    except (TypeError, ValueError):
        return _json_error(400, "invalid_payment", "Invalid payment id")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        payment = await payment_dal.get_payment_by_db_id(session, payment_id)
        if not payment or payment.user_id != user_id:
            return _json_error(404, "not_found", "Payment not found")
        payment = await _refresh_yookassa_payment_status(request, session, payment)
        payment = await _refresh_wata_payment_status(request, session, payment)
        return web.json_response(
            {
                "ok": True,
                "payment_id": payment.payment_id,
                "status": payment.status,
                "paid": payment.status == "succeeded",
            }
        )
