from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_payment_service, get_session_factory
from bot.app.web.webapp.auth import _require_user_id
from bot.app.web.webapp.common import _json_error
from bot.payment_providers.qa.service import QA_PROVIDER, QA_SERVICE_KEY, QaPaymentService
from db.dal import payment_dal


async def complete_qa_payment_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    service = get_payment_service(request, QA_SERVICE_KEY)
    if (
        not isinstance(service, QaPaymentService)
        or not service.configured
        or not service.config.ENABLED
    ):
        return _json_error(404, "qa_payment_unavailable", "QA payment is unavailable")

    try:
        payment_id = int(request.match_info["payment_id"])
    except (TypeError, ValueError):
        return _json_error(400, "invalid_payment", "Invalid payment id")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        payment = await payment_dal.get_payment_by_db_id(session, payment_id)
        if payment is None or int(payment.user_id) != user_id:
            return _json_error(404, "not_found", "Payment not found")
        if str(payment.provider or "").strip().lower() != QA_PROVIDER:
            return _json_error(400, "provider_mismatch", "Payment provider mismatch")
        return await service.complete_payment(session, payment)
