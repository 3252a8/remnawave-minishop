"""Frozen external orders using Core payment adapters and accounting."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.partner_common import amount_to_minor, currency_scale
from db.dal import user_balance_dal, user_dal
from db.extension_models import ExtensionOperation, ExtensionOrder
from db.models import Payment

from .contracts import ExtensionError, OrderSnapshot, ProductProvider, ProductQuote, UserContext
from .jobs import enqueue_internal, json_object, utc
from .registry import get_registry, split_key


def product_provider(key: str) -> ProductProvider:
    owner, name = split_key(key)
    entry = get_registry().require(owner)
    provider = next((item for item in entry.contributions.products if item.id == name), None)
    if provider is None:
        raise ExtensionError("extension_product_unavailable", 503)
    return provider


def order_snapshot(order: ExtensionOrder) -> OrderSnapshot:
    return OrderSnapshot(
        id=str(order.id),
        user_id=int(order.user_id),
        product=f"{order.owner}:{order.product}",
        quote=ProductQuote.model_validate_json(str(order.quote_json)),
        reference=order.reference,
    )


async def create_order(
    context: UserContext, *, product: str, options: dict[str, JsonValue], idempotency_key: str
) -> ExtensionOrder:
    if not 1 <= len(idempotency_key) <= 128:
        raise ExtensionError("invalid_extension_idempotency_key", 400)
    user = await user_dal.lock_user_by_id(context.session, context.user_id)
    if user is None or user.is_banned:
        raise ExtensionError("access_denied", 403)
    owner, name = split_key(product)
    request_json = json_object({"product": product, "options": options})
    existing = await context.session.scalar(
        select(ExtensionOrder).where(
            ExtensionOrder.user_id == context.user_id,
            ExtensionOrder.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_json != request_json:
            raise ExtensionError("extension_idempotency_conflict")
        return existing
    provider = product_provider(product)
    quote = ProductQuote.model_validate(await provider.quote(context, options))
    now = datetime.now(UTC)
    if not now < utc(quote.expires_at) <= now + timedelta(days=1):
        raise ExtensionError("extension_quote_expired")
    if quote.version not in provider.terms_versions:
        raise ExtensionError("extension_terms_incompatible")
    json_object(quote.terms)
    order = ExtensionOrder(
        id=uuid.uuid4().hex,
        owner=owner,
        product=name,
        user_id=context.user_id,
        idempotency_key=idempotency_key,
        request_json=request_json,
        quote_json=quote.model_dump_json(),
        payment_state="pending",
        fulfillment_state="pending",
        created_at=now,
        updated_at=now,
    )
    context.session.add(order)
    await context.session.flush()
    return order


async def lock_order(
    session: AsyncSession, order_id: str, user_id: int | None = None
) -> ExtensionOrder:
    query = select(ExtensionOrder).where(ExtensionOrder.id == order_id)
    if user_id is not None:
        query = query.where(ExtensionOrder.user_id == user_id)
    order = await session.scalar(query.with_for_update().execution_options(populate_existing=True))
    if order is None:
        raise ExtensionError("extension_order_not_found", 404)
    return order


async def accept_payment(session: AsyncSession, payment: Payment) -> ExtensionOrder:
    """Called only after a provider verified payment, while the payment/user are locked."""
    mode = str(payment.sale_mode or "")
    if not mode.startswith("extension|"):
        raise ExtensionError("invalid_extension_payment", 400)
    order = await lock_order(session, mode.removeprefix("extension|"), int(payment.user_id))
    quote = order_snapshot(order).quote
    if (
        order.payment_id != payment.payment_id
        or str(payment.currency).upper() != quote.currency
        or amount_to_minor(payment.amount, scale=currency_scale(quote.currency))
        != quote.amount_minor
    ):
        raise ExtensionError("extension_payment_mismatch")
    if order.payment_state == "paid":
        return order
    if order.payment_state != "pending":
        raise ExtensionError("extension_order_not_payable")
    # Honor a paid invoice even if its quote expired or its plugin was disabled meanwhile.
    order.payment_state = "paid"
    order.updated_at = datetime.now(UTC)
    await enqueue_internal(
        session,
        owner=str(order.owner),
        kind="_fulfill",
        idempotency_key=str(order.id),
        user_id=int(order.user_id),
        payload={"order_id": str(order.id)},
    )
    await session.flush()
    return order


async def ledger_change(
    session: AsyncSession,
    *,
    user_id: int,
    amount_minor: int,
    currency: str,
    kind: str,
    reference: str,
    owner: str,
) -> None:
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None:
        raise ExtensionError("user_not_found", 404)
    key = f"{kind}:{reference}"
    existing = await user_balance_dal.get_ledger_entry_by_key(session, key)
    if existing is not None:
        if (
            existing.user_id != user_id
            or existing.amount_minor != amount_minor
            or existing.currency != currency
        ):
            raise ExtensionError("extension_ledger_conflict")
        return
    balance = await user_balance_dal.balance_minor(session, user_id, currency)
    if balance + amount_minor < 0:
        raise ExtensionError("insufficient_user_balance")
    await user_balance_dal.create_ledger_entry(
        session,
        user_id=user_id,
        currency=currency,
        currency_scale=currency_scale(currency),
        amount_minor=amount_minor,
        kind=kind,
        state="posted",
        reference_type="extension",
        reference_id=reference,
        idempotency_key=key,
        reason=f"Extension {owner}",
        metadata_json=json_object({"owner": owner}),
        posted_at=datetime.now(UTC),
    )


async def request_refund(
    session: AsyncSession, *, order_id: str, user_id: int, to_balance: bool = True
) -> ExtensionOrder:
    """Privileged SDK command: caller must authorize refund policy, never expose blindly."""
    await user_dal.lock_user_by_id(session, user_id)
    order = await lock_order(session, order_id, user_id)
    if order.payment_state in {"refunding", "refunded"}:
        operation = await session.scalar(
            select(ExtensionOperation).where(
                ExtensionOperation.owner == order.owner,
                ExtensionOperation.kind == "_revoke",
                ExtensionOperation.idempotency_key == order.id,
            )
        )
        expected = json_object({"order_id": order_id, "to_balance": to_balance})
        if operation is not None and operation.payload_json != expected:
            raise ExtensionError("extension_idempotency_conflict")
        return order
    if order.payment_state != "paid":
        raise ExtensionError("extension_order_not_paid")
    operations = (
        await session.scalars(
            select(ExtensionOperation)
            .where(
                ExtensionOperation.owner == order.owner,
                ExtensionOperation.kind == "_fulfill",
                ExtensionOperation.idempotency_key == order.id,
            )
            .with_for_update()
        )
    ).all()
    for operation in operations:
        if (
            operation.state == "running"
            and operation.lease_until
            and utc(operation.lease_until) > datetime.now(UTC)
        ):
            raise ExtensionError("extension_fulfillment_in_progress")
        if operation.state != "succeeded":
            operation.state = "cancelled"
            operation.lease_token = None
    order.payment_state = "refunding"
    order.fulfillment_state = "revoking"
    await enqueue_internal(
        session,
        owner=str(order.owner),
        kind="_revoke",
        idempotency_key=order_id,
        user_id=user_id,
        payload={"order_id": order_id, "to_balance": to_balance},
    )
    await session.flush()
    return order
