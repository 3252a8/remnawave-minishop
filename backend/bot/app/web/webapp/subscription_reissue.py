"""User-initiated subscription link reissue for the Mini App.

Revokes the subscription on the panel (which regenerates the short UUID and
therefore disconnects every device still using the previous link). The new
link is delivered by email when possible, falls back to a linked Telegram
account, and always remains available in the Mini App.
"""

import logging
from html import escape as html_escape
from typing import Any

from aiogram import Bot
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot,
    get_i18n,
    get_session_factory,
    get_settings,
    get_subscription_service,
)
from bot.app.web.webapp.cache_helpers import invalidate_webapp_user_caches
from bot.middlewares.i18n import JsonI18n
from bot.services.outbound_messaging import OutboundMessagingService
from bot.services.subscription_reissue_access import reissue_subscription_access
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.user_email_notifications import send_user_notification_email
from bot.services.user_notification_policy import email_recipient, telegram_recipient
from bot.utils.config_link import prepare_config_links
from bot.utils.mini_app_url import (
    subscription_mini_app_install_url,
    subscription_mini_app_path_url,
)
from config.settings import Settings
from db.dal import user_dal

from .assets import (
    _enforce_webapp_rate_limit,
)
from .common import (
    _json_error,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import (
    WebAppSubscriptionReissuePayload,
)
from .response_helpers import json_response

logger = logging.getLogger(__name__)


def subscription_reissue_feature_enabled(settings: Settings) -> bool:
    """Return whether users may rotate their subscription link."""
    return bool(settings.SUBSCRIPTION_REISSUE_ENABLED)


async def subscription_reissue_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="subscription_reissue",
    )
    if rate_limit_response:
        return rate_limit_response

    settings: Settings = get_settings(request)
    if not subscription_reissue_feature_enabled(settings):
        return _json_error(404, "subscription_reissue_disabled", "Subscription reissue is disabled")

    await _parse_model_payload(request, WebAppSubscriptionReissuePayload)

    i18n = get_i18n(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    subscription_service: SubscriptionService = get_subscription_service(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or db_user.is_banned:
            return _json_error(403, "access_denied", "Access denied")

        active = await subscription_service.get_active_subscription_details(session, user_id)
        panel_user_uuid = str((active or {}).get("user_id") or "").strip()
        if not active or not panel_user_uuid:
            return _json_error(400, "subscription_not_active", "Subscription is not active")

        panel_service = getattr(subscription_service, "panel_service", None)
        if not panel_service:
            return _json_error(503, "panel_unavailable", "Panel service unavailable")

        try:
            updated_panel_user, gateway_url = await reissue_subscription_access(
                session,
                panel_service,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                settings=settings,
            )
        except Exception:
            logger.exception("Failed to reissue subscription for user %s", user_id)
            updated_panel_user = None
        if not updated_panel_user:
            return _json_error(502, "subscription_reissue_failed", "Failed to reissue subscription")

        email_sent = False
        if email_recipient(settings, db_user):
            email_sent = await send_subscription_reissue_email(
                settings=settings,
                i18n=i18n,
                session=session,
                db_user=db_user,
                updated_panel_user=updated_panel_user,
                gateway_url=gateway_url,
            )

        telegram_sent = False
        telegram_id = telegram_recipient(db_user) if getattr(db_user, "telegram_id", None) else None
        if not email_sent and telegram_id is not None:
            try:
                telegram_sent = await send_subscription_reissue_telegram(
                    settings=settings,
                    i18n=i18n,
                    session=session,
                    db_user=db_user,
                    updated_panel_user=updated_panel_user,
                    gateway_url=gateway_url,
                    bot=get_bot(request),
                    telegram_id=telegram_id,
                )
            except Exception:
                logger.exception(
                    "Failed to deliver reissued subscription to Telegram user %s",
                    user_id,
                )

        await invalidate_webapp_user_caches(
            settings,
            user_id,
            include_devices=True,
            include_me=True,
        )
        await session.commit()

    logger.info(
        "User %s reissued their subscription via WebApp (email_sent=%s, telegram_sent=%s).",
        user_id,
        email_sent,
        telegram_sent,
    )
    delivery_channel = "email" if email_sent else "telegram" if telegram_sent else "app"
    return json_response(
        {
            "ok": True,
            "email_sent": bool(email_sent),
            "telegram_sent": bool(telegram_sent),
            "delivery_channel": delivery_channel,
        }
    )


def _reissue_email_text(
    i18n: JsonI18n | None,
    language: str,
    key: str,
    **kwargs: Any,
) -> str:
    if not i18n:
        return ""
    text = i18n.gettext(language, key, **kwargs)
    return "" if text == key else text


async def send_subscription_reissue_email(
    *,
    settings: Settings,
    i18n: JsonI18n | None,
    session: AsyncSession,
    db_user: Any,
    updated_panel_user: dict[str, Any],
    gateway_url: str | None = None,
) -> bool:
    raw_link = gateway_url or str(updated_panel_user.get("subscriptionUrl") or "").strip() or None
    display_link, _connect_url = await prepare_config_links(settings, raw_link)

    language = (
        str(getattr(db_user, "language_code", "") or "").strip()
        or settings.DEFAULT_LANGUAGE
        or "ru"
    )
    install_guide_url = subscription_mini_app_install_url(settings)

    message_lines = [
        _reissue_email_text(i18n, language, "email_subscription_reissue_message_intro")
    ]
    if display_link:
        message_lines.append(
            _reissue_email_text(
                i18n,
                language,
                "email_subscription_reissue_link_line",
                config_link=display_link,
            )
        )
    if install_guide_url:
        message_lines.append(
            _reissue_email_text(
                i18n,
                language,
                "email_subscription_reissue_instructions_line",
                install_guide_url=install_guide_url,
            )
        )
    message_text = "\n\n".join(line for line in message_lines if line)

    dashboard_url = install_guide_url or subscription_mini_app_path_url(settings, "/")
    cta_label_key = (
        "email_subscription_reissue_cta" if install_guide_url else "email_user_notification_cta"
    )

    return await send_user_notification_email(
        settings=settings,
        i18n=i18n,
        user=db_user,
        subject_key="email_subscription_reissue_subject",
        message_text=message_text,
        dashboard_url=dashboard_url,
        cta_label_key=cta_label_key,
        heading_key="email_subscription_reissue_heading",
        intro_key="email_subscription_reissue_intro",
        session=session,
        audit_event_type="subscription_reissue_email",
        audit_content="subscription reissue: new link and connection instructions",
    )


async def send_subscription_reissue_telegram(
    *,
    settings: Settings,
    i18n: JsonI18n | None,
    session: AsyncSession,
    db_user: Any,
    updated_panel_user: dict[str, Any],
    bot: Bot,
    telegram_id: int,
    gateway_url: str | None = None,
) -> bool:
    raw_link = gateway_url or str(updated_panel_user.get("subscriptionUrl") or "").strip() or None
    display_link, _connect_url = await prepare_config_links(settings, raw_link)
    language = (
        str(getattr(db_user, "language_code", "") or "").strip()
        or settings.DEFAULT_LANGUAGE
        or "ru"
    )
    install_guide_url = subscription_mini_app_install_url(settings)

    message_lines = [
        _reissue_email_text(i18n, language, "email_subscription_reissue_message_intro")
    ]
    if display_link:
        message_lines.append(
            _reissue_email_text(
                i18n,
                language,
                "email_subscription_reissue_link_line",
                config_link=html_escape(display_link),
            )
        )
    if install_guide_url:
        message_lines.append(
            _reissue_email_text(
                i18n,
                language,
                "email_subscription_reissue_instructions_line",
                install_guide_url=html_escape(install_guide_url),
            )
        )

    return await OutboundMessagingService(bot).send_text(
        session,
        user_id=telegram_id,
        text="\n\n".join(line for line in message_lines if line),
        event_type="subscription_reissue_telegram",
        audit_user_id=int(db_user.user_id),
        audit_content="subscription reissue: new link and connection instructions",
    )
