from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from inspect import isawaitable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_dal, promo_code_dal, subscription_dal
from db.models import (
    FlexibleTrafficLimit,
    HwidDevicePurchase,
    Payment,
    Subscription,
    TariffChange,
    TrafficTopup,
    User,
)

_FINAL_PAYMENT_STATUSES = frozenset({"succeeded", "refunded", "reversed"})
_PENDING_PAYMENT_STATUSES = frozenset(
    {"created", "new", "pending", "waiting_for_capture", "succeeded_pending_finalization"}
)
_SUBSCRIPTION_SNAPSHOT_FIELDS = (
    "panel_user_uuid",
    "panel_subscription_uuid",
    "start_date",
    "end_date",
    "duration_months",
    "is_active",
    "provider",
    "auto_renew_enabled",
    "auto_renew_consent_version",
    "tariff_key",
    "tariff_binding_source",
    "tariff_bound_at",
    "tariff_binding_note",
    "tier_baseline_bytes",
    "topup_balance_bytes",
    "premium_baseline_bytes",
    "premium_topup_balance_bytes",
    "premium_topup_used_bytes",
    "premium_used_bytes",
    "premium_is_limited",
    "premium_period_start_at",
    "premium_unlimited_override",
    "premium_bonus_bytes",
    "regular_bonus_bytes",
    "regular_unlimited_override",
    "period_start_at",
    "is_throttled",
    "effective_monthly_price_rub",
    "hwid_device_limit",
    "extra_hwid_devices",
)
_DATETIME_FIELDS = frozenset(
    {
        "start_date",
        "end_date",
        "tariff_bound_at",
        "premium_period_start_at",
        "period_start_at",
    }
)
_BOOLEAN_FIELDS = frozenset(
    {
        "is_active",
        "auto_renew_enabled",
        "premium_is_limited",
        "premium_unlimited_override",
        "regular_unlimited_override",
        "is_throttled",
    }
)
_INTEGER_FIELDS = frozenset(
    {
        "duration_months",
        "auto_renew_consent_version",
        "tier_baseline_bytes",
        "topup_balance_bytes",
        "premium_baseline_bytes",
        "premium_topup_balance_bytes",
        "premium_topup_used_bytes",
        "premium_used_bytes",
        "premium_bonus_bytes",
        "regular_bonus_bytes",
        "hwid_device_limit",
        "extra_hwid_devices",
    }
)
_DECIMAL_FIELDS = frozenset({"effective_monthly_price_rub"})


class PaymentFulfillmentError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 409,
        details: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or []


def _snapshot_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _subscription_snapshot(subscription: Subscription) -> dict[str, Any]:
    return {
        "subscription_id": int(subscription.subscription_id),
        "user_id": int(subscription.user_id),
        **{
            field: _snapshot_value(getattr(subscription, field, None))
            for field in _SUBSCRIPTION_SNAPSHOT_FIELDS
        },
    }


async def _scalars_all(result: Any) -> list[Any]:
    """Read SQLAlchemy results while preserving lightweight async test adapters."""

    scalars = result.scalars()
    if isawaitable(scalars):
        scalars = await scalars
    values = scalars.all()
    if isawaitable(values):
        values = await values
    return list(values)


async def capture_payment_entitlement_snapshot(
    session: AsyncSession,
    payment: Payment,
) -> dict[str, Any]:
    primary_user = await session.get(User, int(payment.user_id))
    user_ids = {int(payment.user_id)}
    if isinstance(primary_user, User) and primary_user.referred_by_id is not None:
        user_ids.add(int(primary_user.referred_by_id))

    users_result = await session.execute(
        select(User).where(User.user_id.in_(user_ids)).order_by(User.user_id).with_for_update()
    )
    users = await _scalars_all(users_result)
    subscriptions_result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id.in_(user_ids))
        .order_by(Subscription.user_id, Subscription.subscription_id)
        .with_for_update()
    )
    subscriptions = await _scalars_all(subscriptions_result)
    subscriptions_by_user: dict[int, list[dict[str, Any]]] = {user_id: [] for user_id in user_ids}
    for subscription in subscriptions:
        subscriptions_by_user.setdefault(int(subscription.user_id), []).append(
            _subscription_snapshot(subscription)
        )
    users_by_id = {int(user.user_id): user for user in users}
    return {
        "version": 1,
        "users": [
            {
                "user_id": user_id,
                "panel_user_uuid": _snapshot_value(
                    getattr(users_by_id.get(user_id), "panel_user_uuid", None)
                ),
                "subscriptions": subscriptions_by_user.get(user_id, []),
            }
            for user_id in sorted(user_ids)
        ],
    }


def persist_payment_fulfillment(
    payment: Payment,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    payment.fulfillment_source = str(getattr(payment, "fulfillment_source", None) or "provider")
    payment.fulfilled_at = datetime.now(UTC)
    payment.fulfillment_before_snapshot = json.dumps(before, ensure_ascii=False, sort_keys=True)
    payment.fulfillment_after_snapshot = json.dumps(after, ensure_ascii=False, sort_keys=True)


async def payment_action_state(session: AsyncSession, payment: Payment) -> dict[str, Any]:
    status = str(payment.status or "").strip().lower()
    warnings: list[str] = []
    promo_conflict = False
    if payment.promo_code_id:
        activation = await promo_code_dal.get_user_activation_for_promo(
            session,
            int(payment.promo_code_id),
            int(payment.user_id),
        )
        promo_conflict = bool(
            activation is not None
            and int(getattr(activation, "payment_id", 0) or 0) != int(payment.payment_id)
        )
        if promo_conflict:
            warnings.append("promo_used_by_another_payment")
    if not (payment.provider_payment_id or payment.yookassa_payment_id):
        warnings.append("provider_payment_id_missing")
    if status in _PENDING_PAYMENT_STATUSES:
        warnings.append("provider_status_not_failed")
    if not str(payment.sale_mode or "").strip():
        warnings.append("purchase_context_missing")

    can_finalize = status not in _FINAL_PAYMENT_STATUSES and bool(
        str(payment.sale_mode or "").strip()
    )
    reversal_block_reason = None
    if status != "succeeded":
        reversal_block_reason = "payment_not_succeeded"
    elif not payment.fulfillment_before_snapshot or not payment.fulfillment_after_snapshot:
        reversal_block_reason = "fulfillment_snapshot_missing"
    elif payment.reversed_at is not None:
        reversal_block_reason = "payment_already_reversed"
    return {
        "can_manual_finalize": can_finalize,
        "manual_finalize_requires_promo_confirmation": promo_conflict,
        "manual_finalize_warnings": warnings,
        "can_reverse": reversal_block_reason is None,
        "reversal_block_reason": reversal_block_reason,
    }


def _parse_snapshot(raw: str | None) -> dict[str, Any]:
    if not raw:
        raise PaymentFulfillmentError(
            "fulfillment_snapshot_missing",
            "This payment has no reversible fulfillment snapshot.",
        )
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise PaymentFulfillmentError(
            "fulfillment_snapshot_invalid",
            "The stored fulfillment snapshot is invalid.",
        ) from exc
    if not isinstance(parsed, dict) or parsed.get("version") != 1:
        raise PaymentFulfillmentError(
            "fulfillment_snapshot_invalid",
            "The stored fulfillment snapshot version is unsupported.",
        )
    return parsed


def _snapshot_users(snapshot: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in snapshot.get("users", []):
        if isinstance(item, dict) and item.get("user_id") is not None:
            result[int(item["user_id"])] = item
    return result


def _snapshot_subscriptions(user_snapshot: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in user_snapshot.get("subscriptions", []):
        if isinstance(item, dict) and item.get("subscription_id") is not None:
            result[int(item["subscription_id"])] = item
    return result


def _restore_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in _DATETIME_FIELDS:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    if field in _BOOLEAN_FIELDS:
        return bool(value)
    if field in _INTEGER_FIELDS:
        return int(value)
    if field in _DECIMAL_FIELDS:
        return Decimal(str(value))
    return value


async def _delete_payment_effect_rows(session: AsyncSession, payment_id: int) -> None:
    for model in (TrafficTopup, FlexibleTrafficLimit, HwidDevicePurchase, TariffChange):
        await session.execute(delete(model).where(model.payment_id == payment_id))


async def _sync_reversed_user(
    session: AsyncSession,
    *,
    subscription_service: Any,
    user: User,
    before_user: dict[str, Any],
    after_user: dict[str, Any],
) -> None:
    user_id = int(user.user_id)
    before_panel_uuid = str(before_user.get("panel_user_uuid") or "") or None
    after_panel_uuid = str(after_user.get("panel_user_uuid") or "") or None
    if before_panel_uuid != after_panel_uuid:
        user.panel_user_uuid = before_panel_uuid
        await session.flush()

    active = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
    if active is not None:
        if not await subscription_service.sync_main_traffic_limit_to_panel(session, user_id):
            raise PaymentFulfillmentError(
                "payment_reversal_panel_failed",
                "The restored entitlement could not be verified on the panel.",
                status=502,
            )
        return

    if after_panel_uuid is None:
        return
    if before_panel_uuid is None:
        deleted = await subscription_service.panel_service.delete_user_from_panel(after_panel_uuid)
        if not deleted:
            raise PaymentFulfillmentError(
                "payment_reversal_panel_failed",
                "The panel user created by this payment could not be removed.",
                status=502,
            )
        return

    before_subscriptions = _snapshot_subscriptions(before_user)
    previous_end_dates = [
        _restore_value("end_date", item.get("end_date"))
        for item in before_subscriptions.values()
        if item.get("end_date")
    ]
    expire_at = max(previous_end_dates, default=datetime.now(UTC))
    payload = subscription_service._build_panel_update_payload(
        panel_user_uuid=before_panel_uuid,
        expire_at=expire_at,
        status="DISABLED",
        include_default_squads=False,
    )
    updated = await subscription_service.panel_service.update_user_details_on_panel(
        before_panel_uuid,
        payload,
    )
    if not updated:
        raise PaymentFulfillmentError(
            "payment_reversal_panel_failed",
            "The previous inactive entitlement could not be restored on the panel.",
            status=502,
        )


async def reverse_payment_fulfillment(
    session: AsyncSession,
    *,
    payment_id: int,
    actor_admin_id: int,
    reason: str,
    restore_promo_usage: bool,
    subscription_service: Any,
) -> Payment:
    payment = await payment_dal.get_payment_by_db_id_for_update(session, payment_id)
    if payment is None:
        raise PaymentFulfillmentError("not_found", "Payment not found.", status=404)
    status = str(payment.status or "").strip().lower()
    if status != "succeeded":
        raise PaymentFulfillmentError(
            "payment_not_succeeded",
            "Only a successfully fulfilled payment can be reversed.",
        )
    before = _parse_snapshot(payment.fulfillment_before_snapshot)
    after = _parse_snapshot(payment.fulfillment_after_snapshot)
    before_users = _snapshot_users(before)
    after_users = _snapshot_users(after)
    affected_user_ids = sorted(set(before_users) | set(after_users))

    if payment.fulfilled_at is not None:
        later_payment = await session.scalar(
            select(Payment.payment_id)
            .where(
                Payment.user_id == payment.user_id,
                Payment.payment_id != payment.payment_id,
                Payment.status == "succeeded",
                Payment.fulfilled_at.is_not(None),
                Payment.fulfilled_at > payment.fulfilled_at,
            )
            .limit(1)
        )
        if later_payment is not None:
            raise PaymentFulfillmentError(
                "payment_reversal_conflict",
                "A later payment changed this customer's entitlement.",
                details=[f"later_payment:{int(later_payment)}"],
            )

    users_result = await session.execute(
        select(User).where(User.user_id.in_(affected_user_ids)).with_for_update()
    )
    current_users = {int(user.user_id): user for user in users_result.scalars().all()}
    subscription_ids = {
        subscription_id
        for user_snapshot in after_users.values()
        for subscription_id in _snapshot_subscriptions(user_snapshot)
    }
    subscriptions_result = await session.execute(
        select(Subscription)
        .where(Subscription.subscription_id.in_(subscription_ids))
        .with_for_update()
    )
    current_subscriptions = {
        int(subscription.subscription_id): subscription
        for subscription in subscriptions_result.scalars().all()
    }

    conflicts: list[str] = []
    deltas: dict[int, tuple[dict[str, Any] | None, dict[str, Any], list[str]]] = {}
    for user_id, after_user in after_users.items():
        before_user = before_users.get(user_id, {"subscriptions": [], "panel_user_uuid": None})
        user = current_users.get(user_id)
        if user is None:
            conflicts.append(f"user:{user_id}:missing")
            continue
        if before_user.get("panel_user_uuid") != after_user.get("panel_user_uuid") and (
            _snapshot_value(user.panel_user_uuid) != after_user.get("panel_user_uuid")
        ):
            conflicts.append(f"user:{user_id}:panel_user_uuid")
        before_subscriptions = _snapshot_subscriptions(before_user)
        for subscription_id, after_subscription in _snapshot_subscriptions(after_user).items():
            before_subscription = before_subscriptions.get(subscription_id)
            changed_fields = [
                field
                for field in _SUBSCRIPTION_SNAPSHOT_FIELDS
                if before_subscription is None
                or before_subscription.get(field) != after_subscription.get(field)
            ]
            if not changed_fields:
                continue
            current = current_subscriptions.get(subscription_id)
            if current is None:
                conflicts.append(f"subscription:{subscription_id}:missing")
                continue
            conflicts.extend(
                f"subscription:{subscription_id}:{field}"
                for field in changed_fields
                if _snapshot_value(getattr(current, field, None)) != after_subscription.get(field)
            )
            deltas[subscription_id] = (before_subscription, after_subscription, changed_fields)

    if conflicts:
        raise PaymentFulfillmentError(
            "payment_reversal_conflict",
            "The entitlement changed after this payment and cannot be safely restored.",
            details=conflicts,
        )

    now = datetime.now(UTC)
    for subscription_id, (before_subscription, _after_subscription, fields) in deltas.items():
        current = current_subscriptions[subscription_id]
        if before_subscription is None:
            current.is_active = False
            current.end_date = min(current.end_date, now)
            current.status_from_panel = "CANCELLED"
            continue
        for field in fields:
            setattr(current, field, _restore_value(field, before_subscription.get(field)))

    await _delete_payment_effect_rows(session, int(payment.payment_id))
    promo_usage_restored = False
    if restore_promo_usage and payment.promo_code_id:
        promo_usage_restored = await promo_code_dal.release_promo_activation(
            session,
            int(payment.promo_code_id),
            int(payment.user_id),
            payment_id=int(payment.payment_id),
        )
    await session.flush()

    for user_id in affected_user_ids:
        user = current_users.get(user_id)
        if user is None:
            continue
        await _sync_reversed_user(
            session,
            subscription_service=subscription_service,
            user=user,
            before_user=before_users.get(user_id, {"subscriptions": []}),
            after_user=after_users.get(user_id, {"subscriptions": []}),
        )

    payment.reversed_at = now
    payment.reversed_by_admin_id = actor_admin_id
    payment.reversal_note = reason
    payment.promo_usage_restored = promo_usage_restored
    updated = await payment_dal.update_payment_status_by_db_id(session, payment_id, "reversed")
    if updated is None:
        raise PaymentFulfillmentError("not_found", "Payment not found.", status=404)
    return updated
