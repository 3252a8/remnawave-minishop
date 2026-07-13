import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, case, delete, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from db.models import Payment, PromoCode, PromoCodeActivation

logger = logging.getLogger(__name__)

_ARCHIVED_CODE_PREFIX = "__ARCHIVED_PROMO__"


def _archived_storage_code(promo: PromoCode, attempt: int = 0) -> str:
    suffix = f"_{attempt}" if attempt else ""
    public_code = str(promo.archived_code or promo.code or "").strip()
    return f"{_ARCHIVED_CODE_PREFIX}{int(promo.promo_code_id)}{suffix}__{public_code}"


async def create_promo_code(session: AsyncSession, promo_data: dict[str, Any]) -> PromoCode:
    new_promo = PromoCode(**promo_data)
    session.add(new_promo)
    await session.flush()
    await session.refresh(new_promo)
    logger.info("Promo code '%s' created with ID %s", new_promo.code, new_promo.promo_code_id)
    return new_promo


async def get_promo_code_by_id(session: AsyncSession, promo_code_id: int) -> PromoCode | None:
    return await session.get(PromoCode, promo_code_id)


def _promo_lookup_candidates(code_str: str, *, preserve_case: bool) -> list[str]:
    code = str(code_str or "").strip()
    if not code:
        return []
    candidates = [code] if preserve_case else []
    upper_code = code.upper()
    if upper_code not in candidates:
        candidates.append(upper_code)
    return candidates


async def get_promo_code_by_code(
    session: AsyncSession, code_str: str, *, preserve_case: bool = False
) -> PromoCode | None:
    """Get promo code by code string (regardless of active status)"""
    for candidate in _promo_lookup_candidates(code_str, preserve_case=preserve_case):
        stmt = select(PromoCode).where(PromoCode.code == candidate)
        result = await session.execute(stmt)
        promo = result.scalar_one_or_none()
        if promo:
            return promo
    return None


async def get_active_promo_code_by_code_str(
    session: AsyncSession,
    code_str: str,
    *,
    preserve_case: bool = False,
    for_update: bool = False,
) -> PromoCode | None:
    now = datetime.now(UTC)
    for candidate in _promo_lookup_candidates(code_str, preserve_case=preserve_case):
        stmt = select(PromoCode).where(
            PromoCode.code == candidate,
            PromoCode.is_active == True,
            PromoCode.archived_at == None,
            PromoCode.current_activations < PromoCode.max_activations,
            or_(PromoCode.valid_until == None, PromoCode.valid_until > now),
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        promo = result.scalar_one_or_none()
        if promo:
            return promo
    return None


async def get_all_active_promo_codes(
    session: AsyncSession, limit: int = 20, offset: int = 0
) -> list[PromoCode]:
    stmt = (
        select(PromoCode)
        .where(
            PromoCode.is_active == True,
            PromoCode.archived_at == None,
            or_(PromoCode.valid_until == None, PromoCode.valid_until > datetime.now(UTC)),
        )
        .order_by(PromoCode.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_promo_codes_with_details(
    session: AsyncSession, limit: int = 50, offset: int = 0
) -> list[PromoCode]:
    """Get all promo codes (active and inactive) with pagination for management"""
    stmt = (
        select(PromoCode)
        .where(PromoCode.archived_at == None)
        .order_by(PromoCode.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_promo_codes_count(session: AsyncSession) -> int:
    """Get total count of all promo codes"""
    from sqlalchemy import func

    stmt = select(func.count(PromoCode.promo_code_id)).where(PromoCode.archived_at == None)
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_promo_activations_by_code_id(
    session: AsyncSession, promo_code_id: int, limit: int | None = None, offset: int = 0
) -> list[PromoCodeActivation]:
    """Get activation history for a specific promo code with optional pagination."""
    stmt = (
        select(PromoCodeActivation)
        .options(
            selectinload(PromoCodeActivation.user),
            selectinload(PromoCodeActivation.payment),
        )
        .where(PromoCodeActivation.promo_code_id == promo_code_id)
        .order_by(PromoCodeActivation.activated_at.desc())
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_promo_activations_by_code_id(session: AsyncSession, promo_code_id: int) -> int:
    """Count total activations for a specific promo code."""
    stmt = (
        select(func.count())
        .select_from(PromoCodeActivation)
        .where(PromoCodeActivation.promo_code_id == promo_code_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def count_payments_by_promo_code_id(session: AsyncSession, promo_code_id: int) -> int:
    stmt = select(func.count()).select_from(Payment).where(Payment.promo_code_id == promo_code_id)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_promo_code(
    session: AsyncSession, promo_id: int, update_data: dict[str, Any]
) -> PromoCode | None:
    promo = await get_promo_code_by_id(session, promo_id)
    if not promo:
        return None
    for key, value in update_data.items():
        setattr(promo, key, value)
    await session.flush()
    await session.refresh(promo)
    return promo


async def release_archived_promo_code(session: AsyncSession, promo: PromoCode) -> PromoCode:
    if promo.archived_at is None:
        return promo
    if not promo.archived_code:
        promo.archived_code = str(promo.code or "").strip()
    if str(promo.code or "").startswith(_ARCHIVED_CODE_PREFIX):
        await session.flush()
        await session.refresh(promo)
        return promo

    for attempt in range(32):
        storage_code = _archived_storage_code(promo, attempt)
        existing = await get_promo_code_by_code(session, storage_code, preserve_case=True)
        if existing is None or int(existing.promo_code_id) == int(promo.promo_code_id):
            promo.code = storage_code
            promo.is_active = False
            await session.flush()
            await session.refresh(promo)
            return promo

    raise ValueError("archived_code_release_failed")


async def delete_promo_code(session: AsyncSession, promo_id: int) -> PromoCode | None:
    promo = await get_promo_code_by_id(session, promo_id)
    if not promo:
        return None
    activations_count = await count_promo_activations_by_code_id(session, promo_id)
    payments_count = await count_payments_by_promo_code_id(session, promo_id)
    if activations_count > 0 or payments_count > 0:
        promo.is_active = False
        promo.archived_at = datetime.now(UTC)
        return await release_archived_promo_code(session, promo)

    await session.delete(promo)
    await session.flush()
    return promo


async def increment_promo_code_usage(session: AsyncSession, promo_code_id: int) -> PromoCode | None:
    stmt = (
        update(PromoCode)
        .where(
            PromoCode.promo_code_id == promo_code_id,
            PromoCode.current_activations < PromoCode.max_activations,
        )
        .values(current_activations=PromoCode.current_activations + 1)
        .returning(PromoCode.promo_code_id)
    )
    result = await session.execute(stmt)
    updated_id = result.scalar_one_or_none()
    if updated_id is None:
        logger.warning("Promo code ID %s already reached max activations.", promo_code_id)
        return None
    promo = await get_promo_code_by_id(session, int(updated_id))
    if promo:
        await session.refresh(promo)
    return promo


async def get_user_activation_for_promo(
    session: AsyncSession, promo_code_id: int, user_id: int
) -> PromoCodeActivation | None:
    stmt = (
        select(PromoCodeActivation)
        .where(
            PromoCodeActivation.promo_code_id == promo_code_id,
            PromoCodeActivation.user_id == user_id,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def record_promo_activation(
    session: AsyncSession,
    promo_code_id: int,
    user_id: int,
    payment_id: int | None = None,
    *,
    effect_summary: str | None = None,
    bonus_days: int | None = None,
    discount_percent: float | None = None,
    duration_multiplier: float | None = None,
    traffic_multiplier: float | None = None,
    applies_to: str | None = None,
    base_amount: float | None = None,
    discount_amount: float | None = None,
    charged_months: int | None = None,
    charged_gb: float | None = None,
    granted_days: int | None = None,
    granted_gb: float | None = None,
) -> PromoCodeActivation | None:
    from .user_dal import lock_user_by_id

    if await lock_user_by_id(session, user_id) is None:
        logger.error("Cannot record promo activation: User %s not found.", user_id)
        return None

    existing_activation = await get_user_activation_for_promo(session, promo_code_id, user_id)
    if existing_activation:
        logger.info(
            "User %s has already activated promo code %s. Activation ID: %s",
            user_id,
            promo_code_id,
            existing_activation.activation_id,
        )
        return existing_activation

    from .user_dal import get_user_by_id

    user = await get_user_by_id(session, user_id)
    promo = await get_promo_code_by_id(session, promo_code_id)
    if not user or not promo:
        logger.error(
            "Cannot record promo activation: User %s or Promo %s not found.", user_id, promo_code_id
        )
        return None

    if payment_id:
        from .payment_dal import get_payment_by_db_id

        payment = await get_payment_by_db_id(session, payment_id)
        if not payment:
            logger.error("Cannot record promo activation: Payment %s not found.", payment_id)
            return None

    activation_data = {
        "promo_code_id": promo_code_id,
        "user_id": user_id,
        "payment_id": payment_id,
        "effect_summary": effect_summary,
        "bonus_days": bonus_days,
        "discount_percent": discount_percent,
        "duration_multiplier": duration_multiplier,
        "traffic_multiplier": traffic_multiplier,
        "applies_to": applies_to,
        "base_amount": base_amount,
        "discount_amount": discount_amount,
        "charged_months": charged_months,
        "charged_gb": charged_gb,
        "granted_days": granted_days,
        "granted_gb": granted_gb,
        "activated_at": datetime.now(UTC),
    }
    new_activation = PromoCodeActivation(**activation_data)
    session.add(new_activation)
    await session.flush()
    await session.refresh(new_activation)
    logger.info(
        "Promo code %s activated by user %s. Activation ID: %s",
        promo_code_id,
        user_id,
        new_activation.activation_id,
    )
    return new_activation


async def consume_promo_activation(
    session: AsyncSession,
    promo_code_id: int,
    user_id: int,
    payment_id: int | None = None,
    *,
    enforce_limit: bool = True,
    effect_summary: str | None = None,
    bonus_days: int | None = None,
    discount_percent: float | None = None,
    duration_multiplier: float | None = None,
    traffic_multiplier: float | None = None,
    applies_to: str | None = None,
    base_amount: float | None = None,
    discount_amount: float | None = None,
    charged_months: int | None = None,
    charged_gb: float | None = None,
    granted_days: int | None = None,
    granted_gb: float | None = None,
) -> PromoCodeActivation | None:
    """Atomically increment usage and record the activation in one transaction.

    ``enforce_limit=False`` is used only for already-created invoices: those
    rows carry their own frozen checkout terms and are honored even if the
    code later expires, is disabled, or reaches the configured limit.
    """
    from .user_dal import lock_user_by_id

    if await lock_user_by_id(session, user_id) is None:
        logger.error("Cannot consume promo activation: User %s not found.", user_id)
        return None

    existing_activation = await get_user_activation_for_promo(session, promo_code_id, user_id)
    if existing_activation:
        existing_payment_id = int(getattr(existing_activation, "payment_id", 0) or 0)
        if payment_id is not None and existing_payment_id == int(payment_id):
            return existing_activation
        logger.info(
            "User %s has already activated promo code %s. Activation ID: %s",
            user_id,
            promo_code_id,
            existing_activation.activation_id,
        )
        return None

    update_conditions = [PromoCode.promo_code_id == promo_code_id]
    if enforce_limit:
        update_conditions.append(PromoCode.current_activations < PromoCode.max_activations)
    stmt = (
        update(PromoCode)
        .where(and_(*update_conditions))
        .values(current_activations=PromoCode.current_activations + 1)
        .returning(PromoCode.promo_code_id)
    )
    result = await session.execute(stmt)
    updated_id = result.scalar_one_or_none()
    if updated_id is None:
        logger.warning("Promo code ID %s cannot be consumed.", promo_code_id)
        return None

    activation_data = {
        "promo_code_id": promo_code_id,
        "user_id": user_id,
        "payment_id": payment_id,
        "effect_summary": effect_summary,
        "bonus_days": bonus_days,
        "discount_percent": discount_percent,
        "duration_multiplier": duration_multiplier,
        "traffic_multiplier": traffic_multiplier,
        "applies_to": applies_to,
        "base_amount": base_amount,
        "discount_amount": discount_amount,
        "charged_months": charged_months,
        "charged_gb": charged_gb,
        "granted_days": granted_days,
        "granted_gb": granted_gb,
        "activated_at": datetime.now(UTC),
    }
    activation = PromoCodeActivation(**activation_data)
    session.add(activation)
    await session.flush()
    await session.refresh(activation)
    return activation


async def release_promo_activation(
    session: AsyncSession,
    promo_code_id: int,
    user_id: int,
    payment_id: int | None = None,
) -> bool:
    conditions = [
        PromoCodeActivation.promo_code_id == promo_code_id,
        PromoCodeActivation.user_id == user_id,
    ]
    if payment_id is not None:
        conditions.append(PromoCodeActivation.payment_id == payment_id)
    result = await session.execute(select(PromoCodeActivation).where(and_(*conditions)).limit(1))
    activation = result.scalar_one_or_none()
    if activation is None:
        return False
    await session.execute(
        delete(PromoCodeActivation).where(
            PromoCodeActivation.activation_id == activation.activation_id
        )
    )
    await session.execute(
        update(PromoCode)
        .where(PromoCode.promo_code_id == promo_code_id)
        .values(
            current_activations=case(
                (PromoCode.current_activations > 0, PromoCode.current_activations - 1),
                else_=0,
            )
        )
    )
    await session.flush()
    return True


async def user_has_pending_payment_with_promo(
    session: AsyncSession,
    user_id: int,
    promo_code_id: int,
    *,
    exclude_payment_id: int | None = None,
) -> bool:
    status = func.lower(Payment.status)
    conditions = [
        Payment.user_id == user_id,
        Payment.promo_code_id == promo_code_id,
        or_(
            status.like("pending%"),
            status.in_(("created", "new", "waiting_for_capture")),
        ),
    ]
    if exclude_payment_id is not None:
        conditions.append(Payment.payment_id != exclude_payment_id)
    result = await session.execute(select(Payment.payment_id).where(and_(*conditions)).limit(1))
    return result.scalar_one_or_none() is not None


async def count_pending_payments_with_promo(
    session: AsyncSession,
    promo_code_id: int,
    *,
    exclude_payment_id: int | None = None,
) -> int:
    """Count unpaid invoices that currently reserve a limited promo slot."""
    status = func.lower(Payment.status)
    conditions = [
        Payment.promo_code_id == promo_code_id,
        or_(
            status.like("pending%"),
            status.in_(("created", "new", "waiting_for_capture")),
        ),
    ]
    if exclude_payment_id is not None:
        conditions.append(Payment.payment_id != exclude_payment_id)
    result = await session.execute(select(func.count(Payment.payment_id)).where(and_(*conditions)))
    return int(result.scalar_one() or 0)
