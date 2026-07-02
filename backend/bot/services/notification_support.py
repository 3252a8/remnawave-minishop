from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.text_decorations import html_decoration as hd

from bot.services.email_templates import (
    render_support_admin_reply_user,
    render_support_new_ticket_admin,
    render_support_ticket_closed_user,
    render_support_user_reply_admin,
)
from bot.services.email_templates_common import EmailContent
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from db.dal import app_settings_dal, user_dal
from db.models import SupportTicket, SupportTicketMessage, User

if TYPE_CHECKING:
    from bot.middlewares.i18n import JsonI18n
    from bot.services.email_auth_service import EmailAuthService
    from config.settings import Settings

SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_KEY = "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED"


class NotificationSupportMixin:
    if TYPE_CHECKING:
        settings: Settings
        i18n: JsonI18n | None
        session_factory: Any
        email_auth_service: EmailAuthService | None
        bot_username: str
        bot: Bot

        async def _send_to_admins(
            self,
            message: str,
            reply_markup: InlineKeyboardMarkup | None = None,
        ) -> None: ...

        async def _send_to_log_channel(
            self,
            message: str,
            thread_id: int | None = None,
            reply_markup: InlineKeyboardMarkup | None = None,
        ) -> None: ...

    def _support_webapp_url(self, path: str) -> str | None:
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

    def _support_text(self, language: str | None, key: str, fallback: str) -> str:
        if not self.i18n:
            return fallback
        return self.i18n.gettext(language or self.settings.DEFAULT_LANGUAGE, key) or fallback

    @staticmethod
    def _support_preview(body: str, limit: int = 700) -> str:
        text = (body or "").strip()
        return text if len(text) <= limit else f"{text[: limit - 1]}…"

    @staticmethod
    def _support_user_display(user: User) -> str:
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
    def _support_snapshot_rows(snapshot: dict[str, object] | None) -> list[tuple[str, str]]:
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
        ticket: SupportTicket,
        user: User,
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

    def _support_log_thread_id(self) -> int | None:
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

    def _support_user_keyboard(self, ticket: SupportTicket, user: User) -> InlineKeyboardMarkup:
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

    async def _admin_email_users(self) -> list[User]:
        if not self.session_factory:
            return []
        async with self.session_factory() as session:
            users = []
            for admin_id in self.settings.ADMIN_IDS:
                user = await user_dal.get_user_by_id(session, int(admin_id))
                if user and user.email:
                    users.append(user)
            return users

    async def _send_admin_support_email(
        self, renderer: Callable[..., EmailContent], **kwargs: object
    ) -> None:
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

    async def notify_new_support_ticket(
        self,
        ticket: SupportTicket,
        user: User,
        first_message: str,
        snapshot: dict[str, object],
    ) -> None:
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
        ticket: SupportTicket,
        message: SupportTicketMessage,
        user: User,
        snapshot: dict[str, object],
        *,
        unread_count: int | None = None,
        send_telegram: bool = True,
        send_email: bool = True,
    ) -> None:
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

    async def notify_support_admin_reply(
        self, ticket: SupportTicket, message: SupportTicketMessage, user: User
    ) -> None:
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

    async def notify_support_ticket_closed(
        self, ticket: SupportTicket, user: User, closing_admin: User | None
    ) -> None:
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
