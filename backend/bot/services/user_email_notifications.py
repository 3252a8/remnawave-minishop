import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import render_user_notification
from bot.services.message_audit import log_user_message_delivery
from config.settings import Settings

logger = logging.getLogger(__name__)


def _translate(
    i18n: JsonI18n | None,
    language: str,
    key: str | None,
    fallback: str = "",
    **kwargs: Any,
) -> str:
    if not key:
        return fallback
    if not i18n:
        return fallback or key
    text = i18n.gettext(language, key, **kwargs)
    return fallback if text == key and fallback else text


async def send_user_notification_email(
    *,
    settings: Settings,
    i18n: JsonI18n | None,
    user: Any,
    subject_key: str,
    message_text: str,
    dashboard_url: str | None = None,
    cta_label_key: str = "email_user_notification_cta",
    subject_kwargs: dict[str, Any] | None = None,
    heading_key: str | None = None,
    intro_key: str | None = None,
    session: AsyncSession | None = None,
    audit_event_type: str | None = None,
    audit_content: str | None = None,
    raise_on_error: bool = False,
) -> bool:
    if not settings.email_auth_configured:
        return False
    recipient = str(getattr(user, "email", "") or "").strip()
    if not recipient:
        return False

    language = (
        str(getattr(user, "language_code", "") or "").strip() or settings.DEFAULT_LANGUAGE or "ru"
    )
    kwargs = subject_kwargs or {}
    subject = _translate(i18n, language, subject_key, subject_key, **kwargs)
    heading = _translate(i18n, language, heading_key, subject, **kwargs)
    intro = _translate(
        i18n,
        language,
        intro_key or "email_user_notification_intro",
        "Notification from your account.",
    )
    cta_label = _translate(
        i18n,
        language,
        cta_label_key or "email_user_notification_cta",
        "Open dashboard",
    )

    try:
        content = render_user_notification(
            settings,
            language_code=language,
            subject=subject,
            heading=heading,
            intro=intro,
            message_text=message_text,
            dashboard_url=dashboard_url,
            cta_label=cta_label,
            i18n=i18n,
        )
        await EmailAuthService(settings, i18n).send_rendered_email(
            email=recipient,
            content=content,
        )
        if session is not None and audit_event_type:
            await log_user_message_delivery(
                session,
                target_user_id=getattr(user, "user_id", None),
                event_type=audit_event_type,
                channel="email",
                recipient=recipient,
                content=audit_content or f"subject_key={subject_key}",
            )
        return True
    except Exception:
        logger.exception("Failed to send user notification email to %s.", recipient)
        if raise_on_error:
            raise
        return False
