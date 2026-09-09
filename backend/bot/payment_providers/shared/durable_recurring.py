"""Durable local ownership for provider-initiated saved-method charges."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from db.dal import auto_renew_dal, payment_dal

from .common import build_payment_record_payload
from .recurring import RecurringChargeContext, RecurringChargeResult, RecurringRequestSnapshot

logger = logging.getLogger(__name__)

TRANSPORT_RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=13),
)


@dataclass(frozen=True, slots=True)
class DurableRecurringDispatch:
    cycle_id: int
    payment: Any
    payment_id: int
    request_id: str
    attempt_number: int
    transport_replays: int
    fallback_retry_at: datetime


@dataclass(frozen=True, slots=True)
class DurableRecurringPreparation:
    dispatch: DurableRecurringDispatch | None = None
    result: RecurringChargeResult | None = None


def _existing_payment_result(payment: Any) -> RecurringChargeResult:
    status = str(getattr(payment, "status", "") or "").strip().lower()
    provider_payment_id = str(getattr(payment, "provider_payment_id", "") or "").strip() or None
    payment_id = int(payment.payment_id)
    if status in {
        "pending",
        "pending_cloudpayments",
        "pending_overpay",
        "pending_stripe",
        "creation_unknown",
        "succeeded_pending_finalization",
        "succeeded",
    }:
        return RecurringChargeResult.ok(
            provider_payment_id=provider_payment_id,
            payment_db_id=payment_id,
            status=status,
        )
    return RecurringChargeResult.failed(
        f"existing_payment:{status or 'unknown'}",
        provider_payment_id=provider_payment_id,
        payment_db_id=payment_id,
    )


async def prepare_durable_recurring_charge(
    context: RecurringChargeContext,
    *,
    provider: str,
    saved_method_id: str,
    pending_status: str,
    max_transport_replays: int,
    lease_seconds: int,
) -> DurableRecurringPreparation:
    """Claim one cycle and one local payment before calling a provider API."""

    cycle_end = context.renewal_cycle_end
    if not isinstance(cycle_end, datetime):
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed("missing_renewal_cycle")
        )
    cycle_end = (
        cycle_end.replace(tzinfo=UTC) if cycle_end.tzinfo is None else cycle_end.astimezone(UTC)
    )
    provider_key = str(provider or "").strip().lower()
    base_key = str(context.idempotence_key or "").strip()
    if not base_key:
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed("missing_idempotence_key")
        )
    consent_version = max(0, int(context.consent_version or 0))
    payment_method_db_id = (
        int(context.payment_method_db_id) if context.payment_method_db_id is not None else None
    )
    snapshot = RecurringRequestSnapshot(
        amount=float(context.amount),
        currency=str(context.currency).strip().upper(),
        months=int(context.months),
        duration_days=context.duration_days,
        subscription_terms_snapshot=context.subscription_terms_snapshot,
        sale_mode=str(context.sale_mode),
        description=str(context.description),
        metadata={str(key): str(value) for key, value in context.metadata.items()},
        hwid_quote=dict(context.hwid_quote or {}) or None,
        entitlement_context_snapshot=context.entitlement_context_snapshot,
        checkout_bundle_snapshot=context.checkout_bundle_snapshot,
    )
    snapshot_json = snapshot.to_json()

    try:
        if context.auto_renew_cycle_id is not None:
            cycle = await auto_renew_dal.get_cycle(
                context.session,
                int(context.auto_renew_cycle_id),
                fresh=True,
            )
            created_cycle = False
        else:
            cycle, created_cycle = await auto_renew_dal.create_or_get_cycle(
                context.session,
                {
                    "subscription_id": int(context.subscription_id),
                    "user_id": int(context.user_id),
                    "provider": provider_key,
                    "cycle_anchor": auto_renew_dal.cycle_anchor_utc(cycle_end),
                    "renewal_cycle_end": cycle_end,
                    "state": "scheduled",
                    "base_idempotence_key": base_key,
                    "consent_version": consent_version,
                    "payment_method_id": payment_method_db_id,
                    "payment_method_provider_id": saved_method_id,
                    "request_snapshot": snapshot_json,
                },
            )
        if cycle is None:
            return DurableRecurringPreparation(
                result=RecurringChargeResult.failed("auto_renew_cycle_missing")
            )
        if created_cycle:
            await context.session.commit()
    except Exception as exc:
        await context.session.rollback()
        logger.exception("Failed to claim durable %s auto-renew cycle", provider_key)
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed(str(exc), failure_kind="local_cycle_error")
        )

    cycle_id = int(cycle.cycle_id)
    immutable_values = {
        "subscription_id": (int(cycle.subscription_id), int(context.subscription_id)),
        "user_id": (int(cycle.user_id), int(context.user_id)),
        "provider": (str(cycle.provider), provider_key),
        "base_idempotence_key": (str(cycle.base_idempotence_key), base_key),
        "consent_version": (int(cycle.consent_version or 0), consent_version),
        "payment_method_id": (
            int(cycle.payment_method_id) if cycle.payment_method_id is not None else None,
            payment_method_db_id,
        ),
        "payment_method_provider_id": (
            str(cycle.payment_method_provider_id),
            saved_method_id,
        ),
    }
    mismatches = [
        field for field, (stored, expected) in immutable_values.items() if stored != expected
    ]
    if mismatches:
        await auto_renew_dal.stop_cycle(context.session, cycle_id, "immutable_context_changed")
        await context.session.commit()
        logger.error(
            "%s auto-renew cycle %s immutable fields changed: %s",
            provider_key,
            cycle_id,
            ", ".join(mismatches),
        )
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed("immutable_context_changed")
        )

    cycle_state = str(cycle.state or "").strip().lower()
    if cycle_state == "succeeded":
        return DurableRecurringPreparation(result=RecurringChargeResult.ok(status="succeeded"))
    if cycle_state == "stopped":
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed(
                f"cycle_stopped:{cycle.stopped_reason or 'unknown'}"
            )
        )

    if not created_cycle and context.auto_renew_cycle_id is None:
        return DurableRecurringPreparation(result=RecurringChargeResult.ok(status="pending"))
    try:
        snapshot_matches = RecurringRequestSnapshot.from_json(
            str(cycle.request_snapshot)
        ) == RecurringRequestSnapshot.from_json(snapshot_json)
    except (ValueError, KeyError, TypeError):
        snapshot_matches = False
    if not snapshot_matches:
        await auto_renew_dal.stop_cycle(context.session, cycle_id, "immutable_context_changed")
        await context.session.commit()
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed("immutable_context_changed")
        )

    payment = None
    current_payment_id = getattr(cycle, "current_payment_id", None)
    if current_payment_id is not None:
        payment = await payment_dal.get_payment_by_db_id(
            context.session,
            int(current_payment_id),
            fresh=True,
        )
        if payment is None:
            await auto_renew_dal.stop_cycle(context.session, cycle_id, "current_payment_missing")
            await context.session.commit()
            return DurableRecurringPreparation(
                result=RecurringChargeResult.failed("current_payment_missing")
            )
        if context.retry_kind != "transport" or getattr(payment, "provider_payment_id", None):
            return DurableRecurringPreparation(result=_existing_payment_result(payment))

    transport_replays = int(cycle.transport_replays or 0)
    if context.retry_kind == "transport":
        if transport_replays >= max(0, int(max_transport_replays)):
            await auto_renew_dal.stop_cycle(context.session, cycle_id, "transport_replay_cap")
            await context.session.commit()
            return DurableRecurringPreparation(
                result=RecurringChargeResult.failed("transport_replay_cap")
            )
        transport_replays += 1

    attempt_number = max(1, int(cycle.financial_attempts or context.attempt_number or 1))
    payment_payload = build_payment_record_payload(
        user_id=context.user_id,
        amount=float(context.amount),
        currency=snapshot.currency,
        status=pending_status,
        description=context.description,
        months=context.months,
        duration_days=context.duration_days,
        subscription_terms_snapshot=context.subscription_terms_snapshot,
        provider=provider_key,
        sale_mode=context.sale_mode,
        hwid_quote=dict(context.hwid_quote or {}) or None,
        is_auto_renew=True,
        renewal_subscription_id=context.subscription_id,
        renewal_cycle_end=cycle_end,
        entitlement_context_snapshot=context.entitlement_context_snapshot,
        checkout_bundle_snapshot=context.checkout_bundle_snapshot,
    )
    payment_payload.update(
        {
            "idempotence_key": base_key,
            "auto_renew_cycle_id": cycle_id,
            "renewal_attempt_number": attempt_number,
            "renewal_consent_version": consent_version,
            "renewal_payment_method_id": payment_method_db_id,
        }
    )
    try:
        if payment is None:
            (
                payment,
                created_payment,
            ) = await payment_dal.create_or_get_payment_record_by_idempotence_key(
                context.session,
                payment_payload,
            )
            if created_payment:
                await context.session.commit()
        else:
            created_payment = False
    except Exception as exc:
        await context.session.rollback()
        logger.exception("Failed to claim local %s auto-renew payment", provider_key)
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed(
                str(exc),
                payment_db_id=getattr(payment, "payment_id", None),
                failure_kind="local_payment_error",
            )
        )

    payment_was_dispatched = bool(
        current_payment_id is not None
        or getattr(payment, "provider_request_snapshot", None)
        or getattr(payment, "provider_payment_id", None)
    )
    if not created_payment and context.retry_kind != "transport" and payment_was_dispatched:
        return DurableRecurringPreparation(result=_existing_payment_result(payment))

    now = datetime.now(UTC)
    delay_index = min(transport_replays, len(TRANSPORT_RETRY_DELAYS) - 1)
    fallback_retry_at = now + TRANSPORT_RETRY_DELAYS[delay_index]
    payment_id = int(payment.payment_id)
    try:
        await auto_renew_dal.prepare_payment_dispatch(
            context.session,
            payment_id=payment_id,
            request_snapshot=snapshot_json,
            cycle_id=cycle_id,
            attempt_number=attempt_number,
            consent_version=consent_version,
            payment_method_id=payment_method_db_id,
        )
        await auto_renew_dal.record_payment_dispatch(
            context.session,
            cycle_id=cycle_id,
            payment_id=payment_id,
            attempt_number=attempt_number,
            transport_replays=transport_replays,
            fallback_retry_at=fallback_retry_at,
            lease_expires_at=now + timedelta(seconds=max(30, int(lease_seconds))),
        )
        await context.session.commit()
    except Exception as exc:
        await context.session.rollback()
        logger.exception("Failed to persist %s auto-renew dispatch intent", provider_key)
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed(
                str(exc),
                payment_db_id=payment_id,
                failure_kind="local_dispatch_error",
            )
        )

    if not await auto_renew_dal.validate_dispatch_context_for_update(context.session, cycle_id):
        await auto_renew_dal.mark_request_failure(
            context.session,
            payment_id=payment_id,
            status="failed_creation",
            failure_kind="consent_or_method_changed",
            http_status=None,
            provider_code=None,
        )
        await auto_renew_dal.stop_cycle(context.session, cycle_id, "consent_or_method_changed")
        await context.session.commit()
        return DurableRecurringPreparation(
            result=RecurringChargeResult.failed(
                "consent_or_method_changed",
                payment_db_id=payment_id,
                failure_kind="consent_or_method_changed",
            )
        )

    return DurableRecurringPreparation(
        dispatch=DurableRecurringDispatch(
            cycle_id=cycle_id,
            payment=payment,
            payment_id=payment_id,
            request_id=base_key,
            attempt_number=attempt_number,
            transport_replays=transport_replays,
            fallback_retry_at=fallback_retry_at,
        )
    )


async def complete_durable_recurring_charge(
    context: RecurringChargeContext,
    dispatch: DurableRecurringDispatch,
    *,
    provider_payment_id: str,
    pending_status: str,
    provider_status: str | None,
) -> RecurringChargeResult:
    await payment_dal.update_provider_payment_and_status(
        context.session,
        dispatch.payment_id,
        provider_payment_id,
        pending_status,
    )
    await auto_renew_dal.mark_waiting_provider(context.session, dispatch.cycle_id)
    await context.session.commit()
    return RecurringChargeResult.ok(
        provider_payment_id=provider_payment_id,
        payment_db_id=dispatch.payment_id,
        status=provider_status,
    )


async def fail_durable_recurring_charge(
    context: RecurringChargeContext,
    dispatch: DurableRecurringDispatch,
    *,
    message: str,
    uncertain: bool,
    retry_enabled: bool,
    max_transport_replays: int,
    http_status: int | None = None,
    provider_code: str | None = None,
) -> RecurringChargeResult:
    can_retry = bool(
        uncertain
        and retry_enabled
        and dispatch.transport_replays < max(0, int(max_transport_replays))
    )
    failure_kind = "provider_response_unknown" if uncertain else "request_rejected"
    await auto_renew_dal.mark_request_failure(
        context.session,
        payment_id=dispatch.payment_id,
        status="creation_unknown" if uncertain else "failed_creation",
        failure_kind=failure_kind,
        http_status=http_status,
        provider_code=provider_code,
    )
    if can_retry:
        await auto_renew_dal.schedule_transport_retry(
            context.session,
            cycle_id=dispatch.cycle_id,
            next_attempt_at=dispatch.fallback_retry_at,
            failure_kind=failure_kind,
            http_status=http_status,
            provider_code=provider_code,
            transport_replays=dispatch.transport_replays,
        )
    else:
        await auto_renew_dal.stop_cycle(
            context.session,
            dispatch.cycle_id,
            "transport_retry_disabled" if uncertain else failure_kind,
        )
    await context.session.commit()
    return RecurringChargeResult.failed(
        message,
        payment_db_id=dispatch.payment_id,
        retryable=can_retry,
        failure_kind=failure_kind,
        http_status=http_status,
        provider_code=provider_code,
    )
