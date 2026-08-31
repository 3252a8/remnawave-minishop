import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from db.models import Payment

from .payment_order_validation import (
    normalize_payment_status as _normalize_payment_status,
)
from .payment_order_validation import (
    validate_existing_provider_payment_order as _validate_existing_provider_payment_order,
)
from .payment_order_validation import (
    would_overwrite_succeeded_payment as _would_overwrite_succeeded_payment,
)
from .payment_reporting_dal import (
    get_financial_statistics as get_financial_statistics,
)
from .payment_reporting_dal import (
    get_referral_revenue as get_referral_revenue,
)
from .payment_reporting_dal import (
    get_user_total_paid as get_user_total_paid,
)

logger = logging.getLogger(__name__)

_PAYMENT_STATUS_SUCCEEDED = "succeeded"
_PAYMENT_STATUS_PENDING_FINALIZATION = "succeeded_pending_finalization"
_PAYMENT_TERMINAL_STATUSES = frozenset(
    {
        _PAYMENT_STATUS_SUCCEEDED,
        "failed",
        "canceled",
        "cancelled",
        "failed_creation",
        "refunded",
        "reversed",
    }
)
_YOOKASSA_RECONCILABLE_STATUSES = (
    "pending_yookassa",
    "pending",
    "waiting_for_capture",
    _PAYMENT_STATUS_PENDING_FINALIZATION,
)


@dataclass(frozen=True, slots=True)
class YooKassaReconciliationCandidate:
    payment_id: int
    provider_payment_id: str


async def list_yookassa_reconciliation_candidates(
    session: AsyncSession,
    *,
    limit: int = 100,
    grace_seconds: int = 30,
) -> list[YooKassaReconciliationCandidate]:
    """Return old pending YooKassa orders that can be polled safely.

    The provider identifier is persisted before an order becomes eligible.
    ``updated_at`` is also used as the last-poll timestamp so a permanently
    pending order cannot monopolize the front of a bounded batch.
    """

    cutoff = datetime.now(UTC) - timedelta(seconds=max(0, int(grace_seconds)))
    provider_payment_id = func.coalesce(
        Payment.yookassa_payment_id,
        Payment.provider_payment_id,
    )
    last_activity_at = func.coalesce(Payment.updated_at, Payment.created_at)
    stmt = (
        select(Payment.payment_id, provider_payment_id)
        .where(
            func.lower(Payment.provider) == "yookassa",
            func.lower(Payment.status).in_(_YOOKASSA_RECONCILABLE_STATUSES),
            provider_payment_id.isnot(None),
            last_activity_at <= cutoff,
        )
        .order_by(last_activity_at.asc(), Payment.payment_id.asc())
        .limit(max(1, int(limit)))
    )
    rows = (await session.execute(stmt)).all()
    return [
        YooKassaReconciliationCandidate(
            payment_id=int(payment_id),
            provider_payment_id=str(remote_id),
        )
        for payment_id, remote_id in rows
        if remote_id
    ]


async def mark_yookassa_reconciliation_checked(
    session: AsyncSession,
    payment_id: int,
) -> None:
    """Rotate an unresolved order to the back of the reconciliation queue."""

    await session.execute(
        update(Payment)
        .where(
            Payment.payment_id == payment_id,
            func.lower(Payment.provider) == "yookassa",
            func.lower(Payment.status).in_(_YOOKASSA_RECONCILABLE_STATUSES),
        )
        .values(updated_at=func.now())
    )


async def _validate_payment_record_references(
    session: AsyncSession,
    payment_data: dict[str, Any],
) -> None:
    """Reject a payment payload whose referenced rows do not exist."""

    from .user_dal import get_user_by_id

    user = await get_user_by_id(session, payment_data["user_id"])
    if not user:
        raise ValueError(f"User with id {payment_data['user_id']} not found for creating payment.")

    if payment_data.get("promo_code_id"):
        from .promo_code_dal import get_promo_code_by_id

        promo = await get_promo_code_by_id(session, payment_data["promo_code_id"])
        if not promo:
            raise ValueError(f"Promo code with id {payment_data['promo_code_id']} not found.")


async def create_payment_record(session: AsyncSession, payment_data: dict[str, Any]) -> Payment:
    await _validate_payment_record_references(session, payment_data)

    new_payment = Payment(**payment_data)
    session.add(new_payment)
    await session.flush()
    await session.refresh(new_payment)
    logger.info(
        "Payment record %s created for user %s", new_payment.payment_id, new_payment.user_id
    )
    return new_payment


async def get_payment_by_idempotence_key(
    session: AsyncSession,
    idempotence_key: str,
    *,
    fresh: bool = False,
) -> Payment | None:
    """Fetch a payment by the immutable provider idempotence key."""
    key = str(idempotence_key or "").strip()
    if not key:
        return None
    stmt = select(Payment).where(Payment.idempotence_key == key)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_or_get_payment_record_by_idempotence_key(
    session: AsyncSession,
    payment_data: dict[str, Any],
) -> tuple[Payment, bool]:
    """Atomically claim one local payment row for an idempotent provider call.

    PostgreSQL resolves concurrent ``ON CONFLICT`` attempts against the unique
    ``payments.idempotence_key`` constraint, so only one caller can own the
    order before it reaches an external payment API.  The caller commits the
    newly created row before issuing that API call; a concurrent caller then
    loads the same row and can safely reuse the provider idempotence key.
    """
    payload = dict(payment_data)
    idempotence_key = str(payload.get("idempotence_key") or "").strip()
    if not idempotence_key:
        raise ValueError("idempotence_key is required for idempotent payment creation.")
    payload["idempotence_key"] = idempotence_key

    existing = await get_payment_by_idempotence_key(session, idempotence_key, fresh=True)
    if existing:
        return existing, False

    await _validate_payment_record_references(session, payload)
    stmt = (
        pg_insert(Payment)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=[Payment.idempotence_key])
        .returning(Payment.payment_id)
    )
    result = await session.execute(stmt)
    created = result.scalar_one_or_none() is not None

    payment = await get_payment_by_idempotence_key(session, idempotence_key, fresh=True)
    if payment is None:
        raise RuntimeError(
            f"Failed to load payment after claiming its idempotence key {idempotence_key!r}."
        )
    if created:
        logger.info(
            "Payment record %s created with idempotence key %s",
            payment.payment_id,
            idempotence_key,
        )
    return payment, created


async def get_payment_by_provider_payment_id(
    session: AsyncSession,
    provider: str,
    provider_payment_id: str,
    *,
    fresh: bool = False,
) -> Payment | None:
    """Fetch a payment by provider-specific identifier."""
    provider_key = str(provider or "").strip().lower()
    remote_id = str(provider_payment_id or "").strip()
    if not provider_key or not remote_id:
        return None
    stmt = select(Payment).where(
        Payment.provider == provider_key,
        Payment.provider_payment_id == remote_id,
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def ensure_payment_with_provider_id(
    session: AsyncSession,
    *,
    user_id: int,
    amount: float,
    currency: str,
    months: int,
    description: str,
    provider: str,
    provider_payment_id: str,
    sale_mode: str | None = None,
    tariff_key: str | None = None,
    purchased_gb: float | None = None,
    purchased_hwid_devices: int | None = None,
    hwid_valid_from: Any | None = None,
    hwid_valid_until: Any | None = None,
    hwid_pricing_period_months: int | None = None,
    hwid_proration_ratio: float | None = None,
    hwid_full_price: float | None = None,
    hwid_traffic_bonus_bytes: int | None = None,
    entitlement_context_snapshot: str | None = None,
    checkout_bundle_snapshot: str | None = None,
    checkout_bundle_hash: str | None = None,
) -> Payment:
    """Atomically create or validate one order for a provider payment id."""
    provider_key = str(provider or "").strip().lower()
    if not provider_key:
        raise ValueError("provider is required for payment creation.")
    remote_id = str(provider_payment_id or "").strip()
    if not remote_id:
        raise ValueError("provider_payment_id is required for payment creation.")

    existing = await get_payment_by_provider_payment_id(
        session,
        provider_key,
        remote_id,
        fresh=True,
    )
    if existing:
        _validate_existing_provider_payment_order(
            existing,
            user_id=user_id,
            amount=amount,
            currency=currency,
            months=months,
            provider=provider_key,
            sale_mode=sale_mode,
            tariff_key=tariff_key,
            purchased_gb=purchased_gb,
            purchased_hwid_devices=purchased_hwid_devices,
            hwid_valid_from=hwid_valid_from,
            hwid_valid_until=hwid_valid_until,
            hwid_pricing_period_months=hwid_pricing_period_months,
            hwid_proration_ratio=hwid_proration_ratio,
            hwid_full_price=hwid_full_price,
            hwid_traffic_bonus_bytes=hwid_traffic_bonus_bytes,
            entitlement_context_snapshot=entitlement_context_snapshot,
            checkout_bundle_snapshot=checkout_bundle_snapshot,
            checkout_bundle_hash=checkout_bundle_hash,
        )
        return existing

    pending_status = f"pending_{provider_key}"
    payment_payload: dict[str, Any] = {
        "user_id": user_id,
        "amount": float(amount),
        "currency": currency,
        "status": pending_status,
        "description": description,
        "subscription_duration_months": months,
        "provider_payment_id": remote_id,
        "provider": provider_key,
    }
    optional_fields = {
        "sale_mode": sale_mode,
        "tariff_key": tariff_key,
        "purchased_gb": purchased_gb,
        "purchased_hwid_devices": purchased_hwid_devices,
        "hwid_valid_from": hwid_valid_from,
        "hwid_valid_until": hwid_valid_until,
        "hwid_pricing_period_months": hwid_pricing_period_months,
        "hwid_proration_ratio": hwid_proration_ratio,
        "hwid_full_price": hwid_full_price,
        "hwid_traffic_bonus_bytes": hwid_traffic_bonus_bytes,
        "entitlement_context_snapshot": entitlement_context_snapshot,
        "checkout_bundle_snapshot": checkout_bundle_snapshot,
        "checkout_bundle_hash": checkout_bundle_hash,
    }
    payment_payload.update(
        {field: value for field, value in optional_fields.items() if value is not None}
    )
    await _validate_payment_record_references(session, payment_payload)
    stmt = (
        pg_insert(Payment)
        .values(**payment_payload)
        .on_conflict_do_nothing(index_elements=[Payment.provider, Payment.provider_payment_id])
        .returning(Payment.payment_id)
    )
    result = await session.execute(stmt)
    created = result.scalar_one_or_none() is not None

    payment = await get_payment_by_provider_payment_id(
        session,
        provider_key,
        remote_id,
        fresh=True,
    )
    if payment is None:
        raise RuntimeError(f"Failed to load payment after claiming provider id {remote_id!r}.")
    _validate_existing_provider_payment_order(
        payment,
        user_id=user_id,
        amount=amount,
        currency=currency,
        months=months,
        provider=provider_key,
        sale_mode=sale_mode,
        tariff_key=tariff_key,
        purchased_gb=purchased_gb,
        purchased_hwid_devices=purchased_hwid_devices,
        hwid_valid_from=hwid_valid_from,
        hwid_valid_until=hwid_valid_until,
        hwid_pricing_period_months=hwid_pricing_period_months,
        hwid_proration_ratio=hwid_proration_ratio,
        hwid_full_price=hwid_full_price,
        hwid_traffic_bonus_bytes=hwid_traffic_bonus_bytes,
        entitlement_context_snapshot=entitlement_context_snapshot,
        checkout_bundle_snapshot=checkout_bundle_snapshot,
        checkout_bundle_hash=checkout_bundle_hash,
    )
    if created:
        logger.info(
            "Payment record %s created with provider payment id %s",
            payment.payment_id,
            remote_id,
        )
    return payment


async def get_payment_by_db_id(
    session: AsyncSession,
    payment_db_id: int,
    *,
    fresh: bool = False,
) -> Payment | None:

    stmt = (
        select(Payment)
        .where(Payment.payment_id == payment_db_id)
        .options(joinedload(Payment.user), joinedload(Payment.promo_code_used))
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_payment_by_db_id_for_update(
    session: AsyncSession, payment_db_id: int
) -> Payment | None:
    """Load the current payment row under a transaction-scoped write lock.

    Payment finalization can be entered concurrently by webhook retries, a
    worker, and a Web App status refresh.  ``populate_existing`` is important:
    a session that loaded the row before waiting for the lock must not keep a
    stale pending status after the first finalizer commits.
    """
    stmt = (
        select(Payment)
        .where(Payment.payment_id == payment_db_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def claim_payment_finalization(
    session: AsyncSession,
    payment_db_id: int,
    *,
    provider_payment_id: str | None = None,
    provider_payment_url: str | None = None,
) -> Payment | None:
    """Atomically claim a non-final payment for successful-payment effects.

    The claim and all subsequent activation effects remain in the caller's
    transaction.  A concurrent claimant waits for that transaction and then
    sees ``succeeded`` in the conditional ``UPDATE``, so it cannot produce a
    second entitlement, event, or customer notification.  If the first
    transaction rolls back, a provider retry can safely claim the payment.
    """
    values: dict[str, Any] = {
        "status": _PAYMENT_STATUS_PENDING_FINALIZATION,
        "updated_at": func.now(),
    }
    if provider_payment_id is not None:
        values["provider_payment_id"] = provider_payment_id
    if provider_payment_url is not None:
        values["provider_payment_url"] = provider_payment_url

    stmt = (
        update(Payment)
        .where(
            Payment.payment_id == payment_db_id,
            func.lower(Payment.status) != _PAYMENT_STATUS_SUCCEEDED,
            func.lower(Payment.status) != "refunded",
            func.lower(Payment.status) != "reversed",
        )
        .values(**values)
        .returning(Payment.payment_id)
    )
    result = await session.execute(stmt)
    claimed_payment_id = result.scalar_one_or_none()
    if claimed_payment_id is None:
        logger.info("Payment record %s already succeeded; skipping finalization.", payment_db_id)
        return None
    # The conditional UPDATE above already holds the row lock until the caller
    # commits. Reload through the normal loader so callers retain eager-loaded
    # relationships such as ``payment.user``.
    return await get_payment_by_db_id(session, int(claimed_payment_id), fresh=True)


async def find_recent_pending_provider_payment(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    pending_status: str,
    amount: float,
    currency: str | None,
    sale_mode: str | None,
    months: int | None,
    purchased_gb: float | None,
    purchased_hwid_devices: int | None,
    hwid_traffic_bonus_bytes: int | None = None,
    tariff_key: str | None = None,
    promo_code_id: int | None = None,
    promo_effect_summary: str | None = None,
    requested_partner_balance: bool | None = None,
    tariff_change_quote_snapshot: str | None = None,
    entitlement_context_snapshot: str | None = None,
    checkout_bundle_hash: str | None = None,
    since_minutes: int | None = None,
) -> Payment | None:
    """Return the most recent pending payment matching the given tariff parameters.

    Used to reuse an existing provider payment link instead of creating a new one
    on repeated user clicks. A generic or provider-specific payment id must be
    populated so the caller can verify the remote payment link.

    Status matching is case-insensitive and also accepts the generic ``pending``
    alias so legacy rows (e.g. Platega ``PENDING`` or YooKassa ``pending``) stay
    reusable after provider APIs overwrite the internal pending status.
    """
    from datetime import datetime, timedelta

    conditions = [
        Payment.user_id == user_id,
        Payment.provider == provider,
        func.lower(Payment.status).in_(tuple({str(pending_status).lower(), "pending"})),
        or_(
            Payment.provider_payment_id.isnot(None),
            Payment.yookassa_payment_id.isnot(None),
        ),
        func.abs(Payment.amount - float(amount)) < 0.01,
    ]
    if since_minutes is not None:
        cutoff = datetime.now(UTC) - timedelta(minutes=max(1, since_minutes))
        conditions.append(Payment.created_at >= cutoff)
    if currency is not None:
        conditions.append(func.upper(Payment.currency) == str(currency).strip().upper())
    if sale_mode is not None:
        conditions.append(Payment.sale_mode == sale_mode)
    if tariff_change_quote_snapshot is not None:
        conditions.append(Payment.tariff_change_quote_snapshot == tariff_change_quote_snapshot)
    else:
        conditions.append(Payment.tariff_change_quote_snapshot.is_(None))
    if entitlement_context_snapshot is not None:
        conditions.append(Payment.entitlement_context_snapshot == entitlement_context_snapshot)
    else:
        conditions.append(Payment.entitlement_context_snapshot.is_(None))
    if checkout_bundle_hash is not None:
        conditions.append(Payment.checkout_bundle_hash == checkout_bundle_hash)
    else:
        conditions.append(Payment.checkout_bundle_hash.is_(None))
    if tariff_key is not None:
        conditions.append(Payment.tariff_key == tariff_key)
    if promo_code_id is not None:
        conditions.append(Payment.promo_code_id == promo_code_id)
        if promo_effect_summary is not None:
            conditions.append(Payment.promo_effect_summary == promo_effect_summary)
    else:
        conditions.append(Payment.promo_code_id.is_(None))
    if requested_partner_balance is not None:
        partner_balance_amount = func.coalesce(Payment.partner_balance_amount_minor, 0)
        conditions.append(
            partner_balance_amount > 0 if requested_partner_balance else partner_balance_amount == 0
        )
    if months is not None:
        conditions.append(Payment.subscription_duration_months == months)
    else:
        conditions.append(Payment.subscription_duration_months.is_(None))
    if purchased_gb is not None:
        conditions.append(func.abs(Payment.purchased_gb - float(purchased_gb)) < 0.0001)
    else:
        conditions.append(Payment.purchased_gb.is_(None))
    if purchased_hwid_devices is not None:
        conditions.append(Payment.purchased_hwid_devices == purchased_hwid_devices)
    else:
        conditions.append(Payment.purchased_hwid_devices.is_(None))
    if hwid_traffic_bonus_bytes is not None:
        conditions.append(Payment.hwid_traffic_bonus_bytes == hwid_traffic_bonus_bytes)
    else:
        conditions.append(Payment.hwid_traffic_bonus_bytes.is_(None))

    stmt = (
        select(Payment)
        .where(and_(*conditions))
        .options(joinedload(Payment.user), joinedload(Payment.promo_code_used))
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_resumable_promo_payment(
    session: AsyncSession,
    *,
    user_id: int,
) -> Payment | None:
    """Return the newest discounted checkout that still has a reusable link."""

    normalized_status = func.lower(func.trim(Payment.status))
    stmt = (
        select(Payment)
        .where(
            Payment.user_id == user_id,
            or_(
                Payment.promo_code_id.isnot(None),
                Payment.partner_balance_amount_minor > 0,
            ),
            Payment.provider_payment_url.isnot(None),
            func.length(func.trim(Payment.provider_payment_url)) > 0,
            or_(
                normalized_status == "pending",
                normalized_status.like("pending_%"),
                normalized_status.in_(
                    (
                        "created",
                        "active",
                        "new",
                        "open",
                        "process",
                        "processing",
                        "underpaid",
                        "waiting_for_capture",
                    )
                ),
            ),
        )
        .options(joinedload(Payment.promo_code_used))
        .order_by(Payment.created_at.desc(), Payment.payment_id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_payment_status_by_db_id(
    session: AsyncSession,
    payment_db_id: int,
    new_status: str,
    yk_payment_id: str | None = None,
    provider_payment_url: str | None = None,
    checkout_expires_at: datetime | None = None,
    failure_kind: str | None = None,
    failure_http_status: int | None = None,
    failure_provider_code: str | None = None,
) -> Payment | None:
    payment = await get_payment_by_db_id_for_update(session, payment_db_id)
    if payment:
        previous_status = _normalize_payment_status(payment.status)
        preserve_succeeded = _would_overwrite_succeeded_payment(payment.status, new_status)
        if preserve_succeeded:
            logger.info(
                "Payment record %s already succeeded; ignoring status update to %s.",
                payment.payment_id,
                new_status,
            )
        else:
            payment.status = new_status
            payment.updated_at = func.now()
            uses_user_balance = bool(int(getattr(payment, "user_balance_amount_minor", 0) or 0))
            if failure_kind is not None:
                payment.failure_kind = str(failure_kind)[:64]
            if failure_http_status is not None:
                payment.failure_http_status = int(failure_http_status)
            if failure_provider_code is not None:
                payment.failure_provider_code = str(failure_provider_code)[:128]
            normalized_new_status = _normalize_payment_status(new_status)
            if normalized_new_status == _PAYMENT_STATUS_SUCCEEDED:
                from bot.services.partner_checkout_balance import (
                    PartnerCheckoutBalanceService,
                )

                await PartnerCheckoutBalanceService.ensure_consumed(
                    session,
                    payment_id=payment_db_id,
                )
                if uses_user_balance:
                    from bot.services.user_balance_service import UserBalanceService

                    await UserBalanceService.ensure_consumed(
                        session,
                        payment_id=payment_db_id,
                    )
            try:
                balance_savepoint = await session.begin_nested()
                try:
                    from bot.services.partner_checkout_balance import (
                        PartnerCheckoutBalanceService,
                    )

                    await PartnerCheckoutBalanceService.release_if_terminal(
                        session,
                        payment_id=payment_db_id,
                        status=new_status,
                    )
                    if uses_user_balance:
                        from bot.services.user_balance_service import UserBalanceService

                        await UserBalanceService.release_if_terminal(
                            session,
                            payment_id=payment_db_id,
                            status=new_status,
                        )
                except Exception:
                    await balance_savepoint.rollback()
                    raise
                else:
                    await balance_savepoint.commit()
            except Exception:
                logger.exception(
                    "Partner checkout balance release failed for payment %s; "
                    "the reconciler will retry it.",
                    payment_db_id,
                )
            if previous_status == "succeeded" and _normalize_payment_status(new_status) in {
                "refunded",
                "reversed",
            }:
                try:
                    reversal_savepoint = await session.begin_nested()
                    try:
                        from bot.services.partner_commission_service import (
                            PartnerCommissionService,
                        )

                        await PartnerCommissionService.reverse_payment(session, payment_db_id)
                    except Exception:
                        await reversal_savepoint.rollback()
                        raise
                    else:
                        await reversal_savepoint.commit()
                except Exception:
                    logger.exception(
                        "Partner commission reversal failed for refunded payment %s; "
                        "the reconciler will retry it.",
                        payment_db_id,
                    )
                if str(getattr(payment, "sale_mode", "") or "").split("@", 1)[0] == "balance_topup":
                    try:
                        reversal_savepoint = await session.begin_nested()
                        try:
                            from bot.services.user_balance_service import UserBalanceService

                            await UserBalanceService.reverse_payment_topup(
                                session,
                                payment_id=payment_db_id,
                                reason=f"payment {new_status}",
                            )
                        except Exception:
                            await reversal_savepoint.rollback()
                            raise
                        else:
                            await reversal_savepoint.commit()
                    except Exception:
                        logger.exception(
                            "User balance top-up reversal failed for payment %s; "
                            "the reconciler will retry it.",
                            payment_db_id,
                        )
        if yk_payment_id and payment.yookassa_payment_id is None:
            payment.yookassa_payment_id = yk_payment_id
        if provider_payment_url:
            payment.provider_payment_url = provider_payment_url
        if checkout_expires_at is not None:
            payment.checkout_expires_at = checkout_expires_at
        await session.flush()
        await session.refresh(payment)
        if not preserve_succeeded:
            logger.info("Payment record %s status updated to %s.", payment.payment_id, new_status)
    else:
        logger.warning("Payment record with DB ID %s not found for status update.", payment_db_id)
    return payment


async def get_recent_payment_logs_with_user(
    session: AsyncSession, limit: int = 20, offset: int = 0
) -> list[Payment]:
    stmt = (
        select(Payment)
        .options(joinedload(Payment.user))
        .where(Payment.status == "succeeded")
        .order_by(Payment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_payments_count(session: AsyncSession) -> int:
    """Get total count of successful payments."""
    stmt = select(func.count(Payment.payment_id)).where(Payment.status == "succeeded")
    result = await session.execute(stmt)
    return result.scalar() or 0


async def get_all_payments_count(session: AsyncSession) -> int:
    """Count all payment attempts shown in the Web Admin table."""
    result = await session.execute(select(func.count(Payment.payment_id)))
    return result.scalar() or 0


async def get_all_succeeded_payments_with_user(session: AsyncSession) -> list[Payment]:
    """Get all successful payments with user data for export."""
    stmt = (
        select(Payment)
        .options(selectinload(Payment.user))
        .where(Payment.status == "succeeded")
        .order_by(Payment.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_user_succeeded_payments(
    session: AsyncSession, user_id: int, exclude_payment_id: int | None = None
) -> int:
    """Count succeeded payments for a specific user.

    If exclude_payment_id is provided, that specific payment will be excluded
    from the count. Useful to check "prior" payments while processing the
    current payment in the same transaction.
    """
    conditions = [Payment.user_id == user_id, Payment.status == "succeeded"]
    if exclude_payment_id is not None:
        conditions.append(Payment.payment_id != exclude_payment_id)
    stmt = select(func.count(Payment.payment_id)).where(and_(*conditions))
    result = await session.execute(stmt)
    return result.scalar() or 0


async def get_user_succeeded_payments_after(
    session: AsyncSession,
    user_id: int,
    after: Any,
    *,
    limit: int = 20,
    exclude_payment_id: int | None = None,
) -> list[Payment]:
    """Return succeeded payments that could supersede an older checkout."""

    conditions = [Payment.user_id == user_id, Payment.status == "succeeded"]
    if exclude_payment_id is not None:
        conditions.append(Payment.payment_id != exclude_payment_id)
    if after is not None:
        conditions.append(or_(Payment.created_at >= after, Payment.updated_at >= after))

    stmt = (
        select(Payment)
        .where(and_(*conditions))
        .options(joinedload(Payment.user), joinedload(Payment.promo_code_used))
        .order_by(Payment.created_at.desc(), Payment.updated_at.desc(), Payment.payment_id.desc())
        .limit(max(1, int(limit)))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_provider_payment_and_status(
    session: AsyncSession,
    payment_db_id: int,
    provider_payment_id: str,
    new_status: str,
    provider_payment_url: str | None = None,
    checkout_expires_at: datetime | None = None,
) -> Payment | None:
    payment = await get_payment_by_db_id_for_update(session, payment_db_id)
    if payment:
        preserve_succeeded = _would_overwrite_succeeded_payment(payment.status, new_status)
        if preserve_succeeded:
            logger.info(
                "Payment record %s already succeeded; ignoring provider status update to %s.",
                payment.payment_id,
                new_status,
            )
        else:
            payment.status = new_status
            payment.updated_at = func.now()
        payment.provider_payment_id = provider_payment_id
        if provider_payment_url:
            payment.provider_payment_url = provider_payment_url
        if checkout_expires_at is not None:
            payment.checkout_expires_at = checkout_expires_at
        await session.flush()
        await session.refresh(payment)
        if not preserve_succeeded:
            logger.info(
                "Payment record %s updated with provider id %s and status %s.",
                payment.payment_id,
                provider_payment_id,
                new_status,
            )
    else:
        logger.warning("Payment record with DB ID %s not found for provider update.", payment_db_id)
    return payment


async def transition_provider_payment_to_terminal(
    session: AsyncSession,
    payment_db_id: int,
    provider_payment_id: str,
    new_status: str,
    *,
    failure_kind: str | None = None,
    failure_http_status: int | None = None,
    failure_provider_code: str | None = None,
    provider_cancellation_party: str | None = None,
    provider_cancellation_reason: str | None = None,
    suppress_failure_notification: bool = False,
) -> tuple[Payment | None, bool]:
    """Lock and finalize a payment once, returning whether this call changed it."""

    normalized_new_status = _normalize_payment_status(new_status)
    if normalized_new_status not in _PAYMENT_TERMINAL_STATUSES:
        raise ValueError(f"Payment status is not terminal: {new_status}")

    payment = await get_payment_by_db_id_for_update(session, payment_db_id)
    if payment is None:
        logger.warning("Payment record with DB ID %s not found for terminal update.", payment_db_id)
        return None, False

    if _normalize_payment_status(payment.status) in _PAYMENT_TERMINAL_STATUSES:
        if (
            _normalize_payment_status(payment.status) != _PAYMENT_STATUS_SUCCEEDED
            and payment.auto_renew_cycle_id is not None
        ):
            from . import auto_renew_dal

            await auto_renew_dal.stop_cycle(
                session,
                int(payment.auto_renew_cycle_id),
                failure_kind or normalized_new_status,
            )
        logger.info(
            "Payment record %s is already terminal with status %s; skipping duplicate update.",
            payment.payment_id,
            payment.status,
        )
        return payment, False

    payment.status = normalized_new_status
    payment.updated_at = func.now()
    payment.provider_payment_id = provider_payment_id
    if failure_kind is not None:
        payment.failure_kind = str(failure_kind)[:64]
    if failure_http_status is not None:
        payment.failure_http_status = int(failure_http_status)
    if failure_provider_code is not None:
        payment.failure_provider_code = str(failure_provider_code)[:128]
    if provider_cancellation_party is not None:
        payment.provider_cancellation_party = str(provider_cancellation_party)[:64]
    if provider_cancellation_reason is not None:
        payment.provider_cancellation_reason = str(provider_cancellation_reason)[:128]
    if suppress_failure_notification:
        payment.failure_notified_at = func.now()
    if (
        normalized_new_status != _PAYMENT_STATUS_SUCCEEDED
        and payment.auto_renew_cycle_id is not None
    ):
        from . import auto_renew_dal

        await auto_renew_dal.stop_cycle(
            session,
            int(payment.auto_renew_cycle_id),
            failure_kind or normalized_new_status,
        )
    from .payment_checkout_dal import release_partner_balance_safely

    await release_partner_balance_safely(
        session,
        payment_id=payment_db_id,
        status=normalized_new_status,
    )
    await session.flush()
    await session.refresh(payment)
    logger.info(
        "Payment record %s transitioned to terminal status %s.",
        payment.payment_id,
        normalized_new_status,
    )
    return payment, True
