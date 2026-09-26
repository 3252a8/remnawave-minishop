"""Database-only integration for canonical payment identity and durable notifications."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.extension_models import ExtensionOperation, ExtensionOrder
from db.models import Payment


async def bind_payment(session: AsyncSession, payment: Payment) -> None:
    mode = str(payment.sale_mode or "")
    if not mode.startswith("extension|"):
        return
    order = await session.scalar(
        select(ExtensionOrder)
        .where(
            ExtensionOrder.id == mode.removeprefix("extension|"),
            ExtensionOrder.user_id == payment.user_id,
        )
        .with_for_update()
    )
    if order is None or order.payment_state != "pending":
        raise ValueError("extension_order_not_payable")
    if order.payment_id is not None and order.payment_id != payment.payment_id:
        raise ValueError("extension_order_already_invoiced")
    order.payment_id = payment.payment_id
    await session.flush()


_payment_subscribers: tuple[tuple[str, str, int], ...] = ()


def configure_payment_subscribers(subscribers: tuple[tuple[str, str, int], ...]) -> None:
    global _payment_subscribers
    _payment_subscribers = subscribers


async def record_payment_succeeded(session: AsyncSession, payment: Payment) -> None:
    """Capture recipients at commit time, including when workers are offline."""
    if not _payment_subscribers:
        return
    event_id = str(payment.payment_id)
    key = hashlib.sha256(f"payment.succeeded:{event_id}".encode()).hexdigest()
    now = datetime.now(UTC)
    payload = {
        "event": "payment.succeeded",
        "event_id": event_id,
        "payload": {
            "user_id": int(payment.user_id),
            "payment_db_id": int(payment.payment_id),
            "amount": float(payment.amount),
            "currency": str(payment.currency),
            "provider": str(payment.provider),
            "funding_source": str(payment.funding_source or "external"),
            "sale_mode": str(payment.sale_mode or ""),
        },
    }
    for owner, job, attempts in _payment_subscribers:
        existing = await session.scalar(
            select(ExtensionOperation.id).where(
                ExtensionOperation.owner == owner,
                ExtensionOperation.kind == job,
                ExtensionOperation.idempotency_key == key,
            )
        )
        if existing is not None:
            continue
        session.add(
            ExtensionOperation(
                id=uuid.uuid4().hex,
                owner=owner,
                kind=job,
                idempotency_key=key,
                user_id=payment.user_id,
                payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                state="queued",
                attempts=0,
                max_attempts=attempts,
                not_before=now,
                created_at=now,
                updated_at=now,
            )
        )
    if _payment_subscribers:
        await session.flush()
