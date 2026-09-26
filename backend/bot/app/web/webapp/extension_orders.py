"""Core checkout for immutable extension orders. Providers remain payment authorities."""

import asyncio
import json
from datetime import UTC, datetime

from aiohttp import web
from sqlalchemy import select

from bot.app.web.context import get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import ok_envelope_for
from bot.payment_providers import get_provider_spec
from bot.payment_providers.base import WebAppPaymentContext
from bot.plugins.extensions import ExtensionError
from bot.plugins.extensions.commerce import (
    accept_payment,
    create_order,
    ledger_change,
    lock_order,
    order_snapshot,
    product_provider,
)
from bot.plugins.extensions.jobs import JSON_OBJECT, utc
from bot.services.partner_common import currency_scale, minor_to_decimal_string
from db.dal import payment_dal, user_dal
from db.extension_models import ExtensionOrder

from .assets import _enforce_webapp_rate_limit
from .contract_schemas import user_contract
from .extension_payments import balance_available, payment_methods
from .extension_runtime import user_context
from .extension_schemas import (
    ExtensionCheckout,
    ExtensionCheckoutOut,
    ExtensionOrderCreate,
    ExtensionOrderOut,
    ExtensionOrdersOut,
    ExtensionPaymentMethodOut,
    ExtensionPaymentMethodsOut,
)
from .response_helpers import json_response


def serialize_order(order: ExtensionOrder) -> ExtensionOrderOut:
    snapshot = order_snapshot(order)
    return ExtensionOrderOut(
        id=snapshot.id,
        product=snapshot.product,
        quote=snapshot.quote,
        payment_id=order.payment_id,
        payment_state=str(order.payment_state),
        fulfillment_state=str(order.fulfillment_state),
        data=JSON_OBJECT.validate_json(str(order.result_json or "{}")),
    )


async def extension_orders_route(request: web.Request) -> web.Response:
    async with user_context(request) as context:
        query = select(ExtensionOrder).where(ExtensionOrder.user_id == context.user_id)
        if request.query.get("owner"):
            query = query.where(ExtensionOrder.owner == request.query["owner"])
        cursor = request.query.get("cursor", "")
        if cursor:
            query = query.where(ExtensionOrder.id < cursor)
        orders = (
            await context.session.scalars(query.order_by(ExtensionOrder.id.desc()).limit(100))
        ).all()
        payload = ExtensionOrdersOut(orders=[serialize_order(item) for item in orders])
        return json_response({"ok": True, **payload.model_dump(mode="json")})


async def extension_order_route(request: web.Request) -> web.Response:
    try:
        async with user_context(request) as context:
            order = await context.session.scalar(
                select(ExtensionOrder).where(
                    ExtensionOrder.id == request.query.get("order_id", ""),
                    ExtensionOrder.user_id == context.user_id,
                )
            )
            if order is None:
                raise ExtensionError("extension_order_not_found", 404)
            result = serialize_order(order)
            if request.query.get("refresh") == "true" and order.fulfillment_state == "fulfilled":
                provider = product_provider(result.product)
                if provider.status is not None:
                    async with asyncio.timeout(15):
                        result.data = await provider.status(context, order_snapshot(order))
            return json_response({"ok": True, "order": result.model_dump(mode="json")})
    except ExtensionError as exc:
        return json_response({"ok": False, "error": exc.code}, status=exc.status)


async def extension_order_create_route(request: web.Request) -> web.Response:
    payload = await parse_body_or_400(request, ExtensionOrderCreate)
    if isinstance(payload, web.Response):
        return payload
    try:
        async with user_context(request) as context:
            limited = await _enforce_webapp_rate_limit(
                request, user_id=context.user_id, action="extension-orders"
            )
            if limited is not None:
                return limited
            async with asyncio.timeout(15):
                order = await create_order(
                    context,
                    product=payload.product,
                    options=payload.options,
                    idempotency_key=payload.idempotency_key,
                )
            await context.session.commit()
            return json_response(
                {"ok": True, "order": serialize_order(order).model_dump(mode="json")}
            )
    except ExtensionError as exc:
        return json_response({"ok": False, "error": exc.code}, status=exc.status)


async def extension_payment_methods_route(request: web.Request) -> web.Response:
    try:
        async with user_context(request) as context:
            order = await lock_order(
                context.session, request.query.get("order_id", ""), context.user_id
            )
            quote = order_snapshot(order).quote
            methods = []
            if order.payment_state == "pending" and order.payment_id is None:
                product_provider(f"{order.owner}:{order.product}")
                if utc(quote.expires_at) <= datetime.now(UTC):
                    raise ExtensionError("extension_quote_expired")
                user = await user_dal.get_user_by_id(context.session, context.user_id)
                settings = get_settings(request)
                is_admin = bool(
                    user and user.telegram_id and int(user.telegram_id) in settings.ADMIN_IDS
                )
                methods = [
                    ExtensionPaymentMethodOut(id=spec.id, label=spec.webapp_label or spec.label)
                    for spec in payment_methods(
                        settings,
                        request.app,
                        is_admin=is_admin,
                        quote=quote,
                        order_id=str(order.id),
                    )
                ]
                if balance_available(request, quote):
                    methods.insert(
                        0,
                        ExtensionPaymentMethodOut(
                            id="user_balance", label="Balance", label_key="wa_balance_title"
                        ),
                    )
                if quote.amount_minor == 0:
                    methods = [
                        ExtensionPaymentMethodOut(
                            id="free", label="Continue", label_key="wa_continue"
                        )
                    ]
            payload = ExtensionPaymentMethodsOut(methods=methods)
            return json_response({"ok": True, **payload.model_dump(mode="json")})
    except ExtensionError as exc:
        return json_response({"ok": False, "error": exc.code}, status=exc.status)


async def extension_checkout_route(request: web.Request) -> web.Response:
    payload = await parse_body_or_400(request, ExtensionCheckout)
    if isinstance(payload, web.Response):
        return payload
    try:
        async with user_context(request) as context:
            limited = await _enforce_webapp_rate_limit(
                request, user_id=context.user_id, action="extension-checkout"
            )
            if limited is not None:
                return limited
            user = await user_dal.lock_user_by_id(context.session, context.user_id)
            if user is None or user.is_banned:
                raise ExtensionError("access_denied", 403)
            order = await lock_order(context.session, payload.order_id, context.user_id)
            snapshot = order_snapshot(order)
            payment_payload = {}
            if order.payment_id is not None:
                payment = await payment_dal.get_payment_by_db_id(
                    context.session, int(order.payment_id)
                )
                if payment is not None:
                    payment_payload = {
                        "payment_id": int(payment.payment_id),
                        "status": str(payment.status),
                        "payment_url": payment.provider_payment_url,
                    }
            elif order.payment_state == "pending":
                product_provider(snapshot.product)
                if utc(snapshot.quote.expires_at) <= datetime.now(UTC):
                    raise ExtensionError("extension_quote_expired")
                settings = get_settings(request)
                quote = snapshot.quote
                mode = f"extension|{order.id}"
                price = float(
                    minor_to_decimal_string(
                        quote.amount_minor, scale=currency_scale(quote.currency)
                    )
                )
                if payload.method == "user_balance" or quote.amount_minor == 0:
                    if quote.amount_minor and not balance_available(request, quote):
                        raise ExtensionError("payment_unavailable", 400)
                    await ledger_change(
                        context.session,
                        user_id=context.user_id,
                        amount_minor=-quote.amount_minor,
                        currency=quote.currency,
                        kind="extension_purchase",
                        reference=str(order.id),
                        owner=str(order.owner),
                    )
                    payment = await payment_dal.create_payment_record(
                        context.session,
                        {
                            "user_id": context.user_id,
                            "amount": price,
                            "currency": quote.currency,
                            "description": quote.title,
                            "provider": "user_balance",
                            "funding_source": "user_balance",
                            "status": "pending",
                            "sale_mode": mode,
                        },
                    )
                    await accept_payment(context.session, payment)
                    await payment_dal.update_payment_status_by_db_id(
                        context.session, int(payment.payment_id), "succeeded"
                    )
                    await context.session.commit()
                    payment_payload = {"payment_id": int(payment.payment_id), "status": "succeeded"}
                else:
                    spec = get_provider_spec(payload.method)
                    is_admin = bool(
                        user.telegram_id and int(user.telegram_id) in set(settings.ADMIN_IDS or [])
                    )
                    available = payment_methods(
                        settings,
                        request.app,
                        is_admin=is_admin,
                        quote=quote,
                        order_id=str(order.id),
                    )
                    if spec is None or spec.create_webapp_payment is None or spec not in available:
                        raise ExtensionError("payment_unavailable", 400)
                    response = await spec.create_webapp_payment(
                        WebAppPaymentContext(
                            request=request,
                            session=context.session,
                            user_id=context.user_id,
                            method=payload.method,
                            months=1,
                            price=price,
                            stars_price=quote.amount_minor if quote.currency == "XTR" else None,
                            currency=quote.currency,
                            description=quote.title,
                            sale_mode=mode,
                            payer_email=payload.payer_email,
                            payer_phone=payload.payer_phone,
                        )
                    )
                    if not isinstance(response, web.Response) or not isinstance(
                        response.body, bytes
                    ):
                        raise ExtensionError("invalid_payment_response", 502)
                    if response.status >= 400:
                        return response
                    payment_payload = JSON_OBJECT.validate_python(json.loads(response.body))
                    await context.session.refresh(order)
                    await context.session.commit()
            result = ExtensionCheckoutOut(order=serialize_order(order), payment=payment_payload)
            return json_response({"ok": True, **result.model_dump(mode="json")})
    except ExtensionError as exc:
        return json_response({"ok": False, "error": exc.code}, status=exc.status)


EXTENSION_ORDER_ROUTE_CONTRACTS = {
    "extension_payment_methods_route": user_contract(
        response_schema=ok_envelope_for(ExtensionPaymentMethodsOut),
        models=(ExtensionPaymentMethodsOut,),
    ),
    "extension_order_route": user_contract(
        response_schema=ok_envelope_for(ExtensionOrderOut, key="order"),
        models=(ExtensionOrderOut,),
    ),
    "extension_orders_route": user_contract(
        response_schema=ok_envelope_for(ExtensionOrdersOut), models=(ExtensionOrdersOut,)
    ),
    "extension_order_create_route": user_contract(
        request_model=ExtensionOrderCreate,
        response_schema=ok_envelope_for(ExtensionOrderOut, key="order"),
        models=(ExtensionOrderOut,),
    ),
    "extension_checkout_route": user_contract(
        request_model=ExtensionCheckout,
        response_schema=ok_envelope_for(ExtensionCheckoutOut),
        models=(ExtensionCheckoutOut,),
    ),
}
