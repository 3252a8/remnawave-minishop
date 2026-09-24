from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from aiohttp import web

from bot.app.web.context import get_session_factory
from db.dal import message_log_dal, user_dal

from .common import _extract_authenticated_user_id

logger = logging.getLogger(__name__)


_AUDITED_MUTATIONS = {
    "/api/balance/topup": "balance_topup",
    "/api/account/language": "account_language",
    "/api/account/email/verify": "account_email_link",
    "/api/account/email/change/confirm": "account_email_change",
    "/api/account/email/notification": "account_notification_email",
    "/api/account/password/confirm": "account_password_change",
    "/api/account/passkeys/register": "account_passkey_register",
    "/api/account/passkeys/delete": "account_passkey_delete",
    "/api/account/identities/unlink": "account_identity_unlink",
    "/api/account/telegram/link": "account_telegram_link",
    "/api/account/telegram/merge/request": "account_telegram_merge_request",
    "/api/account/telegram/merge/confirm": "account_telegram_merge_confirm",
    "/api/referral/welcome-bonus/claim": "referral_bonus_claim",
    "/api/promo/apply": "promo_apply",
    "/api/subscription/auto-renew": "subscription_auto_renew",
    "/api/subscription/reissue": "subscription_reissue",
    "/api/partner/applications": "partner_application_create",
    "/api/partner/withdrawals": "partner_withdrawal_create",
    "/api/partner/withdrawals/{id}": "partner_withdrawal_cancel",
    "/api/partner/balance/renew": "partner_balance_renew",
    "/api/devices/disconnect": "device_disconnect",
    "/api/support/tickets": "support_ticket_create",
    "/api/support/tickets/{id}/messages": "support_ticket_reply",
    "/api/tariffs/change": "tariff_change",
    "/api/tariffs/change-payment": "tariff_change_payment",
    "/api/payments": "payment_create",
    "/api/gifts/claim": "gift_claim",
    "/api/payments/{payment_id}/cancel": "payment_cancel",
    "/api/payments/{payment_id}/qa/complete": "qa_payment_complete",
}


def _route_canonical(request: web.Request) -> str:
    try:
        resource = request.match_info.route.resource
        canonical = getattr(resource, "canonical", None)
        if canonical:
            return str(canonical)
    except (AttributeError, RuntimeError):
        pass
    return request.path


async def _audit_successful_mutation(request: web.Request, response: web.StreamResponse) -> None:
    if request.method != "POST" or response.status >= 400:
        return
    canonical = _route_canonical(request)
    action = _AUDITED_MUTATIONS.get(canonical)
    if not action:
        return
    user_id = _extract_authenticated_user_id(request)
    if user_id is None:
        return

    try:
        async with get_session_factory(request)() as session:
            user = await user_dal.get_user_by_id(session, user_id)
            await message_log_dal.create_message_log(
                session,
                {
                    "user_id": user_id,
                    "telegram_username": getattr(user, "username", None),
                    "telegram_first_name": getattr(user, "first_name", None),
                    "event_type": f"webapp:{action}",
                    "content": f"POST {canonical}; status={response.status}",
                    "is_admin_event": False,
                    "target_user_id": None,
                    "timestamp": datetime.now(UTC),
                },
            )
    except Exception:
        logger.exception("Failed to audit Mini App action %s for user %s", action, user_id)


@web.middleware
async def webapp_action_audit_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    response = await handler(request)
    await _audit_successful_mutation(request, response)
    return response
