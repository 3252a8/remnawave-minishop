"""User-chosen device labels, keyed by the opaque device token (never the raw HWID)."""

from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.device_models import UserDeviceName


async def get_device_names(session: AsyncSession, user_id: int) -> dict[str, str]:
    result = await session.execute(
        select(UserDeviceName.device_token, UserDeviceName.name).where(
            UserDeviceName.user_id == user_id
        )
    )
    return {str(token): str(name) for token, name in result.all()}


async def set_device_name(
    session: AsyncSession, user_id: int, device_token: str, name: str
) -> None:
    """Store a label for the device; an empty ``name`` restores the default one."""
    if not name:
        await session.execute(
            delete(UserDeviceName).where(
                UserDeviceName.user_id == user_id,
                UserDeviceName.device_token == device_token,
            )
        )
        return
    now = datetime.now(UTC)
    statement = insert(UserDeviceName).values(
        user_id=user_id,
        device_token=device_token,
        name=name,
        created_at=now,
        updated_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[UserDeviceName.user_id, UserDeviceName.device_token],
            set_={"name": statement.excluded.name, "updated_at": statement.excluded.updated_at},
        )
    )


async def merge_owner(session: AsyncSession, source_user_id: int, target_user_id: int) -> None:
    """Move labels to the surviving account; its own label wins for a shared device."""
    target_tokens = select(UserDeviceName.device_token).where(
        UserDeviceName.user_id == target_user_id
    )
    await session.execute(
        delete(UserDeviceName).where(
            UserDeviceName.user_id == source_user_id,
            UserDeviceName.device_token.in_(target_tokens),
        )
    )
    await session.execute(
        update(UserDeviceName)
        .where(UserDeviceName.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
