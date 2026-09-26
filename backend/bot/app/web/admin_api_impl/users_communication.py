import logging
from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_i18n, get_session_factory, get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from config.settings import Settings
from db.dal import message_log_dal, user_dal
from db.models import User

from .auth import _require_admin_user_id
from .common import _error, _ok
from .schemas import AdminUserMessageBody

logger = logging.getLogger(__name__)


async def admin_user_message_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserMessageBody)
    text = str(body.text or "").strip()
    if not text:
        return _error(400, "empty_text")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        target_user = await user_dal.get_user_by_id(session, target_id)
        if not target_user or not target_user.telegram_id:
            return _error(404, "no_telegram_account")

        try:
            await send_message_via_queue(
                queue_manager,
                int(target_user.telegram_id),
                MessageContent(content_type="text", text=text),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.warning("Admin direct message failed: %s", exc)
            return _error(502, "send_failed", str(exc))

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_direct_message_webapp",
                "content": text[:4000],
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )

    return _ok({})


async def admin_user_message_preview_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    admin_telegram_id = request.get("admin_telegram_id")
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserMessageBody)
    text = str(body.text or "").strip()
    if not text:
        return _error(400, "empty_text")
    if not admin_telegram_id:
        return _error(403, "admin_telegram_unavailable")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    try:
        await send_message_via_queue(
            queue_manager,
            int(admin_telegram_id),
            MessageContent(content_type="text", text=text),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning("Admin direct message preview failed: %s", exc)
        return _error(502, "preview_failed", str(exc))

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_direct_message_preview_webapp",
                "content": text[:4000],
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )

    return _ok({})


def _admin_user_display_name_for_message(user: User) -> str:
    full = " ".join(
        part
        for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
        if part
    ).strip()
    return (
        full
        or (f"@{user.username}" if getattr(user, "username", None) else None)
        or getattr(user, "email", None)
        or f"User #{user.user_id}"
    )


async def admin_user_telegram_profile_link_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    admin_telegram_id = request.get("admin_telegram_id")
    if not admin_telegram_id:
        return _error(403, "admin_telegram_unavailable")

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    target_id = int(request.match_info["user_id"])
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        target_user = await user_dal.get_user_by_id(session, target_id)
        if not target_user:
            return _error(404, "not_found")
        if not target_user.telegram_id:
            return _error(404, "no_telegram_account")

        admin_user = await user_dal.get_user_by_id(session, actor_id)
        lang = getattr(admin_user, "language_code", None) or settings.DEFAULT_LANGUAGE or "ru"

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_profile_link_webapp",
                "content": f"Requested Telegram profile link for user_id={target_id}",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()

    i18n_instance = get_i18n(request)
    translate = (
        (lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs))
        if i18n_instance is not None
        else (lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    )
    target_name = _admin_user_display_name_for_message(target_user)
    telegram_id = int(target_user.telegram_id)
    profile_url = f"tg://user?id={telegram_id}"
    message_text = translate(
        "admin_user_profile_link_message",
        name=html_escape(target_name),
        user_id=html_escape(str(target_user.minishop_id)),
        telegram_id=telegram_id,
    )
    if message_text == "admin_user_profile_link_message":
        message_text = (
            f"User profile: <b>{html_escape(target_name)}</b>\n"
            f"User ID: <code>{html_escape(str(target_user.minishop_id))}</code>\n"
            f"Telegram ID: <code>{telegram_id}</code>\n\n"
            "Use the button below to open the profile in Telegram."
        )

    button_text = translate("user_card_open_profile_button")
    if button_text == "user_card_open_profile_button":
        button_text = "👤 Open profile"

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=button_text, url=profile_url)]]
    )

    try:
        await send_message_via_queue(
            queue_manager,
            int(admin_telegram_id),
            MessageContent(content_type="text", text=message_text),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=markup,
        )
    except Exception as exc:
        logger.warning("Admin profile link message enqueue failed: %s", exc)
        return _error(502, "send_failed", str(exc))

    return _ok({"queued": True})
