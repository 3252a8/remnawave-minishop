from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from config.subscription_periods import legacy_months_to_days
from db.models import (
    Payment,
    TributeEntitlement,
    TributeProductPurchase,
    TributeShopWebhookEvent,
    TributeWebhookEvent,
)


async def ensure_webhook_event(
    session: AsyncSession,
    event_data: dict[str, Any],
) -> tuple[TributeWebhookEvent, bool]:
    """Atomically claim one durable row for a semantic Tribute event."""

    payload = dict(event_data)
    fingerprint = str(payload.get("fingerprint") or "").strip().lower()
    if len(fingerprint) != 64:
        raise ValueError("A 64-character Tribute event fingerprint is required.")
    payload["fingerprint"] = fingerprint

    statement = (
        pg_insert(TributeWebhookEvent)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=[TributeWebhookEvent.fingerprint])
        .returning(TributeWebhookEvent.event_id)
    )
    created = (await session.execute(statement)).scalar_one_or_none() is not None
    event = (
        await session.execute(
            select(TributeWebhookEvent)
            .where(TributeWebhookEvent.fingerprint == fingerprint)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return event, created


async def get_entitlement_for_update(
    session: AsyncSession,
    *,
    tribute_subscription_id: int,
    trb_user_id: str,
) -> TributeEntitlement | None:
    result = await session.execute(
        select(TributeEntitlement)
        .where(
            TributeEntitlement.tribute_subscription_id == int(tribute_subscription_id),
            TributeEntitlement.trb_user_id == str(trb_user_id),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def create_entitlement(
    session: AsyncSession,
    entitlement_data: dict[str, Any],
) -> TributeEntitlement:
    entitlement_data = dict(entitlement_data)
    if entitlement_data.get("duration_months"):
        entitlement_data.setdefault(
            "duration_days", legacy_months_to_days(entitlement_data["duration_months"])
        )
        entitlement_data.setdefault("period_semantics", "provider_managed")
    entitlement = TributeEntitlement(**entitlement_data)
    session.add(entitlement)
    await session.flush()
    await session.refresh(entitlement)
    return entitlement


async def ensure_product_purchase(
    session: AsyncSession,
    purchase_data: dict[str, Any],
) -> tuple[TributeProductPurchase, bool]:
    """Atomically lock one lifecycle row per Tribute purchase_id."""

    payload = dict(purchase_data)
    purchase_id = int(payload.get("tribute_purchase_id") or 0)
    if purchase_id <= 0:
        raise ValueError("A positive Tribute purchase ID is required.")
    payload["tribute_purchase_id"] = purchase_id

    statement = (
        pg_insert(TributeProductPurchase)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=[TributeProductPurchase.tribute_purchase_id])
        .returning(TributeProductPurchase.purchase_row_id)
    )
    created = (await session.execute(statement)).scalar_one_or_none() is not None
    purchase = (
        await session.execute(
            select(TributeProductPurchase)
            .where(TributeProductPurchase.tribute_purchase_id == purchase_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return purchase, created


async def get_product_purchase_for_update(
    session: AsyncSession,
    purchase_id: int,
) -> TributeProductPurchase | None:
    result = await session.execute(
        select(TributeProductPurchase)
        .where(TributeProductPurchase.tribute_purchase_id == int(purchase_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def ensure_shop_webhook_event(
    session: AsyncSession,
    event_data: dict[str, Any],
) -> tuple[TributeShopWebhookEvent, bool]:
    """Atomically lock one lifecycle row per semantic Shop event."""

    payload = dict(event_data)
    fingerprint = str(payload.get("fingerprint") or "").strip().lower()
    if len(fingerprint) != 64:
        raise ValueError("A 64-character Tribute Shop event fingerprint is required.")
    payload["fingerprint"] = fingerprint

    statement = (
        pg_insert(TributeShopWebhookEvent)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=[TributeShopWebhookEvent.fingerprint])
        .returning(TributeShopWebhookEvent.event_id)
    )
    created = (await session.execute(statement)).scalar_one_or_none() is not None
    event = (
        await session.execute(
            select(TributeShopWebhookEvent)
            .where(TributeShopWebhookEvent.fingerprint == fingerprint)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return event, created


async def get_shop_recurring_state(
    session: AsyncSession,
    order_uuid: str,
) -> str | None:
    """Return the latest state-changing recurring event in provider time order."""

    result = await session.execute(
        select(
            TributeShopWebhookEvent.event_name,
            TributeShopWebhookEvent.status_reason,
        )
        .where(
            TributeShopWebhookEvent.order_uuid == str(order_uuid),
            TributeShopWebhookEvent.status.in_(("processing", "processed")),
            TributeShopWebhookEvent.event_name.in_(
                (
                    "shop_order",
                    "shop_order_charge_success",
                    "shop_order_charge_failed",
                    "shop_order_cancelled",
                )
            ),
        )
        .order_by(
            TributeShopWebhookEvent.event_created_at.desc(),
            TributeShopWebhookEvent.event_id.desc(),
        )
    )
    for event_name, status_reason in result.all():
        if event_name in {"shop_order", "shop_order_charge_success"}:
            return "active"
        if event_name == "shop_order_cancelled":
            return "inactive"
        if event_name == "shop_order_charge_failed" and status_reason == "charge_retry_3":
            return "inactive"
    return None


async def get_other_active_shop_order_uuid(
    session: AsyncSession,
    *,
    user_id: int,
    exclude_order_uuid: str | None = None,
) -> str | None:
    """Return another provider-confirmed active Shop recurrence for one user.

    A succeeded payment alone is not enough: cancellation and terminal retry
    webhooks do not rewrite it.  Rank only state-changing webhook receipts and
    join their newest state to the durable originating payment.
    """

    state_changing_event = or_(
        TributeShopWebhookEvent.event_name.in_(
            (
                "shop_order",
                "shop_order_charge_success",
                "shop_order_cancelled",
            )
        ),
        and_(
            TributeShopWebhookEvent.event_name == "shop_order_charge_failed",
            TributeShopWebhookEvent.status_reason == "charge_retry_3",
        ),
    )
    ranked_states = (
        select(
            TributeShopWebhookEvent.order_uuid.label("order_uuid"),
            TributeShopWebhookEvent.event_name.label("event_name"),
            func.row_number()
            .over(
                partition_by=TributeShopWebhookEvent.order_uuid,
                order_by=(
                    TributeShopWebhookEvent.event_created_at.desc(),
                    TributeShopWebhookEvent.event_id.desc(),
                ),
            )
            .label("state_rank"),
        )
        .where(
            TributeShopWebhookEvent.status.in_(("processing", "processed")),
            state_changing_event,
        )
        .subquery()
    )
    conditions = [
        Payment.user_id == int(user_id),
        func.lower(Payment.provider) == "tribute",
        func.lower(Payment.status).in_(("succeeded", "succeeded_pending_finalization")),
        or_(
            Payment.sale_mode == "subscription",
            Payment.sale_mode.like("subscription@%"),
        ),
        Payment.provider_payment_id == ranked_states.c.order_uuid,
        ranked_states.c.state_rank == 1,
        ranked_states.c.event_name.in_(("shop_order", "shop_order_charge_success")),
    ]
    if exclude_order_uuid:
        conditions.append(Payment.provider_payment_id != str(exclude_order_uuid))
    result = await session.execute(
        select(Payment.provider_payment_id)
        .join(
            ranked_states,
            Payment.provider_payment_id == ranked_states.c.order_uuid,
        )
        .where(*conditions)
        .order_by(Payment.payment_id.desc())
        .limit(1)
    )
    order_uuid = result.scalar_one_or_none()
    return str(order_uuid) if order_uuid else None


async def get_other_active_creator_subscription_id(
    session: AsyncSession,
    *,
    user_id: int,
    exclude_subscription_id: int | None = None,
) -> int | None:
    """Return another Creator subscription still recurrent at Tribute.

    Keyed on the local account, like every other duplicate-recurrence check:
    the Telegram ID is Tribute's identity for a subscriber, not this
    deployment's, and mixing the two made Creator and Shop compare different
    things and never see each other's recurrence.
    """

    conditions = [
        TributeEntitlement.user_id == int(user_id),
        TributeEntitlement.status == "active",
    ]
    if exclude_subscription_id is not None:
        conditions.append(
            TributeEntitlement.tribute_subscription_id != int(exclude_subscription_id)
        )
    result = await session.execute(
        select(TributeEntitlement.tribute_subscription_id)
        .where(*conditions)
        .order_by(
            TributeEntitlement.last_event_created_at.desc(),
            TributeEntitlement.entitlement_id.desc(),
        )
        .limit(1)
    )
    subscription_id = result.scalar_one_or_none()
    return int(subscription_id) if subscription_id is not None else None


async def get_shop_order_quarantine_reason(
    session: AsyncSession,
    order_uuid: str,
) -> str | None:
    """Return the durable initial quarantine reason for a Shop order."""

    result = await session.execute(
        select(TributeShopWebhookEvent.status_reason)
        .where(
            TributeShopWebhookEvent.order_uuid == str(order_uuid),
            TributeShopWebhookEvent.event_name == "shop_order",
            TributeShopWebhookEvent.status == "quarantined",
        )
        .order_by(
            TributeShopWebhookEvent.event_created_at.desc(),
            TributeShopWebhookEvent.event_id.desc(),
        )
        .limit(1)
    )
    reason = result.scalar_one_or_none()
    return str(reason) if reason else None


async def get_shop_success_tombstone_reason(
    session: AsyncSession,
    *,
    order_uuid: str,
    success_created_at: datetime,
    initial_success: bool,
) -> str | None:
    """Return a later provider event that definitively supersedes this success.

    A completed refund is unscoped at the order level in Minishop's webhook
    state. It can safely tombstone the initial success, but not an arbitrary
    recurring success: Tribute explicitly allows refunding an older charge
    without cancelling a newer recurrence. For recurring charges only
    ``last_charge_refunded`` is a definitive global tombstone.
    """

    tombstones = [
        and_(
            TributeShopWebhookEvent.event_name == "shop_order_cancelled",
            TributeShopWebhookEvent.status_reason == "last_charge_refunded",
        )
    ]
    if initial_success:
        tombstones.extend(
            (
                and_(
                    TributeShopWebhookEvent.event_name == "shop_order_refunded",
                    TributeShopWebhookEvent.status_reason == "manual_entitlement_review",
                ),
                TributeShopWebhookEvent.event_name == "shop_order_payment_failed",
            )
        )

    result = await session.execute(
        select(
            TributeShopWebhookEvent.event_name,
            TributeShopWebhookEvent.status_reason,
        )
        .where(
            TributeShopWebhookEvent.order_uuid == str(order_uuid),
            TributeShopWebhookEvent.status == "processed",
            TributeShopWebhookEvent.event_created_at >= success_created_at,
            or_(*tombstones),
        )
        .order_by(
            TributeShopWebhookEvent.event_created_at.desc(),
            TributeShopWebhookEvent.event_id.desc(),
        )
        .limit(1)
    )
    row = result.one_or_none()
    if row is None:
        return None
    event_name, status_reason = row
    if event_name == "shop_order_refunded":
        return "completed_refund"
    if event_name == "shop_order_payment_failed":
        return "payment_failed"
    return str(status_reason) if status_reason else "last_charge_refunded"


def mark_event_processed(
    event: TributeWebhookEvent | TributeShopWebhookEvent,
    *,
    status: str = "processed",
    reason: str | None = None,
    payment_id: int | None = None,
) -> None:
    event.status = str(status)
    event.status_reason = str(reason)[:128] if reason else None
    if payment_id is not None:
        event.payment_id = int(payment_id)
    event.processed_at = datetime.now(UTC)
