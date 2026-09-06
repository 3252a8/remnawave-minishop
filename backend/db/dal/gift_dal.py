from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, case, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from db.gift_models import SubscriptionGift
from db.models import Payment, User


async def issue(session: AsyncSession, payment: Payment) -> SubscriptionGift:
    # The caller holds the payment row lock, including for provider replays.
    existing = await by_payment(session, int(payment.payment_id))
    if existing is not None:
        return existing
    gift = SubscriptionGift(
        payment_id=payment.payment_id,
        purchaser_id=payment.user_id,
        token=secrets.token_urlsafe(32),
        status="ready",
    )
    session.add(gift)
    await session.flush()
    return gift


async def by_payment(
    session: AsyncSession, payment_id: int, *, lock: bool = False
) -> SubscriptionGift | None:
    stmt = select(SubscriptionGift).where(SubscriptionGift.payment_id == payment_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def by_token(session: AsyncSession, token: str) -> SubscriptionGift | None:
    return (
        await session.execute(select(SubscriptionGift).where(SubscriptionGift.token == token))
    ).scalar_one_or_none()


async def activating_for_user(session: AsyncSession, user_id: int) -> SubscriptionGift | None:
    return (
        await session.execute(
            select(SubscriptionGift)
            .where(
                SubscriptionGift.recipient_id == user_id, SubscriptionGift.status == "activating"
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def purchased(session: AsyncSession, user_id: int) -> list[tuple[SubscriptionGift, Payment]]:
    rows = await session.execute(
        select(SubscriptionGift, Payment)
        .join(Payment, Payment.payment_id == SubscriptionGift.payment_id)
        .where(SubscriptionGift.purchaser_id == user_id)
        .order_by(SubscriptionGift.gift_id.desc())
        .limit(100)
    )
    return [(row[0], row[1]) for row in rows]


async def merge_owner(session: AsyncSession, source_id: int, target_id: int) -> None:
    for column in (SubscriptionGift.purchaser_id, SubscriptionGift.recipient_id):
        await session.execute(
            update(SubscriptionGift).where(column == source_id).values({column.key: target_id})
        )


async def pending_delivery(session: AsyncSession) -> list[int]:
    return list(
        (
            await session.scalars(
                select(SubscriptionGift.payment_id)
                .where(
                    SubscriptionGift.status == "ready",
                    SubscriptionGift.recipient_email.isnot(None),
                    SubscriptionGift.delivery_status.in_(("pending", "failed")),
                    SubscriptionGift.delivery_attempts < 5,
                    or_(
                        SubscriptionGift.delivery_attempted_at.is_(None),
                        SubscriptionGift.delivery_attempted_at
                        < datetime.now(UTC) - timedelta(minutes=5),
                    ),
                )
                .order_by(SubscriptionGift.gift_id)
                .limit(20)
            )
        ).all()
    )


async def pending_activation(session: AsyncSession) -> list[tuple[str, int]]:
    rows = await session.execute(
        select(SubscriptionGift.token, SubscriptionGift.recipient_id)
        .where(
            SubscriptionGift.status == "activating",
            SubscriptionGift.recipient_id.isnot(None),
            or_(
                SubscriptionGift.activation_attempted_at.is_(None),
                SubscriptionGift.activation_attempted_at < datetime.now(UTC) - timedelta(minutes=1),
            ),
        )
        .order_by(SubscriptionGift.gift_id)
        .limit(20)
    )
    return [(str(row[0]), int(row[1])) for row in rows]


async def admin_list(
    session: AsyncSession,
    *,
    status: str,
    query: str,
    page: int,
    page_size: int,
    sort: str = "date_desc",
    source: str = "",
) -> tuple[list[tuple[SubscriptionGift, Payment, User | None, User | None]], int]:
    purchaser = aliased(User)
    recipient = aliased(User)
    stmt = (
        select(SubscriptionGift, Payment, purchaser, recipient)
        .join(Payment, Payment.payment_id == SubscriptionGift.payment_id)
        .outerjoin(purchaser, purchaser.user_id == SubscriptionGift.purchaser_id)
        .outerjoin(recipient, recipient.user_id == SubscriptionGift.recipient_id)
    )
    if source == "admin":
        stmt = stmt.where(Payment.provider == "admin_gift")
    elif source == "purchase":
        stmt = stmt.where(Payment.provider != "admin_gift")
    if status:
        if status == "revoked":
            stmt = stmt.where(
                or_(SubscriptionGift.status == "revoked", Payment.status != "succeeded")
            )
        else:
            stmt = stmt.where(SubscriptionGift.status == status, Payment.status == "succeeded")
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(
            or_(
                cast(SubscriptionGift.gift_id, String).ilike(pattern),
                cast(SubscriptionGift.purchaser_id, String).ilike(pattern),
                cast(SubscriptionGift.recipient_id, String).ilike(pattern),
                purchaser.email.ilike(pattern),
                purchaser.username.ilike(pattern),
                recipient.email.ilike(pattern),
                recipient.username.ilike(pattern),
                SubscriptionGift.recipient_email.ilike(pattern),
                Payment.tariff_key.ilike(pattern),
            )
        )
    total = int((await session.scalar(select(func.count()).select_from(stmt.subquery()))) or 0)
    columns = {
        "id": SubscriptionGift.gift_id,
        "buyer": func.lower(
            func.coalesce(purchaser.username, purchaser.email, purchaser.first_name, "")
        ),
        "recipient": func.lower(
            func.coalesce(recipient.username, recipient.email, recipient.first_name, "")
        ),
        "tariff": Payment.tariff_key,
        "amount": func.coalesce(Payment.checkout_total_amount, Payment.amount),
        "status": case((Payment.status != "succeeded", "revoked"), else_=SubscriptionGift.status),
        "date": SubscriptionGift.created_at,
        "provider": Payment.provider,
    }
    key, _, direction = sort.rpartition("_")
    column = columns.get(key, SubscriptionGift.created_at)
    ordering = column.asc().nulls_last() if direction == "asc" else column.desc().nulls_last()
    rows = await session.execute(
        stmt.order_by(ordering, SubscriptionGift.gift_id.desc())
        .offset(page * page_size)
        .limit(page_size)
    )
    return [(row[0], row[1], row[2], row[3]) for row in rows], total
