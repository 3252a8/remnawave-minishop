import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.text_decorations import html_decoration as hd

from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import (
    render_support_admin_reply_user,
    render_support_new_ticket_admin,
    render_support_ticket_closed_user,
    render_support_user_reply_admin,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from bot.utils.telegram_markup import (
    is_profile_link_error,
    remove_profile_link_buttons,
)
from bot.utils.text_sanitizer import (
    display_name_or_fallback,
    username_for_display,
)
from config.settings import Settings
from db.dal import app_settings_dal, user_dal

SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_KEY = "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED"


class NotificationService:
    """Enhanced notification service for sending messages to admins and log channels"""

    def __init__(
        self,
        bot: Bot,
        settings: Settings,
        i18n: Optional[JsonI18n] = None,
        *,
        session_factory=None,
        email_auth_service: Optional[EmailAuthService] = None,
        bot_username: Optional[str] = None,
    ):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.session_factory = session_factory
        self.email_auth_service = email_auth_service
        self.bot_username = bot_username or ""

    @staticmethod
    def _format_user_display(
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> str:
        base_display = display_name_or_fallback(first_name, f"ID {user_id}")
        if username:
            base_display = f"{base_display} ({username_for_display(username)})"
        safe_display = hd.quote(base_display)
        clean_email = str(email or "").strip()
        if clean_email:
            safe_display = f"{safe_display} · <code>{hd.quote(clean_email)}</code>"
        return safe_display

    @staticmethod
    def _build_profile_keyboard(
        translate: Callable[..., str],
        user_id: int,
        referrer_id: Optional[int] = None,
    ) -> InlineKeyboardMarkup:
        """Create inline keyboard with links to user (and referrer) profiles.

        Email-only users have a synthetic negative ``user_id`` with no
        Telegram profile, so we skip the tg:// button for them.
        """
        buttons = []
        if user_id and user_id > 0:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=translate("log_open_profile_link"),
                        url=f"tg://user?id={user_id}",
                    )
                ]
            )

        if referrer_id and referrer_id > 0:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=translate("log_open_referrer_profile_button"),
                        url=f"tg://user?id={referrer_id}",
                    )
                ]
            )

        return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    async def _send_to_log_channel(
        self,
        message: str,
        thread_id: Optional[int] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ):
        """Send message to configured log channel/group using message queue"""
        if not self.settings.LOG_CHAT_ID:
            return

        queue_manager = get_queue_manager()
        if not queue_manager:
            logging.warning("Message queue manager not available, falling back to direct send")
            final_thread_id = thread_id or self.settings.LOG_THREAD_ID

            def _build_kwargs(markup: Optional[InlineKeyboardMarkup]) -> Dict[str, Any]:
                kwargs: Dict[str, Any] = {
                    "chat_id": self.settings.LOG_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
                if markup:
                    kwargs["reply_markup"] = markup
                if final_thread_id:
                    kwargs["message_thread_id"] = final_thread_id
                return kwargs

            try:
                await self.bot.send_message(**_build_kwargs(reply_markup))
            except TelegramBadRequest as exc:
                if is_profile_link_error(exc):
                    fallback_markup = remove_profile_link_buttons(reply_markup)
                    logging.warning(
                        "Telegram rejected profile buttons for log chat %s: %s. "
                        "Retrying without tg:// links.",
                        self.settings.LOG_CHAT_ID,
                        getattr(exc, "message", "") or str(exc),
                    )
                    try:
                        await self.bot.send_message(**_build_kwargs(fallback_markup))
                    except Exception as retry_exc:
                        logging.error(
                            "Failed to send notification without profile buttons to log "
                            f"channel {self.settings.LOG_CHAT_ID}: {retry_exc}"
                        )
                    return
                logging.error(
                    f"Failed to send notification to log channel {self.settings.LOG_CHAT_ID}: {exc}"
                )
            except Exception:
                logging.exception(
                    "Failed to send notification to log channel %s.", self.settings.LOG_CHAT_ID
                )
            return

        try:
            # Use thread_id if provided, otherwise use from settings
            final_thread_id = thread_id or self.settings.LOG_THREAD_ID

            kwargs = {"text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
            if reply_markup:
                kwargs["reply_markup"] = reply_markup

            # Add thread ID for supergroups if specified
            if final_thread_id:
                kwargs["message_thread_id"] = final_thread_id

            # Queue message for sending (groups are rate limited to 15/minute)
            await queue_manager.send_message(self.settings.LOG_CHAT_ID, **kwargs)

        except Exception:
            logging.exception(
                "Failed to queue notification to log channel %s.", self.settings.LOG_CHAT_ID
            )

    async def _send_to_admins(
        self,
        message: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ):
        """Send message to all admin users using message queue"""
        if not self.settings.ADMIN_IDS:
            return

        queue_manager = get_queue_manager()
        if not queue_manager:
            logging.warning("Message queue manager not available, falling back to direct send")
            for admin_id in self.settings.ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                    )
                except Exception:
                    logging.exception("Failed to send notification to admin %s.", admin_id)
            return

        for admin_id in self.settings.ADMIN_IDS:
            try:
                await queue_manager.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )
            except Exception:
                logging.exception("Failed to queue notification to admin %s.", admin_id)

    def _support_webapp_url(self, path: str) -> Optional[str]:
        base_url = str(getattr(self.settings, "SUBSCRIPTION_MINI_APP_URL", "") or "").strip()
        if not base_url:
            return None
        normalized_path = f"/{str(path or '').lstrip('/')}"
        return f"{base_url.rstrip('/')}{normalized_path}"

    def _support_ticket_url(self, ticket_id: int, *, admin: bool = True) -> str:
        path = f"/admin/support/{ticket_id}" if admin else f"/support/{ticket_id}"
        webapp_url = self._support_webapp_url(path)
        if webapp_url:
            return webapp_url
        bot_username = self.bot_username.strip().lstrip("@")
        if bot_username:
            return f"https://t.me/{bot_username}?startapp=ticket_{ticket_id}"
        return "https://t.me/"

    def _support_mini_app_button(
        self,
        *,
        text: str,
        path: str,
        fallback_url: str,
        web_app_button: bool = True,
    ) -> InlineKeyboardButton:
        webapp_url = self._support_webapp_url(path)
        if webapp_url and web_app_button:
            return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url))
        return InlineKeyboardButton(text=text, url=webapp_url or fallback_url)

    def _support_text(self, language: Optional[str], key: str, fallback: str) -> str:
        if not self.i18n:
            return fallback
        return self.i18n.gettext(language or self.settings.DEFAULT_LANGUAGE, key) or fallback

    @staticmethod
    def _support_preview(body: str, limit: int = 700) -> str:
        text = (body or "").strip()
        return text if len(text) <= limit else f"{text[: limit - 1]}…"

    @staticmethod
    def _support_user_display(user) -> str:
        name = " ".join(
            part for part in [user.first_name, getattr(user, "last_name", None)] if part
        )
        if user.username:
            display = f"{name or user.username} (@{user.username})"
        else:
            display = name or f"ID {user.user_id}"
        email = str(getattr(user, "email", None) or "").strip()
        if email:
            return f"{display} · {email}" if display and display != email else email
        return display

    @staticmethod
    def _support_snapshot_rows(snapshot: Optional[dict]) -> list[tuple[str, str]]:
        if not snapshot:
            return []
        rows = []
        for key, label in (
            ("tariff", "email_support_row_tariff"),
            ("end_date", "email_support_row_end_date"),
            ("remaining", "email_support_row_remaining"),
            ("panel_status", "email_support_row_panel_status"),
        ):
            value = snapshot.get(key)
            if value:
                rows.append((label, str(value)))
        return rows

    @staticmethod
    def _coerce_bool_setting(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return bool(value)

    async def support_admin_email_notifications_enabled(self) -> bool:
        enabled = bool(getattr(self.settings, SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_KEY, False))
        if not self.session_factory:
            return enabled
        try:
            async with self.session_factory() as session:
                found, raw_value = await app_settings_dal.get_override_value(
                    session,
                    SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_KEY,
                )
        except Exception:
            logging.exception("Failed to read support admin email notification override.")
            return enabled
        if not found:
            return enabled
        return self._coerce_bool_setting(raw_value, enabled)

    def _support_keyboard(
        self,
        ticket,
        user,
        *,
        admin: bool = True,
        web_app_buttons: bool = True,
    ) -> InlineKeyboardMarkup:
        ticket_path = (
            f"/admin/support/{ticket.ticket_id}" if admin else f"/support/{ticket.ticket_id}"
        )
        rows = [
            [
                self._support_mini_app_button(
                    text="Открыть тикет",
                    path=ticket_path,
                    fallback_url=self._support_ticket_url(ticket.ticket_id, admin=admin),
                    web_app_button=web_app_buttons,
                )
            ]
        ]
        if admin:
            profile_row = []
            if getattr(user, "user_id", 0) and int(user.user_id) > 0:
                profile_row.append(
                    InlineKeyboardButton(text="Профиль", url=f"tg://user?id={user.user_id}")
                )
            user_card_path = f"/admin/users/{user.user_id}"
            if self._support_webapp_url(user_card_path):
                profile_row.append(
                    self._support_mini_app_button(
                        text="Карточка пользователя",
                        path=user_card_path,
                        fallback_url=self._support_ticket_url(ticket.ticket_id, admin=True),
                        web_app_button=web_app_buttons,
                    )
                )
            if profile_row:
                rows.append(profile_row)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _support_log_thread_id(self) -> Optional[int]:
        return getattr(self.settings, "LOG_SUPPORT_THREAD_ID", None)

    def _support_thread_is_configured(self) -> bool:
        return bool(getattr(self.settings, "LOG_CHAT_ID", None) and self._support_log_thread_id())

    async def _send_admin_support_telegram(
        self,
        message: str,
        *,
        admin_markup: InlineKeyboardMarkup,
        log_markup: InlineKeyboardMarkup,
    ) -> None:
        thread_id = self._support_log_thread_id()
        if not self._support_thread_is_configured():
            await self._send_to_admins(message, reply_markup=admin_markup)
        await self._send_to_log_channel(
            message,
            thread_id=thread_id,
            reply_markup=log_markup,
        )

    def _support_user_keyboard(self, ticket, user) -> InlineKeyboardMarkup:
        button_text = self._support_text(
            getattr(user, "language_code", None),
            "wa_support_open_ticket",
            "Открыть тикет",
        )
        webapp_url = self._support_webapp_url(f"/support/{ticket.ticket_id}")
        if webapp_url:
            button = InlineKeyboardButton(text=button_text, web_app=WebAppInfo(url=webapp_url))
        else:
            button = InlineKeyboardButton(
                text=button_text,
                url=self._support_ticket_url(ticket.ticket_id, admin=False),
            )
        return InlineKeyboardMarkup(inline_keyboard=[[button]])

    async def _admin_email_users(self):
        if not self.session_factory:
            return []
        async with self.session_factory() as session:
            users = []
            for admin_id in self.settings.ADMIN_IDS:
                user = await user_dal.get_user_by_id(session, int(admin_id))
                if user and user.email:
                    users.append(user)
            return users

    async def _send_admin_support_email(self, renderer, **kwargs) -> None:
        if not await self.support_admin_email_notifications_enabled():
            return
        if not self.email_auth_service:
            return
        for admin in await self._admin_email_users():
            try:
                content = renderer(
                    self.settings,
                    self.i18n,
                    getattr(admin, "language_code", None) or self.settings.DEFAULT_LANGUAGE,
                    **kwargs,
                )
                await self.email_auth_service.send_rendered_email(
                    email=admin.email,
                    content=content,
                )
            except Exception:
                logging.exception("Failed to send support email to admin %s.", admin.user_id)

    async def notify_new_support_ticket(self, ticket, user, first_message: str, snapshot: dict):
        if not getattr(self.settings, "LOG_SUPPORT", True):
            return
        priority_emoji = {"low": "🟢", "normal": "🟡", "high": "🟠", "urgent": "🔴"}.get(
            ticket.priority,
            "🟡",
        )
        preview = self._support_preview(first_message)
        user_display = self._support_user_display(user)
        message = (
            f"🆘 <b>Новый тикет #{ticket.ticket_id}</b>\n"
            f"{priority_emoji} <b>{hd.quote(ticket.priority)}</b> · {hd.quote(ticket.category)}\n\n"
            f"<b>Пользователь</b>\n{hd.quote(user_display)}\nID: <code>{user.user_id}</code>\n\n"
            f"<b>Подписка</b>\n"
            f"{hd.quote(str(snapshot.get('tariff') or '—'))}, "
            f"до {hd.quote(str(snapshot.get('end_date') or '—'))}, "
            f"осталось {hd.quote(str(snapshot.get('remaining') or '—'))}\n"
            f"статус: {hd.quote(str(snapshot.get('panel_status') or '—'))}\n\n"
            f"<b>Текст обращения</b>\n{hd.quote(preview)}"
        )
        admin_keyboard = self._support_keyboard(ticket, user, admin=True)
        log_keyboard = self._support_keyboard(ticket, user, admin=True, web_app_buttons=False)
        await self._send_admin_support_telegram(
            message,
            admin_markup=admin_keyboard,
            log_markup=log_keyboard,
        )
        await self._send_admin_support_email(
            render_support_new_ticket_admin,
            ticket_id=ticket.ticket_id,
            user_display=user_display,
            subject=ticket.subject,
            body_preview=preview,
            snapshot_rows=self._support_snapshot_rows(snapshot),
            ticket_url=self._support_ticket_url(ticket.ticket_id, admin=True),
        )

    async def notify_support_user_reply(
        self,
        ticket,
        message,
        user,
        snapshot: dict,
        *,
        unread_count: Optional[int] = None,
        send_telegram: bool = True,
        send_email: bool = True,
    ):
        if not getattr(self.settings, "LOG_SUPPORT", True):
            return
        preview = self._support_preview(message.body)
        user_display = self._support_user_display(user)
        unread_line = (
            f"\n<b>Unread:</b> {int(unread_count)}"
            if unread_count is not None and int(unread_count or 0) > 1
            else ""
        )
        text = (
            f"💬 <b>Ответ пользователя в тикете #{ticket.ticket_id}</b>\n"
            f"{hd.quote(user_display)}{unread_line}\n\n{hd.quote(preview)}"
        )
        if send_telegram and getattr(self.settings, "LOG_SUPPORT", True):
            admin_keyboard = self._support_keyboard(ticket, user, admin=True)
            log_keyboard = self._support_keyboard(ticket, user, admin=True, web_app_buttons=False)
            await self._send_admin_support_telegram(
                text,
                admin_markup=admin_keyboard,
                log_markup=log_keyboard,
            )
        if send_email:
            await self._send_admin_support_email(
                render_support_user_reply_admin,
                ticket_id=ticket.ticket_id,
                user_display=user_display,
                subject=ticket.subject,
                body_preview=preview,
                snapshot_rows=self._support_snapshot_rows(snapshot),
                ticket_url=self._support_ticket_url(ticket.ticket_id, admin=True),
            )

    async def notify_support_admin_reply(self, ticket, message, user):
        preview = self._support_preview(message.body, limit=500)
        url = self._support_ticket_url(ticket.ticket_id, admin=False)
        text = f"💬 <b>Новый ответ по тикету #{ticket.ticket_id}</b>\n\n{hd.quote(preview)}"
        keyboard = self._support_user_keyboard(ticket, user)
        if int(user.user_id) > 0:
            queue_manager = get_queue_manager()
            if queue_manager:
                await send_message_via_queue(
                    queue_manager,
                    int(user.user_id),
                    MessageContent(content_type="text", text=text),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=keyboard,
                )
            else:
                await self.bot.send_message(
                    chat_id=int(user.user_id),
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=keyboard,
                )
        if self.email_auth_service and getattr(user, "email", None):
            content = render_support_admin_reply_user(
                self.settings,
                self.i18n,
                getattr(user, "language_code", None),
                ticket_id=ticket.ticket_id,
                subject=ticket.subject,
                body_preview=preview,
                ticket_url=url,
            )
            await self.email_auth_service.send_rendered_email(email=user.email, content=content)

    async def notify_support_ticket_closed(self, ticket, user, closing_admin):
        url = self._support_ticket_url(ticket.ticket_id, admin=False)
        text = f"✅ <b>Тикет #{ticket.ticket_id} закрыт</b>\n\n{hd.quote(ticket.subject)}"
        keyboard = self._support_user_keyboard(ticket, user)
        if int(user.user_id) > 0:
            queue_manager = get_queue_manager()
            if queue_manager:
                await send_message_via_queue(
                    queue_manager,
                    int(user.user_id),
                    MessageContent(content_type="text", text=text),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=keyboard,
                )
            else:
                await self.bot.send_message(
                    chat_id=int(user.user_id),
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=keyboard,
                )
        if self.email_auth_service and getattr(user, "email", None):
            content = render_support_ticket_closed_user(
                self.settings,
                self.i18n,
                getattr(user, "language_code", None),
                ticket_id=ticket.ticket_id,
                subject=ticket.subject,
                ticket_url=url,
            )
            await self.email_auth_service.send_rendered_email(email=user.email, content=content)

    async def notify_new_user_registration(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        email: Optional[str] = None,
        referred_by_id: Optional[int] = None,
    ):
        """Send notification about new user registration"""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        referral_text = ""
        if referred_by_id:
            referrer_link = hd.link(str(referred_by_id), f"tg://user?id={referred_by_id}")
            referral_text = _(
                "log_referral_suffix",
                referrer_link=referrer_link,
            )

        message = _(
            "log_new_user_registration",
            user_id=user_id,
            user_display=user_display,
            referral_text=referral_text,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id, referred_by_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_new_email_user_registration(
        self,
        user_id: int,
        email: str,
        referred_by_id: Optional[int] = None,
    ):
        """Send notification about new user registration via email (Web App)."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        referral_text = ""
        if referred_by_id:
            referrer_link = hd.link(str(referred_by_id), f"tg://user?id={referred_by_id}")
            referral_text = _(
                "log_referral_suffix",
                referrer_link=referrer_link,
            )

        message = _(
            "log_new_email_user_registration",
            user_id=user_id,
            email=hd.quote(email),
            referral_text=referral_text,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Email users have a synthetic (negative) user_id with no Telegram profile,
        # so we only attach the referrer button when a real referrer is present.
        reply_markup: Optional[InlineKeyboardMarkup] = None
        if referred_by_id and referred_by_id > 0:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("log_open_referrer_profile_button"),
                            url=f"tg://user?id={referred_by_id}",
                        )
                    ]
                ]
            )

        await self._send_to_log_channel(message, reply_markup=reply_markup)

    async def notify_account_email_linked(
        self,
        user_id: int,
        email: str,
        telegram_id: Optional[int] = None,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ):
        """Send notification when an email is linked to a Telegram-created account."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=telegram_id or user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_account_email_linked",
            user_id=user_id,
            telegram_id=telegram_id or user_id,
            user_display=user_display,
            email=hd.quote(email),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        reply_markup: Optional[InlineKeyboardMarkup] = None
        if telegram_id and telegram_id > 0:
            reply_markup = self._build_profile_keyboard(_, telegram_id)

        await self._send_to_log_channel(message, reply_markup=reply_markup)

    async def notify_account_telegram_linked(
        self,
        user_id: int,
        email: Optional[str],
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ):
        """Send notification when Telegram is linked to an email-created account."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=telegram_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_account_telegram_linked",
            user_id=user_id,
            telegram_id=telegram_id,
            user_display=user_display,
            email=hd.quote(email or ""),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        profile_keyboard = self._build_profile_keyboard(_, telegram_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_account_merged(
        self,
        *,
        primary_user_id: int,
        removed_user_id: int,
        email: Optional[str],
        telegram_id: Optional[int],
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        final_end_date_text: Optional[str] = None,
        primary_panel_user_uuid: Optional[str] = None,
        removed_panel_user_uuid: Optional[str] = None,
    ):
        """Send notification when duplicate email/Telegram accounts are merged."""
        if not self.settings.LOG_NEW_USERS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        display_user_id = int(telegram_id or primary_user_id)
        user_display = self._format_user_display(
            user_id=display_user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_account_merged",
            primary_user_id=primary_user_id,
            removed_user_id=removed_user_id,
            telegram_id=telegram_id or "",
            user_display=user_display,
            email=hd.quote(email or ""),
            final_end_date=hd.quote(final_end_date_text or ""),
            primary_panel_user_uuid=hd.quote(primary_panel_user_uuid or ""),
            removed_panel_user_uuid=hd.quote(removed_panel_user_uuid or ""),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        profile_keyboard = (
            self._build_profile_keyboard(_, int(telegram_id)) if telegram_id else None
        )
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    def _format_traffic_gb_admin(self, traffic_gb: float) -> str:
        value = float(traffic_gb)
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"

    def _tariff_display_for_log(self, tariff_key: Optional[str]) -> str:
        if not tariff_key:
            return ""
        cfg = getattr(self.settings, "tariffs_config", None)
        if not cfg:
            return str(tariff_key)
        try:
            tariff = cfg.require(str(tariff_key))
            return str(tariff.name(self.settings.DEFAULT_LANGUAGE))
        except Exception:
            return str(tariff_key)

    async def notify_payment_received(
        self,
        user_id: int,
        amount: float,
        currency: str,
        months: int,
        payment_provider: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        traffic_gb: Optional[float] = None,
        *,
        traffic_is_premium: bool = False,
        tariff_key: Optional[str] = None,
    ):
        """Send notification about successful payment"""
        if not self.settings.LOG_PAYMENTS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            email=email,
        )

        try:
            from bot.payment_providers import provider_emoji_map

            provider_emoji = provider_emoji_map(self.settings).get(payment_provider.lower(), "💰")
        except Exception:
            provider_emoji = "💰"

        if traffic_gb is not None:
            traffic_label = self._format_traffic_gb_admin(float(traffic_gb))
            traffic_kind = _(
                "log_payment_traffic_kind_premium"
                if traffic_is_premium
                else "log_payment_traffic_kind_regular",
            )
            traffic_summary = _(
                "log_payment_traffic_purchase_line", gb=traffic_label, kind=traffic_kind
            )
            tariff_name = self._tariff_display_for_log(tariff_key)
            tariff_line = (
                _("log_payment_tariff_line", name=hd.quote(tariff_name)) if tariff_name else ""
            )
            message = _(
                "log_payment_received_traffic",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                traffic_summary=traffic_summary,
                tariff_line=tariff_line,
                payment_provider=payment_provider,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            message = _(
                "log_payment_received",
                provider_emoji=provider_emoji,
                user_display=user_display,
                amount=amount,
                currency=currency,
                months=months,
                payment_provider=payment_provider,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_promo_activation(
        self,
        user_id: int,
        promo_code: str,
        bonus_days: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ):
        """Send notification about promo code activation"""
        if not self.settings.LOG_PROMO_ACTIVATIONS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            email=email,
        )

        message = _(
            "log_promo_activation",
            user_display=user_display,
            promo_code=promo_code,
            bonus_days=bonus_days,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_trial_activation(
        self,
        user_id: int,
        end_date: datetime,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ):
        """Send notification about trial activation"""
        if not self.settings.LOG_TRIAL_ACTIVATIONS:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            email=email,
        )

        message = _(
            "log_trial_activation",
            user_display=user_display,
            end_date=end_date.strftime("%Y-%m-%d %H:%M"),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_panel_sync(
        self,
        status: str,
        details: str,
        users_processed: int,
        subs_synced: int,
        username: Optional[str] = None,
    ):
        """Send notification about panel synchronization"""
        if not getattr(self.settings, "LOG_PANEL_SYNC", True):
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        # Status emoji based on sync result
        status_emoji = {"completed": "✅", "completed_with_errors": "⚠️", "failed": "❌"}.get(
            status, "🔄"
        )

        message = _(
            "log_panel_sync",
            status_emoji=status_emoji,
            status=status,
            users_processed=users_processed,
            subs_synced=subs_synced,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
            details=details,
        )

        # Send to log channel
        await self._send_to_log_channel(message)

    async def notify_suspicious_promo_attempt(
        self,
        user_id: int,
        suspicious_input: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        email: Optional[str] = None,
    ):
        """Send notification about a suspicious promo code attempt."""
        if not self.settings.LOG_SUSPICIOUS_ACTIVITY:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            first_name=first_name,
            email=email,
        )

        message = _(
            "log_suspicious_promo",
            user_display=user_display,
            user_id=user_id,
            suspicious_input=hd.quote(suspicious_input),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def send_custom_notification(
        self,
        message: str,
        to_admins: bool = False,
        to_log_channel: bool = True,
        thread_id: Optional[int] = None,
    ):
        """Send custom notification message"""
        if to_log_channel:
            await self._send_to_log_channel(message, thread_id)
        if to_admins:
            await self._send_to_admins(message)


# Removed legacy helper functions that duplicated NotificationService API
