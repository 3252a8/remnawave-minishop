import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import message_log_dal

from .message_log_notifier import notify_message_log

logger = logging.getLogger(__name__)


def _clean_piece(value: object | None) -> str:
    return str(value or "").strip()


async def log_user_message_delivery(
    session: AsyncSession,
    *,
    target_user_id: int | None,
    event_type: str,
    channel: str,
    content: str,
    recipient: str | None = None,
    timestamp: datetime | None = None,
) -> None:
    """Add a best-effort user log entry for important outbound messages."""
    clean_event = _clean_piece(event_type)
    clean_channel = _clean_piece(channel)
    if not clean_event or not clean_channel:
        return

    parts = [f"channel={clean_channel}"]
    clean_recipient = _clean_piece(recipient)
    if clean_recipient:
        parts.append(f"recipient={clean_recipient}")
    clean_content = _clean_piece(content)
    if clean_content:
        parts.append(clean_content)

    try:
        payload = {
            "user_id": None,
            "event_type": clean_event,
            "content": " | ".join(parts)[:4000],
            "is_admin_event": False,
            "target_user_id": int(target_user_id) if target_user_id is not None else None,
            "timestamp": timestamp or datetime.now(UTC),
        }
        await message_log_dal.create_message_log_no_commit(session, payload)
        await notify_message_log(payload)
    except Exception:
        logger.exception(
            "Failed to add outbound message audit log for user %s event %s",
            target_user_id,
            clean_event,
        )
