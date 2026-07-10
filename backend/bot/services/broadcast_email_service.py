"""Background delivery of admin broadcasts over email.

The admin webapp broadcast endpoint queues Telegram messages through the rate
limited queue manager; email delivery is much slower (SMTP round-trips), so it
runs here as a detached asyncio task with bounded concurrency. Results are
summarized into ``message_logs`` so admins can audit delivery afterwards.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import render_broadcast_email
from config.settings import Settings
from db.dal import message_log_dal

logger = logging.getLogger(__name__)

BROADCAST_EMAIL_CONCURRENCY = 3
_BROADCAST_EMAIL_TASKS: set[asyncio.Task[None]] = set()


@dataclass(frozen=True)
class BroadcastEmailRecipient:
    user_id: int
    email: str
    language_code: str | None = None
    # Per-recipient rendered overrides (shortcode personalization). When ``None``
    # the shared ``message_text`` / ``subject`` passed to the sender are used, so
    # plain broadcasts and existing callers keep working unchanged.
    message_text: str | None = None
    subject: str | None = None


async def _send_one(
    email_service: EmailAuthService,
    settings: Settings,
    i18n: JsonI18n | None,
    recipient: BroadcastEmailRecipient,
    *,
    subject: str,
    message_text: str,
    buttons: Sequence[tuple[str, str]],
    semaphore: asyncio.Semaphore,
) -> bool:
    async with semaphore:
        try:
            content = render_broadcast_email(
                settings,
                language_code=recipient.language_code,
                subject=recipient.subject if recipient.subject is not None else subject,
                message_text=(
                    recipient.message_text if recipient.message_text is not None else message_text
                ),
                buttons=buttons,
                i18n=i18n,
            )
            await email_service.send_rendered_email(email=recipient.email, content=content)
            return True
        except Exception:
            logger.exception("Broadcast email failed for user %s.", recipient.user_id)
            return False


async def deliver_broadcast_emails(
    *,
    settings: Settings,
    i18n: JsonI18n | None,
    recipients: Sequence[BroadcastEmailRecipient],
    subject: str,
    message_text: str,
    buttons: Sequence[tuple[str, str]] = (),
    session_factory: sessionmaker | None = None,
    actor_id: int | None = None,
    target: str = "",
) -> tuple[int, int]:
    """Send the broadcast to every recipient; returns ``(sent, failed)``."""
    email_service = EmailAuthService(settings, i18n)
    semaphore = asyncio.Semaphore(BROADCAST_EMAIL_CONCURRENCY)
    results = await asyncio.gather(
        *(
            _send_one(
                email_service,
                settings,
                i18n,
                recipient,
                subject=subject,
                message_text=message_text,
                buttons=buttons,
                semaphore=semaphore,
            )
            for recipient in recipients
        )
    )
    sent = sum(1 for result in results if result)
    failed = len(results) - sent

    if session_factory is not None:
        try:
            async with session_factory() as session:
                await message_log_dal.create_message_log(
                    session,
                    {
                        "user_id": actor_id,
                        "event_type": "admin_broadcast_email_summary",
                        "content": (
                            f"target={target} email_sent={sent} email_failed={failed} "
                            f"text={message_text[:120]}"
                        ),
                        "is_admin_event": True,
                    },
                )
        except Exception:
            logger.exception("Failed to log broadcast email summary.")
    logger.info(
        "Broadcast email delivery finished: target=%s sent=%s failed=%s", target, sent, failed
    )
    return sent, failed


def schedule_broadcast_emails(
    *,
    settings: Settings,
    i18n: JsonI18n | None,
    recipients: Sequence[BroadcastEmailRecipient],
    subject: str,
    message_text: str,
    buttons: Sequence[tuple[str, str]] = (),
    session_factory: sessionmaker | None = None,
    actor_id: int | None = None,
    target: str = "",
) -> int:
    """Kick off background email delivery; returns the number of recipients."""
    if not recipients:
        return 0

    async def _run() -> None:
        await deliver_broadcast_emails(
            settings=settings,
            i18n=i18n,
            recipients=recipients,
            subject=subject,
            message_text=message_text,
            buttons=buttons,
            session_factory=session_factory,
            actor_id=actor_id,
            target=target,
        )

    task = asyncio.create_task(_run())
    _BROADCAST_EMAIL_TASKS.add(task)
    task.add_done_callback(_BROADCAST_EMAIL_TASKS.discard)
    return len(recipients)
