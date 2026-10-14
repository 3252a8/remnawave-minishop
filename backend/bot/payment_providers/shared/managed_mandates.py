"""Provider-owned schedules: immutable mandates and idempotent paid cycles.

No charge is initiated here. Provider read APIs confirm each charge before
fulfillment; both webhook delivery and the worker use the same durable ledger.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from config.subscription_periods import legacy_months_to_days, sale_mode_duration_days
from db.dal import payment_dal, provider_mandate_dal, subscription_dal
from db.models import User
from db.provider_mandate_models import ProviderMandate

from .common import payment_amount_and_currency_match, sale_mode_base
from .link_flow import CreatePaymentRequest, CreateResult
from .success import PaymentSuccessRequest, finalize_successful_payment

logger = logging.getLogger(__name__)
TERMINAL_STATES = {"cancelled", "failed"}


def checkout_period_days(months: Any, sale_mode: str) -> int | None:
    if sale_mode_base(sale_mode) != "subscription":
        return None
    try:
        explicit = sale_mode_duration_days(sale_mode)
        return explicit or legacy_months_to_days(months)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_charge_time(value: Any, *, default_timezone: Any = UTC) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed.astimezone(UTC)
        if parsed.tzinfo
        else parsed.replace(tzinfo=default_timezone).astimezone(UTC)
    )


async def create_managed_checkout(
    service: Any,
    request: CreatePaymentRequest,
    *,
    provider: str,
    period_days: int,
    create_remote: Callable[[], Awaitable[CreateResult]],
) -> CreateResult:
    remote_id = ""
    try:
        async with service.async_session_factory() as session:
            # Serialize new mandates per account across backend instances.
            await session.execute(
                select(User.user_id).where(User.user_id == request.user_id).with_for_update()
            )
            live = await provider_mandate_dal.list_mandates(
                session, providers=service.mandate_providers, user_id=request.user_id
            )
            if live:
                return False, {"message": "active_provider_subscription_exists"}
            success, data = await create_remote()
            if not success:
                return False, data
            remote_id = str(data.get("id") or "")
            payment_url = str(data.get("payment_url") or "")
            if not remote_id or not payment_url:
                if remote_id:
                    await service.stop_remote_subscription(remote_id)
                return False, {"message": "invalid_subscription_response"}
            session.add(
                ProviderMandate(
                    provider=provider,
                    remote_id=remote_id,
                    anchor_payment_id=int(request.payment.payment_id),
                    user_id=request.user_id,
                    provider_customer_id=str(request.user_id),
                    period_days=period_days,
                    status="pending",
                )
            )
            await session.commit()
            return True, data
    except Exception:
        logger.exception("%s: could not persist mandate ownership", provider)
        if remote_id:
            await service.stop_remote_subscription(remote_id)
        return False, {"message": "subscription_persistence_failed"}


async def mirror_auto_renew(service: Any, *, provider: str, remote_id: str) -> None:
    async with service.async_session_factory() as session:
        record = await provider_mandate_dal.get_mandate(
            session, provider=provider, remote_id=remote_id, for_update=True
        )
        if record is None:
            return
        subscription = await subscription_dal.get_active_subscription_by_user_id(
            session, int(record.user_id)
        )
        if subscription is not None and str(subscription.provider) == provider:
            enabled = record.status in {"active", "past_due", "paused"}
            if bool(subscription.auto_renew_enabled) != enabled:
                await subscription_dal.set_auto_renew(
                    session,
                    int(subscription.subscription_id),
                    enabled,
                    stop_reason="provider_cancelled" if not enabled else "consent_changed",
                )
        await session.commit()


async def settle_managed_charge(
    service: Any,
    *,
    provider: str,
    remote_id: str,
    charge_id: str,
    amount: Any,
    currency: Any,
    occurred_at: datetime,
    remote_state: str,
) -> bool:
    if not charge_id:
        return False
    async with service.async_session_factory() as session:
        record = await provider_mandate_dal.get_mandate(
            session, provider=provider, remote_id=remote_id, for_update=True
        )
        if record is None:
            return False
        anchor = await payment_dal.get_payment_by_db_id(session, int(record.anchor_payment_id))
        if (
            anchor is None
            or anchor.provider != provider
            or int(anchor.user_id) != int(record.user_id)
        ):
            return False
        if not payment_amount_and_currency_match(
            expected_amount=anchor.amount,
            expected_currency=anchor.currency,
            received_amount=amount,
            received_currency=currency,
        ):
            return False
        key = f"mandate:{provider}:{remote_id}:{charge_id}"
        existing = await payment_dal.get_payment_by_idempotence_key(session, key, fresh=True)
        if existing is not None and existing.status in {"succeeded", "succeeded_pending_review"}:
            return True
        if record.initial_charge_id is None:
            # The original checkout is credited by the first confirmed charge;
            # later transactions get independent local orders, never overwrite it.
            record.initial_charge_id = charge_id
            payment = anchor
            payment.idempotence_key = key
            await session.flush()
        elif record.initial_charge_id == charge_id:
            payment = anchor
        else:
            payment, _created = await payment_dal.create_or_get_payment_record_by_idempotence_key(
                session,
                {
                    "user_id": int(record.user_id),
                    "amount": float(anchor.amount),
                    "currency": anchor.currency,
                    "status": f"pending_{provider}",
                    "description": anchor.description,
                    "subscription_duration_months": int(anchor.subscription_duration_months or 0),
                    "subscription_duration_days": int(record.period_days),
                    "period_semantics": "provider_managed",
                    "subscription_terms_snapshot": anchor.subscription_terms_snapshot,
                    "provider": provider,
                    "provider_payment_id": charge_id,
                    "idempotence_key": key,
                    "sale_mode": anchor.sale_mode,
                    "tariff_key": anchor.tariff_key,
                    "is_auto_renew": True,
                },
            )
        claimed = await payment_dal.claim_payment_finalization(
            session,
            int(payment.payment_id),
            provider_payment_id=remote_id if payment.payment_id == anchor.payment_id else charge_id,
        )
        if claimed is None:
            await session.commit()
            return True
        if record.status not in TERMINAL_STATES:
            record.status = remote_state
        previous_charge_at = parse_charge_time(record.last_charge_at)
        record.last_charge_at = max(previous_charge_at or occurred_at, occurred_at)
        await session.flush()
        outcome = await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=service.bot,
                settings=service.settings,
                i18n=service.i18n,
                session=session,
                subscription_service=service.subscription_service,
                referral_service=service.referral_service,
                payment=claimed,
                user_id=int(record.user_id),
                amount=float(anchor.amount),
                currency=anchor.currency,
                sale_mode=str(anchor.sale_mode or "subscription"),
                months=int(anchor.subscription_duration_months or 0),
                traffic_amount=None,
                provider_subscription=provider,
                provider_notification=provider,
                log_prefix=f"{provider} recurring payment",
            )
        )
        if outcome is None:
            return False
    await mirror_auto_renew(service, provider=provider, remote_id=remote_id)
    return True


class ManagedMandateMixin:
    mandate_providers: tuple[str, ...] = ()
    async_session_factory: Any
    _mandate_cursor: int = 0

    async def stop_remote_subscription(self, remote_id: str) -> bool:
        raise NotImplementedError

    async def reconcile_remote_mandate(self, *, provider: str, remote_id: str) -> bool:
        raise NotImplementedError

    async def cancel_provider_recurrence(self, session: Any, *, user_id: int) -> bool:
        records = await provider_mandate_dal.list_mandates(
            session, providers=self.mandate_providers, user_id=user_id, limit=10000
        )
        for record in records:
            if not await self.stop_remote_subscription(str(record.remote_id)):
                return False
            record.status = "cancelled"
        await session.flush()
        return True

    async def reconcile_recurring_payments(self) -> None:
        if not getattr(self, "can_reconcile_payments", True):
            return
        async with self.async_session_factory() as session:
            records = await provider_mandate_dal.list_mandates(
                session, providers=self.mandate_providers, after_id=self._mandate_cursor
            )
            candidates = [
                (int(record.mandate_id), str(record.provider), str(record.remote_id))
                for record in records
            ]
        if not candidates:
            self._mandate_cursor = 0
            return
        # One bounded batch per tick, with a cursor so old plans cannot starve
        # newer ones or monopolize the worker's one-off reconciliation queue.
        for candidate_id, provider, remote_id in candidates:
            self._mandate_cursor = candidate_id
            try:
                await self.reconcile_remote_mandate(provider=provider, remote_id=remote_id)
            except Exception:
                logger.exception("%s: mandate reconciliation failed", provider)


async def update_mandate_state(service: Any, *, provider: str, remote_id: str, status: str) -> None:
    async with service.async_session_factory() as session:
        record = await provider_mandate_dal.get_mandate(
            session, provider=provider, remote_id=remote_id, for_update=True
        )
        if record is not None and record.status not in TERMINAL_STATES:
            record.status = status
            if status in TERMINAL_STATES and record.initial_charge_id is None:
                await payment_dal.transition_provider_payment_to_terminal(
                    session,
                    int(record.anchor_payment_id),
                    remote_id,
                    "failed",
                    failure_kind="provider_subscription_cancelled",
                )
            await session.commit()
    await mirror_auto_renew(service, provider=provider, remote_id=remote_id)
