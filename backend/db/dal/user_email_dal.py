# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; this DAL intentionally mutates loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type"

"""Persistence helpers for verified account email addresses."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import User, UserEmailAddress


class EmailAddressConflictError(ValueError):
    pass


def normalize_account_email(email: str) -> str:
    return str(email or "").strip().lower()


async def list_user_email_addresses(
    session: AsyncSession,
    user_id: int,
) -> list[UserEmailAddress]:
    result = await session.execute(
        select(UserEmailAddress)
        .where(UserEmailAddress.user_id == user_id)
        .order_by(
            UserEmailAddress.is_primary.desc(),
            UserEmailAddress.is_notification.desc(),
            UserEmailAddress.created_at.asc(),
        )
    )
    return list(result.scalars().all())


async def get_user_by_verified_email_address(
    session: AsyncSession,
    email: str,
) -> User | None:
    normalized = normalize_account_email(email)
    if not normalized:
        return None
    return (
        await session.execute(
            select(User)
            .join(UserEmailAddress, UserEmailAddress.user_id == User.user_id)
            .where(
                UserEmailAddress.email == normalized,
                UserEmailAddress.verified_at.is_not(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def upsert_user_email_address(
    session: AsyncSession,
    *,
    user_id: int,
    email: str,
    source: str,
    verified_at: datetime | None = None,
    is_primary: bool = False,
    is_notification: bool = False,
) -> UserEmailAddress:
    normalized = normalize_account_email(email)
    if not normalized:
        raise ValueError("Email is required")
    address = (
        await session.execute(select(UserEmailAddress).where(UserEmailAddress.email == normalized))
    ).scalar_one_or_none()
    if address is not None and int(address.user_id) != int(user_id):
        raise EmailAddressConflictError("Email address belongs to another account")
    if address is None:
        address = UserEmailAddress(
            user_id=user_id,
            email=normalized,
            source=str(source or "email")[:32],
            verified_at=verified_at or datetime.now(UTC),
        )
        session.add(address)
        await session.flush()
    else:
        address.verified_at = verified_at or address.verified_at or datetime.now(UTC)
        if str(address.source or "") not in {"email", "google", "yandex"}:
            address.source = str(source or "email")[:32]

    if is_primary:
        await session.execute(
            update(UserEmailAddress)
            .where(
                UserEmailAddress.user_id == user_id,
                UserEmailAddress.email != normalized,
                UserEmailAddress.is_primary == True,
            )
            .values(is_primary=False)
        )
        address.is_primary = True
    if is_notification:
        await session.execute(
            update(UserEmailAddress)
            .where(
                UserEmailAddress.user_id == user_id,
                UserEmailAddress.email != normalized,
                UserEmailAddress.is_notification == True,
            )
            .values(is_notification=False)
        )
        address.is_notification = True
    await session.flush()
    return address


async def ensure_primary_user_email_address(
    session: AsyncSession,
    user: User,
    *,
    source: str = "email",
) -> UserEmailAddress | None:
    email = normalize_account_email(str(user.email or ""))
    if not email or not user.email_verified_at:
        return None
    notification_email = normalize_account_email(
        str(getattr(user, "notification_email", None) or "")
    )
    if not notification_email:
        user.notification_email = email
        notification_email = email
    return await upsert_user_email_address(
        session,
        user_id=int(user.user_id),
        email=email,
        source=source,
        verified_at=user.email_verified_at,
        is_primary=True,
        is_notification=notification_email == email,
    )


async def set_user_notification_email(
    session: AsyncSession,
    user: User,
    email: str,
) -> UserEmailAddress | None:
    normalized = normalize_account_email(email)
    await ensure_primary_user_email_address(session, user)
    address = (
        await session.execute(
            select(UserEmailAddress).where(
                UserEmailAddress.user_id == user.user_id,
                UserEmailAddress.email == normalized,
                UserEmailAddress.verified_at.is_not(None),
            )
        )
    ).scalar_one_or_none()
    if address is None:
        return None
    await session.execute(
        update(UserEmailAddress)
        .where(
            UserEmailAddress.user_id == user.user_id,
            UserEmailAddress.is_notification == True,
        )
        .values(is_notification=False)
    )
    await session.flush()
    address.is_notification = True
    user.notification_email = normalized
    await session.flush()
    return address
