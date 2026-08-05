import logging
from datetime import datetime
from typing import Any

from sqlalchemy import String, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql.elements import ColumnElement

from ..models import MessageLog, User

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


def _message_logs_query(sort: str) -> Any:
    author = aliased(User, name="log_author")
    target = aliased(User, name="log_target")
    author_name = func.nullif(
        func.trim(func.coalesce(author.first_name, "") + " " + func.coalesce(author.last_name, "")),
        "",
    )
    target_name = func.nullif(
        func.trim(func.coalesce(target.first_name, "") + " " + func.coalesce(target.last_name, "")),
        "",
    )
    author_label = func.coalesce(
        author_name,
        author.username,
        author.email,
        MessageLog.telegram_first_name,
        MessageLog.telegram_username,
        cast(MessageLog.user_id, String),
    )
    target_label = func.coalesce(
        target_name,
        target.username,
        target.email,
        cast(MessageLog.target_user_id, String),
    )
    sort_columns: dict[str, ColumnElement[Any]] = {
        "date": MessageLog.timestamp,
        "event": MessageLog.event_type,
        "user": author_label,
        "target": target_label,
        "content": MessageLog.content,
    }
    sort_key, _, direction = (sort or "date_desc").lower().rpartition("_")
    column = sort_columns.get(sort_key, MessageLog.timestamp)
    descending = direction != "asc"
    order = column.desc().nullslast() if descending else column.asc().nullslast()
    tie_breaker = MessageLog.log_id.desc() if descending else MessageLog.log_id.asc()
    return (
        select(MessageLog)
        .outerjoin(author, MessageLog.user_id == author.user_id)
        .outerjoin(target, MessageLog.target_user_id == target.user_id)
        .options(selectinload(MessageLog.author_user), selectinload(MessageLog.target_user))
        .order_by(order, tie_breaker)
    )


async def get_all_message_logs(
    session: AsyncSession, limit: int, offset: int, *, sort: str = "date_desc"
) -> list[MessageLog]:
    stmt = _message_logs_query(sort).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_all_message_logs(session: AsyncSession) -> int:
    stmt = select(func.count()).select_from(MessageLog)
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_user_message_logs(
    session: AsyncSession,
    user_id_to_search: int,
    limit: int,
    offset: int,
    *,
    sort: str = "date_desc",
) -> list[MessageLog]:
    stmt = (
        _message_logs_query(sort)
        .where(
            or_(
                MessageLog.user_id == user_id_to_search,
                MessageLog.target_user_id == user_id_to_search,
            )
        )
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


async def has_recent_target_event(
    session: AsyncSession,
    *,
    target_user_id: int,
    event_type: str,
    since: datetime,
) -> bool:
    stmt = (
        select(MessageLog.log_id)
        .where(
            MessageLog.target_user_id == target_user_id,
            MessageLog.event_type == event_type,
            MessageLog.timestamp >= since,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def has_target_event_content(
    session: AsyncSession,
    *,
    target_user_id: int,
    event_type: str,
    content_fragment: str,
) -> bool:
    stmt = (
        select(MessageLog.log_id)
        .where(
            MessageLog.target_user_id == target_user_id,
            MessageLog.event_type == event_type,
            MessageLog.content.contains(content_fragment),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


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
