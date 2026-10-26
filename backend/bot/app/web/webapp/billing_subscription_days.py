"""Web App entry point for confirmed subscription-day add-on purchases."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from sqlalchemy import select

from bot.app.web.context import (
    get_i18n,
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.services.subscription_days_purchase import purchase_with_days
from bot.services.subscription_days_quotes import AddonSelection, SubscriptionDaysError
from db.dal import user_dal
from db.models import User

from .billing_quotes import _localized_payment_description
from .common import _json_error
from .payloads import WebAppPaymentCreatePayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def _restore_committed_entitlement(request: web.Request, user_id: int) -> None:
    """Compensate an ambiguous panel write using freshly locked committed DB state."""
    try:
        async with get_session_factory(request)() as session:
            await session.scalar(select(User).where(User.user_id == user_id).with_for_update())
            service = get_subscription_service(request)
            if not await service.sync_main_traffic_limit_to_panel(session, user_id):
                logger.error(
                    "Could not restore committed entitlement after day purchase for %s", user_id
                )
            await session.commit()
    except Exception:
        logger.exception("Day purchase panel compensation failed for user %s", user_id)


async def create_subscription_days_payment(
    request: web.Request,
    user_id: int,
    payload: WebAppPaymentCreatePayload,
) -> web.Response:
    if (
        not payload.quote_token
        or payload.gift
        or payload.renew_hwid_devices
        or payload.checkout_addons is not None
        or payload.promo_code
        or payload.use_partner_balance
        or payload.balance_source is not None
        or payload.balance_auto_renew
    ):
        return _json_error(
            400, "invalid_subscription_days_purchase", "Unsupported day purchase options"
        )
    try:
        selection = AddonSelection.parse(
            payload.sale_mode,
            payload.tariff_key,
            payload.device_count
            if str(payload.sale_mode or "").split("@", 1)[0] == "hwid_devices"
            else payload.traffic_gb,
        )
    except SubscriptionDaysError as exc:
        return _json_error(exc.status, exc.code, "Invalid add-on selection")
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        description = _localized_payment_description(
            i18n=get_i18n(request),
            lang=user.language_code or get_settings(request).DEFAULT_LANGUAGE,
            units=int(selection.units)
            if selection.mode == "hwid_devices"
            else float(selection.units),
            sale_mode=f"{selection.mode}@{selection.tariff_key}",
            traffic_gb=float(selection.units) if selection.mode != "hwid_devices" else None,
        )
        try:
            payment = await purchase_with_days(
                session,
                get_subscription_service(request),
                user_id=user_id,
                selection=selection,
                token=payload.quote_token,
                description=description,
            )
            payment_id = int(payment.payment_id)
            await session.commit()
        except SubscriptionDaysError as exc:
            await session.rollback()
            if exc.code == "subscription_days_panel_failed":
                await _restore_committed_entitlement(request, user_id)
            return _json_error(exc.status, exc.code, exc.reason or exc.code)
        except asyncio.CancelledError:
            await session.rollback()
            await asyncio.shield(_restore_committed_entitlement(request, user_id))
            raise
        except Exception:
            await session.rollback()
            logger.exception("Subscription-day purchase failed for user %s", user_id)
            await _restore_committed_entitlement(request, user_id)
            return _json_error(
                502, "subscription_days_panel_failed", "The purchase could not be completed"
            )
    return json_response(
        {
            "ok": True,
            "action": "completed",
            "payment_id": payment_id,
            "status": "succeeded",
            "paid": True,
        }
    )
