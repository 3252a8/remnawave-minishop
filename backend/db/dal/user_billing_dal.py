from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from db.models import UserBilling, UserPaymentMethod


async def get_user_billing(session: AsyncSession, user_id: int) -> UserBilling | None:
    stmt = select(UserBilling).where(UserBilling.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_yk_payment_method(
    session: AsyncSession,
    *,
    user_id: int,
    payment_method_id: str,
    card_last4: str | None = None,
    card_network: str | None = None,
) -> UserBilling:
    existing = await get_user_billing(session, user_id)
    if existing:
        existing.yookassa_payment_method_id = payment_method_id
        existing.card_last4 = card_last4
        existing.card_network = card_network
        existing.updated_at = func.now()
        await session.flush()
        await session.refresh(existing)
        return existing
    record = UserBilling(
        user_id=user_id,
        yookassa_payment_method_id=payment_method_id,
        card_last4=card_last4,
        card_network=card_network,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def delete_yk_payment_method(session: AsyncSession, user_id: int) -> bool:
    existing = await get_user_billing(session, user_id)
    if not existing:
        return False
    existing.yookassa_payment_method_id = None
    existing.card_last4 = None
    existing.card_network = None
    existing.updated_at = func.now()
    await session.flush()
    await session.refresh(existing)
    return True


# Multi-card support API
async def upsert_user_payment_method(
    session: AsyncSession,
    *,
    user_id: int,
    provider_payment_method_id: str,
    provider: str = "yookassa",
    card_last4: str | None = None,
    card_network: str | None = None,
    set_default: bool = False,
) -> UserPaymentMethod:
    provider = str(provider or "yookassa").strip().lower() or "yookassa"
    existing_stmt = select(UserPaymentMethod).where(
        UserPaymentMethod.provider == provider,
        UserPaymentMethod.provider_payment_method_id == provider_payment_method_id,
    )
    result = await session.execute(existing_stmt)
    existing: UserPaymentMethod | None = result.scalar_one_or_none()
    if existing:
        existing.card_last4 = card_last4
        existing.card_network = card_network
        if set_default:
            # unset previous defaults
            await session.execute(
                update(UserPaymentMethod)
                .where(
                    UserPaymentMethod.user_id == user_id,
                    UserPaymentMethod.provider == provider,
                )
                .values(is_default=False)
            )
            existing.is_default = True
        existing.updated_at = func.now()
        await session.flush()
        await session.refresh(existing)
        return existing
    if set_default:
        await session.execute(
            update(UserPaymentMethod)
            .where(
                UserPaymentMethod.user_id == user_id,
                UserPaymentMethod.provider == provider,
            )
            .values(is_default=False)
        )
    record = UserPaymentMethod(
        user_id=user_id,
        provider=provider,
        provider_payment_method_id=provider_payment_method_id,
        card_last4=card_last4,
        card_network=card_network,
        is_default=set_default,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def list_user_payment_methods(
    session: AsyncSession, user_id: int, provider: str | None = None
) -> list[UserPaymentMethod]:
    stmt = select(UserPaymentMethod).where(UserPaymentMethod.user_id == user_id)
    if provider:
        stmt = stmt.where(UserPaymentMethod.provider == provider)
    stmt = stmt.order_by(UserPaymentMethod.is_default.desc(), UserPaymentMethod.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_default_payment_method(
    session: AsyncSession, user_id: int, provider: str = "yookassa"
) -> UserPaymentMethod | None:
    provider = str(provider or "yookassa").strip().lower() or "yookassa"
    stmt = select(UserPaymentMethod).where(
        UserPaymentMethod.user_id == user_id,
        UserPaymentMethod.provider == provider,
        UserPaymentMethod.is_default == True,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def set_user_default_payment_method(
    session: AsyncSession, user_id: int, method_id: int
) -> bool:
    methods = await list_user_payment_methods(session, user_id)
    selected = next((m for m in methods if m.method_id == method_id), None)
    if not selected:
        return False
    await session.execute(
        update(UserPaymentMethod)
        .where(
            UserPaymentMethod.user_id == user_id,
            UserPaymentMethod.provider == selected.provider,
        )
        .values(is_default=False)
    )
    await session.execute(
        update(UserPaymentMethod)
        .where(UserPaymentMethod.method_id == method_id)
        .values(is_default=True)
    )
    return True


async def delete_user_payment_method(session: AsyncSession, user_id: int, method_id: int) -> bool:
    stmt = select(UserPaymentMethod).where(
        UserPaymentMethod.method_id == method_id, UserPaymentMethod.user_id == user_id
    )
    result = await session.execute(stmt)
    method = result.scalar_one_or_none()
    if not method:
        return False
    await session.delete(method)
    await session.flush()
    return True


async def delete_user_payment_method_by_provider_id(
    session: AsyncSession,
    user_id: int,
    provider_payment_method_id: str,
) -> bool:
    """Delete a saved payment method by its provider payment_method.id for a specific user.

    Useful when callbacks pass the provider id (e.g., YooKassa pm_...) instead of our internal method_id.
    """  # noqa: E501
    stmt = select(UserPaymentMethod).where(
        UserPaymentMethod.user_id == user_id,
        UserPaymentMethod.provider_payment_method_id == provider_payment_method_id,
    )
    result = await session.execute(stmt)
    method: UserPaymentMethod | None = result.scalar_one_or_none()
    if not method:
        return False
    await session.delete(method)
    await session.flush()
    return True


async def user_has_saved_payment_method(
    session: AsyncSession,
    user_id: int,
    provider: str = "yookassa",
) -> bool:
    """Return True if the user has at least one saved payment method."""
    try:
        provider = str(provider or "yookassa").strip().lower() or "yookassa"
        methods = await list_user_payment_methods(session, user_id, provider)
        if methods:
            return True
        if provider != "yookassa":
            return False
        billing = await get_user_billing(session, user_id)
        return bool(billing and billing.yookassa_payment_method_id)
    except Exception:
        return False
