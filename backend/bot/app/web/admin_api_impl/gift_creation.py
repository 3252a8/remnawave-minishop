"""Admin-only, idempotent issuance of complimentary subscription gifts."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aiohttp import web
from pydantic import ConfigDict, EmailStr, Field
from sqlalchemy import select

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_for,
    ok_envelope_with,
    register_contract,
)
from bot.app.web.webapp.auth_common import _public_webapp_base_url
from bot.app.web.webapp.billing_checkout_bundle import CheckoutBundleError, build_checkout_bundle
from bot.app.web.webapp.billing_quotes import BasePaymentQuote
from bot.app.web.webapp.contract_schemas import PLAN_LIST_SCHEMA
from bot.app.web.webapp.gift_checkout import attach_gift_delivery
from bot.app.web.webapp.payloads import WebAppCheckoutAddonsPayload, WebAppPaymentCreatePayload
from bot.app.web.webapp.serializers_plans import _serialize_plans
from bot.infra import events
from bot.infra.event_payloads import PaymentSucceededPayload
from bot.infra.payment_events import build_payment_succeeded_payload
from bot.services.gift_purchase import issue_paid_gift
from bot.services.subscription_gifts import gift_url
from bot.services.subscription_order_terms import freeze_subscription_terms
from config.settings import Settings
from config.subscription_periods import with_period_days
from db.dal import gift_dal, user_dal
from db.gift_models import SubscriptionGift
from db.models import Payment

from .auth import _require_admin_user_id
from .common import _error, _ok
from .gifts import AdminGiftView


class AdminGiftCreateBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    plan_id: str = Field(min_length=1, max_length=160)
    checkout_addons: WebAppCheckoutAddonsPayload | None = None
    recipient_email: EmailStr | None = None


def _gift_plans(settings: Settings) -> list[dict[str, Any]]:
    plans = []
    for plan in _serialize_plans(settings, settings.DEFAULT_LANGUAGE):
        if plan.get("sale_mode", "subscription") != "subscription":
            continue
        if not plan.get("tariff_key"):
            plan = {
                **plan,
                "id": f"legacy:period:{plan['duration_days']}",
                "effective_hwid_device_limit": settings.USER_HWID_DEVICE_LIMIT or 0,
                "monthly_gb": (settings.user_traffic_limit_bytes or 0) / 1024**3,
                "premium_monthly_gb": 0,
            }
        plans.append(plan)
    return plans


register_contract(
    "admin_gift_options_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "plans": PLAN_LIST_SCHEMA,
                "email_available": {"type": "boolean"},
            }
        )
    ),
)
register_contract(
    "admin_gift_create_route",
    RouteContract(
        request_model=AdminGiftCreateBody,
        response_schema=ok_envelope_for(AdminGiftView, key="gift"),
        models=(AdminGiftView,),
    ),
)
register_contract(
    "admin_gift_detail_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminGiftView, key="gift"),
        models=(AdminGiftView,),
    ),
)


async def admin_gift_options_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings = get_settings(request)
    return _ok(
        {
            "plans": _gift_plans(settings),
            "email_available": bool(
                settings.smtp_delivery_configured and settings.SUBSCRIPTION_MINI_APP_URL
            ),
        }
    )


async def admin_gift_create_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminGiftCreateBody)
    settings = get_settings(request)
    key = f"admin-gift:{actor_id}:{body.request_id}"
    created = False
    async with get_session_factory(request)() as session:
        # Serialize same-actor retries, including a lost HTTP response after commit.
        actor = await user_dal.lock_user_by_id(session, actor_id)
        if actor is None or actor.is_banned:
            return _error(403, "access_denied")
        payment = await session.scalar(select(Payment).where(Payment.idempotence_key == key))
        if payment is None:
            if body.recipient_email and not (
                settings.smtp_delivery_configured and settings.SUBSCRIPTION_MINI_APP_URL
            ):
                return _error(400, "gift_email_unavailable")
            plan = next(
                (
                    p
                    for p in _gift_plans(settings)
                    if str(p.get("id")) == body.plan_id
                    and p.get("sale_mode", "subscription") == "subscription"
                ),
                None,
            )
            if plan is None:
                return _error(400, "invalid_plan")
            days = int(plan["duration_days"])
            tariff_key = plan.get("tariff_key")
            sale_mode = (
                with_period_days(
                    f"subscription@{tariff_key}" if tariff_key else "subscription", days
                )
                + "|gift"
            )
            payload = WebAppPaymentCreatePayload(
                gift=True,
                duration_days=days,
                tariff_key=tariff_key,
                checkout_addons=body.checkout_addons,
                gift_recipient_email=body.recipient_email,
            )
            quote = BasePaymentQuote(
                payment_units=int(plan.get("period_key") or plan.get("months") or 0),
                price=float(plan.get("price") or 0),
                stars_price=plan.get("stars_price"),
                sale_mode=sale_mode,
                traffic_gb_for_payment=None,
                default_currency_code=str(plan["currency"]),
            )
            try:
                _, bundle = build_checkout_bundle(
                    quote, settings=settings, payment_payload=payload, method="admin_gift"
                )
            except CheckoutBundleError as exc:
                return _error(400, exc.code)
            bundle = attach_gift_delivery(bundle, payload, settings.TRIAL_DAYS_STRATEGY)
            # Do not let free add-ons become paid credit in later tariff calculations.
            snapshot = json.loads(bundle.snapshot or "{}")
            for field in (
                "base_subscription_amount",
                "base_subscription_stars",
                "addons_amount",
                "addons_stars",
            ):
                if field in snapshot:
                    snapshot[field] = 0
            for item in snapshot.get("items", []):
                for field in (
                    "amount",
                    "stars_amount",
                    "future_amount",
                    "future_stars_amount",
                    "immediate_amount",
                    "immediate_stars_amount",
                ):
                    if field in item:
                        item[field] = 0
            encoded_snapshot = json.dumps(
                snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            terms = freeze_subscription_terms(settings, sale_mode)
            assert terms is not None
            frozen = json.loads(terms)
            frozen.update(inviter_days=0, referee_days=0, grant_source="admin")
            payment = Payment(
                user_id=actor_id,
                idempotence_key=key,
                provider="admin_gift",
                funding_source="admin_grant",
                amount=0,
                currency=quote.default_currency_code,
                status="succeeded",
                sale_mode=sale_mode,
                tariff_key=tariff_key,
                subscription_duration_months=plan.get("months") or 0,
                subscription_duration_days=days,
                period_semantics="fixed_days",
                subscription_terms_snapshot=json.dumps(frozen, ensure_ascii=False, sort_keys=True),
                checkout_total_amount=0,
                checkout_base_amount=0,
                checkout_discount_amount=0,
                checkout_bundle_snapshot=encoded_snapshot,
                checkout_bundle_hash=hashlib.sha256(encoded_snapshot.encode()).hexdigest(),
                fulfilled_at=datetime.now(UTC),
                fulfilled_by_admin_id=actor_id,
                fulfillment_source="admin",
            )
            session.add(payment)
            await session.flush()
            gift = await issue_paid_gift(session, payment)
            created = True
        else:
            gift = await gift_dal.by_payment(session, int(payment.payment_id))
            if gift is None:
                return _error(409, "gift_unavailable")
        result = AdminGiftView.from_orm_admin_gift(
            gift,
            payment,
            actor,
            None,
            language=settings.DEFAULT_LANGUAGE,
            balance_enabled=settings.balance_settings.enabled,
        )
        if gift.status == "ready" and payment.status == "succeeded":
            result.link = gift_url(_public_webapp_base_url(settings, request), str(gift.token))
        event = PaymentSucceededPayload.model_validate(
            build_payment_succeeded_payload(
                user_id=actor_id,
                payment_db_id=int(payment.payment_id),
                provider="admin_gift",
                notification_provider="admin_gift",
                amount=0,
                currency=payment.currency,
                sale_mode=payment.sale_mode,
                tariff_key=payment.tariff_key,
                months=payment.subscription_duration_months,
                traffic_gb=None,
                payment=payment,
                activation=None,
                end_date=None,
                is_auto_renew=False,
                renewal_subscription_id=None,
            )
        )
        await session.commit()
    if created:
        await events.emit_model(event)
    return _ok({"gift": result.model_dump(mode="json")})


async def admin_gift_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        gift_id = int(request.match_info["gift_id"])
    except ValueError:
        return _error(400, "invalid_gift")
    async with get_session_factory(request)() as session:
        gift = await session.get(SubscriptionGift, gift_id)
        if gift is None:
            return _error(404, "gift_unavailable")
        payment = await session.get(Payment, gift.payment_id)
        assert payment is not None
        buyer = (
            await user_dal.get_user_by_id(session, gift.purchaser_id) if gift.purchaser_id else None
        )
        recipient = (
            await user_dal.get_user_by_id(session, gift.recipient_id) if gift.recipient_id else None
        )
        settings = get_settings(request)
        result = AdminGiftView.from_orm_admin_gift(
            gift,
            payment,
            buyer,
            recipient,
            language=settings.DEFAULT_LANGUAGE,
            balance_enabled=settings.balance_settings.enabled,
        )
        # Purchased bearer links remain private to the buyer.
        if (
            payment.provider == "admin_gift"
            and gift.status == "ready"
            and payment.status == "succeeded"
        ):
            result.link = gift_url(_public_webapp_base_url(settings, request), str(gift.token))
    return _ok({"gift": result.model_dump(mode="json")})
