from __future__ import annotations

import logging
from datetime import datetime

from aiohttp import web
from pydantic import Field

from bot.app.web.context import get_session_factory, get_settings, get_subscription_service
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.services.checkout_addons import checkout_addon_grants
from bot.services.subscription_gifts import GiftError, activation_conflict, claim_gift, gift_url
from bot.services.subscription_order_terms import read_subscription_terms
from db.dal import gift_dal, payment_dal, subscription_dal, user_dal
from db.gift_models import SubscriptionGift
from db.models import Payment

from .assets import _enforce_webapp_rate_limit
from .auth_common import _public_webapp_base_url
from .common import _invalidate_webapp_user_caches, _json_error, _require_user_id
from .response_helpers import json_response
from .serializers_plans import _serialize_plans


async def gift_options_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        plans = _serialize_plans(settings, user.language_code or settings.DEFAULT_LANGUAGE)
    return json_response(
        {
            "ok": True,
            "email_available": bool(
                settings.smtp_delivery_configured and settings.SUBSCRIPTION_MINI_APP_URL
            ),
            "enabled": settings.GIFTS_ENABLED,
            "plans": [
                plan for plan in plans if plan.get("sale_mode", "subscription") == "subscription"
            ]
            if settings.GIFTS_ENABLED
            else [],
        }
    )


class GiftTokenBody(HttpBodyModel):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class GiftView(HttpResponseModel):
    gift_id: int
    payment_id: int
    status: str
    tariff_title: str
    duration_days: int
    devices: int | None = None
    regular_limit_gb: float | None = None
    premium_limit_gb: float | None = None
    premium_unlimited: bool = False
    created_at: datetime | None = None
    activated_at: datetime | None = None
    activation_end_at: datetime | None = None
    link: str | None = None
    owned: bool = False
    claimed_by_me: bool = False
    conflict: str = ""
    bonus_days: int = 0
    regular_bonus_gb: float = 0
    premium_bonus_gb: float = 0
    recipient_email: str | None = None
    delivery_status: str | None = None
    delivered_at: datetime | None = None
    extends_subscription: bool = False

    @classmethod
    def from_orm_gift(
        cls,
        gift: SubscriptionGift,
        payment: Payment,
        *,
        viewer_id: int,
        base_url: str,
        language: str = "ru",
    ) -> GiftView:
        terms = read_subscription_terms(payment)
        tariff = terms.tariff if terms else None
        addons = checkout_addon_grants(payment.checkout_bundle_snapshot)
        owned = gift.purchaser_id == viewer_id
        status = str(gift.status) if payment.status == "succeeded" else "revoked"
        return cls(
            gift_id=int(gift.gift_id),
            payment_id=int(gift.payment_id),
            status=status,
            tariff_title=tariff.name(language) if tariff else str(payment.tariff_key or ""),
            duration_days=terms.duration_days
            if terms
            else int(payment.subscription_duration_days or 0),
            devices=(int(tariff.hwid_device_limit or 0) + addons.device_count)
            if tariff
            else (terms.legacy_limits.get("devices") if terms and terms.legacy_limits else None),
            regular_limit_gb=addons.regular_limit_gb
            if addons.regular_limit_gb is not None
            else (
                tariff.monthly_gb
                if tariff
                else (
                    (terms.legacy_limits.get("traffic") or 0) / 1024**3
                    if terms and terms.legacy_limits
                    else None
                )
            ),
            premium_limit_gb=addons.premium_limit_gb
            if addons.premium_limit_gb is not None
            else (tariff.premium_monthly_gb if tariff else None),
            premium_unlimited=bool(tariff and tariff.premium_unlimited),
            created_at=gift.created_at,
            activated_at=gift.activated_at,
            activation_end_at=gift.activation_end_at,
            link=gift_url(base_url, str(gift.token)) if owned and status == "ready" else None,
            owned=owned,
            claimed_by_me=gift.recipient_id == viewer_id,
            bonus_days=int(gift.bonus_days or 0),
            regular_bonus_gb=float(gift.regular_bonus_gb or 0),
            premium_bonus_gb=float(gift.premium_bonus_gb or 0),
            recipient_email=gift.recipient_email if owned else None,
            delivery_status=gift.delivery_status if owned else None,
            delivered_at=gift.delivered_at if owned else None,
        )


async def gifts_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    base = _public_webapp_base_url(get_settings(request), request)
    async with get_session_factory(request)() as session:
        rows = await gift_dal.purchased(session, user_id)
        user = await user_dal.get_user_by_id(session, user_id)
        language = user.language_code if user else get_settings(request).DEFAULT_LANGUAGE
        gifts = [
            GiftView.from_orm_gift(
                gift, payment, viewer_id=user_id, base_url=base, language=language
            ).model_dump(mode="json")
            for gift, payment in rows
        ]
    return json_response(
        {"ok": True, "gifts": gifts, "enabled": get_settings(request).GIFTS_ENABLED}
    )


async def gift_preview_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await parse_body_or_400(request, GiftTokenBody)
    limited = await _enforce_webapp_rate_limit(request, user_id=user_id, action="gift-preview")
    if limited is not None:
        return limited
    async with get_session_factory(request)() as session:
        gift = await gift_dal.by_token(session, payload.token)
        if gift is None:
            return _json_error(404, "gift_not_found", "gift_not_found")
        payment = await payment_dal.get_payment_by_db_id(session, int(gift.payment_id))
        if payment is None:
            return _json_error(404, "gift_not_found", "gift_not_found")
        result = GiftView.from_orm_gift(
            gift,
            payment,
            viewer_id=user_id,
            base_url=_public_webapp_base_url(get_settings(request), request),
        )
        active = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
        catalog = get_settings(request).tariffs_config
        result.conflict = activation_conflict(
            gift,
            payment,
            active,
            catalog.get(payment.tariff_key) if catalog else None,
            get_settings(request).USER_TRAFFIC_STRATEGY,
        )
        result.extends_subscription = (
            active is not None and not result.conflict and str(active.provider) != "trial"
        )
        if result.status == "activating" and result.claimed_by_me:
            result.conflict = ""
    return json_response({"ok": True, "gift": result.model_dump(mode="json")})


async def gift_claim_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await parse_body_or_400(request, GiftTokenBody)
    limited = await _enforce_webapp_rate_limit(request, user_id=user_id, action="gift-claim")
    if limited is not None:
        return limited
    async with get_session_factory(request)() as session:
        try:
            await claim_gift(
                session,
                token=payload.token,
                user_id=user_id,
                service=get_subscription_service(request),
            )
        except GiftError as exc:
            return _json_error(exc.status, exc.code, exc.code)
        except Exception:
            logging.getLogger(__name__).error("Gift activation failed for recipient %s", user_id)
            await session.rollback()
            return _json_error(502, "gift_activation_retry", "gift_activation_retry")
    await _invalidate_webapp_user_caches(get_settings(request), user_id, include_devices=True)
    return json_response({"ok": True})
