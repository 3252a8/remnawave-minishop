import logging

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..models import MessageLog

logger = logging.getLogger(__name__)


async def create_message_log(session: AsyncSession, log_data: dict) -> MessageLog | None:

    try:
        log_entry = await create_message_log_no_commit(session, log_data)
        await session.commit()
        await session.refresh(log_entry)
        return log_entry
    except Exception as e:
        await session.rollback()
        logger.exception("Failed to create and commit message log: %s", e)
        return None


async def get_all_message_logs(session: AsyncSession, limit: int, offset: int) -> list[MessageLog]:
    stmt = (
        select(MessageLog)
        .options(selectinload(MessageLog.author_user), selectinload(MessageLog.target_user))
        .order_by(MessageLog.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_all_message_logs(session: AsyncSession) -> int:
    stmt = select(func.count()).select_from(MessageLog)
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_user_message_logs(
    session: AsyncSession, user_id_to_search: int, limit: int, offset: int
) -> list[MessageLog]:
    stmt = (
        select(MessageLog)
        .options(selectinload(MessageLog.author_user), selectinload(MessageLog.target_user))
        .where(
            or_(
                MessageLog.user_id == user_id_to_search,
                MessageLog.target_user_id == user_id_to_search,
            )
        )
        .order_by(MessageLog.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_user_message_logs(session: AsyncSession, user_id_to_search: int) -> int:
    stmt = (
        select(func.count())
        .select_from(MessageLog)
        .where(
            or_(
                MessageLog.user_id == user_id_to_search,
                MessageLog.target_user_id == user_id_to_search,
            )
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def create_message_log_no_commit(session: AsyncSession, log_data: dict) -> MessageLog:

    if log_data.get("target_user_id"):
        from .user_dal import get_user_by_id

        target_user = await get_user_by_id(session, log_data["target_user_id"])
        if not target_user:
            logger.warning(
                "Target user %s not found for message log. Setting to NULL.",
                log_data["target_user_id"],
            )
            log_data["target_user_id"] = None

    new_log = MessageLog(**log_data)
    session.add(new_log)

    logger.debug(
        "Message log added to session: user %s, event %s",
        log_data.get("user_id"),
        log_data.get("event_type"),
    )
    return new_log
