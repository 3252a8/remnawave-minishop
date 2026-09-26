"""Core-owned external fulfillment and entitlement synchronization handlers."""

from datetime import UTC, datetime

from pydantic import JsonValue
from sqlalchemy import select

from db.dal import user_dal
from db.extension_models import ExtensionOperation
from db.models import Payment

from .commerce import ledger_change, lock_order, order_snapshot, product_provider
from .contracts import ExtensionError, FulfillmentResult, OperationContext
from .jobs import JSON_OBJECT, json_object


async def execute_operation(
    operation: OperationContext, kind: str, payload: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    if kind == "_backup_upload":
        from .backups import upload_archive

        await upload_archive(operation, payload)
        return {}
    if operation.user_id is None:
        raise ExtensionError("extension_user_missing", 400)
    if kind == "_reward":
        async with operation.runtime.require_session_factory()() as session:
            user = await user_dal.lock_user_by_id(session, operation.user_id)
            if user is None or user.is_banned:
                raise ExtensionError("access_denied", 403)
            row = await session.get(ExtensionOperation, operation.operation_id)
            if row is None or not row.result_json:
                raise ExtensionError("extension_reward_not_applied", 400)
            if row.lease_token != operation.lease_token:
                raise ExtensionError("extension_lease_changed", 503)
            reward_result = JSON_OBJECT.validate_json(str(row.result_json))
            operation.assert_current()
            subscription_service = operation.runtime.require_subscription_service()
            if not await subscription_service.sync_main_traffic_limit_to_panel(
                session, operation.user_id
            ):
                raise ExtensionError("extension_panel_sync_failed", 502)
            await session.commit()
            return reward_result
    order_id = str(payload["order_id"])
    async with operation.runtime.require_session_factory()() as session:
        user = await user_dal.lock_user_by_id(session, operation.user_id)
        if user is None or (user.is_banned and kind == "_fulfill"):
            raise ExtensionError("access_denied")
        order = await lock_order(session, order_id, operation.user_id)
        if order.owner != operation.owner:
            raise ExtensionError("extension_owner_mismatch", 403)
        snapshot = order_snapshot(order)
        payment_id = order.payment_id
        provider = product_provider(snapshot.product)
        if snapshot.quote.version not in provider.terms_versions:
            raise ExtensionError("extension_terms_incompatible")
        if kind == "_fulfill":
            if order.payment_state != "paid" or order.fulfillment_state == "fulfilled":
                return JSON_OBJECT.validate_json(str(order.result_json or "{}"))
            order.fulfillment_state = "fulfilling"
        elif kind == "_revoke":
            if order.payment_state == "refunded":
                return {}
            if order.payment_state != "refunding":
                raise ExtensionError("extension_order_not_refunding")
        else:
            raise ExtensionError("extension_operation_unknown", 400)
        await session.commit()
    operation.assert_current()
    result = None
    if kind == "_fulfill":
        result = FulfillmentResult.model_validate(await provider.fulfill(operation, snapshot))
        json_object(result.data)
    else:
        await provider.revoke(operation, snapshot)
    operation.assert_current()
    async with operation.runtime.require_session_factory()() as session:
        # Match webhook lock order: payment -> user -> order -> operation.
        payment = (
            await session.scalar(
                select(Payment).where(Payment.payment_id == payment_id).with_for_update()
            )
            if kind == "_revoke" and payment_id is not None
            else None
        )
        await user_dal.lock_user_by_id(session, operation.user_id)
        order = await lock_order(session, order_id, operation.user_id)
        lease = await session.scalar(
            select(ExtensionOperation)
            .where(ExtensionOperation.id == operation.operation_id)
            .with_for_update()
        )
        if lease is None or lease.lease_token != operation.lease_token:
            raise ExtensionError("extension_lease_changed", 503)
        if result is not None and order.payment_state == "paid":
            order.reference = result.reference
            order.result_json = json_object(result.data)
            order.fulfillment_state = "fulfilled"
        elif kind == "_revoke" and order.payment_state == "refunding":
            if payload.get("to_balance"):
                await ledger_change(
                    session,
                    user_id=operation.user_id,
                    amount_minor=snapshot.quote.amount_minor,
                    currency=snapshot.quote.currency,
                    kind="extension_refund",
                    reference=order_id,
                    owner=operation.owner,
                )
            order.payment_state = "refunded"
            order.fulfillment_state = "revoked"
            if payment is not None:
                payment.status = "refunded"
        order.updated_at = datetime.now(UTC)
        await session.commit()
    return result.data if result is not None else {}
