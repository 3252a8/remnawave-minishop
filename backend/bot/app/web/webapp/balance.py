from __future__ import annotations

import logging

from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.services.user_balance_service import UserBalanceService
from db.dal import user_dal

from .assets import _enforce_webapp_rate_limit
from .billing_payments import _create_subscription_payment
from .common import _json_error, _normalize_language, _parse_model_payload, _require_user_id
from .payloads import WebAppBalanceTopupPayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def balance_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        payload = await UserBalanceService(settings).snapshot(
            session,
            user_id=user_id,
            include_history=False,
        )
    return json_response({"ok": True, **payload})


async def balance_topup_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    limited = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="balance-topup",
    )
    if limited is not None:
        return limited
    settings = get_settings(request)
    config = settings.balance_settings
    if not config.enabled:
        return _json_error(403, "user_balance_disabled", "User balance is disabled")
    payload = await _parse_model_payload(request, WebAppBalanceTopupPayload)
    amount = float(payload.amount)
    if amount < config.topup_min_amount:
        return _json_error(400, "balance_topup_below_minimum", "Top-up amount is too small")
    if amount > config.topup_max_amount:
        return _json_error(400, "balance_topup_above_maximum", "Top-up amount is too large")
    method = payload.method.strip().lower()
    if method in {"", "stars", "partner_balance", "user_balance"}:
        return _json_error(
            400,
            "balance_topup_payment_unavailable",
            "This payment method cannot top up a balance",
        )
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or bool(user.is_banned):
            return _json_error(403, "access_denied", "Access denied")
        from bot.services.account_roles import is_admin as account_is_admin

        is_admin = await account_is_admin(session, user_id)
        logger.info(
            "Balance top-up requested: user_id=%s amount=%s currency=%s provider=%s",
            user_id,
            amount,
            config.currency,
            method,
        )
        return await _create_subscription_payment(
            request=request,
            session=session,
            user_id=user_id,
            method=method,
            months=1,
            price=amount,
            stars_price=None,
            currency=config.currency,
            lang=_normalize_language(user.language_code or settings.DEFAULT_LANGUAGE),
            sale_mode="balance_topup",
            is_admin=is_admin,
        )
