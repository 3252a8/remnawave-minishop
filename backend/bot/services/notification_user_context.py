"""Shared account identity and navigation for user-specific log notifications."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy import select

from bot.utils.mini_app_url import bot_start_deep_link, subscription_mini_app_path_url
from bot.utils.text_sanitizer import username_for_display
from db.dal import user_dal
from db.models import User

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

logger = logging.getLogger(__name__)

_USER_LINE_FALLBACKS = {
    "log_user_id_line": "ID: <code>{value}</code>",
    "log_user_username_line": "Telegram username: <code>{value}</code>",
    "log_user_telegram_id_line": "Telegram ID: <code>{value}</code>",
    "log_user_email_line": "Email: <code>{value}</code>",
    "log_user_name_line": "Name: {value}",
}


class NotificationUserContextMixin:
    if TYPE_CHECKING:
        settings: Settings
        i18n: JsonI18n | None
        session_factory: sessionmaker | None
        bot_username: str

    def _format_user_display(
        self,
        user_id: str,
        username: str | None = None,
        first_name: str | None = None,
        email: str | None = None,
        telegram_id: int | None = None,
    ) -> str:
        fields = [
            ("log_user_id_line", user_id if user_id != "—" else None),
            (
                "log_user_username_line",
                "@" + username_for_display(username).lstrip("@") if username else None,
            ),
            (
                "log_user_telegram_id_line",
                str(telegram_id) if telegram_id and telegram_id > 0 else None,
            ),
            ("log_user_email_line", email),
            ("log_user_name_line", first_name),
        ]
        lines = []
        for key, raw in fields:
            value = str(raw or "").strip()
            if value:
                safe_value = hd.quote(value)
                line = (
                    self.i18n.gettext(self.settings.DEFAULT_LANGUAGE, key, value=safe_value)
                    if self.i18n
                    else key
                )
                lines.append(
                    _USER_LINE_FALLBACKS[key].format(value=safe_value) if line == key else line
                )
        return "\n".join(lines)

    async def _public_user_id(self, user_id: int, known_id: str | None = None) -> str:
        if known_id:
            return known_id
        if self.session_factory is not None:
            try:
                async with self.session_factory() as session:
                    result = await session.execute(
                        select(User.minishop_id).where(User.user_id == user_id)
                    )
                    public_id = result.scalar_one_or_none()
                    if public_id:
                        return str(public_id)
            except Exception:
                logger.exception("Failed to resolve public ID for user %s.", user_id)
        return "—"

    def _build_profile_keyboard(
        self,
        translate: Callable[..., str],
        telegram_id: int | None,
        referrer_telegram_id: int | None = None,
        *,
        user_id: int | None = None,
        minishop_id: str | None = None,
        profile_button_key: str = "log_open_profile_link",
        card_button_key: str = "log_open_user_card_button",
    ) -> InlineKeyboardMarkup | None:
        buttons = []
        card_button = None
        if user_id is not None:
            reference = minishop_id if minishop_id and minishop_id != "—" else str(user_id)
            card_link = bot_start_deep_link(self.bot_username, f"admin_user_{reference}")
            if card_link is None and getattr(self.settings, "SUBSCRIPTION_MINI_APP_URL", None):
                card_link = subscription_mini_app_path_url(
                    self.settings, f"admin/users/{reference}"
                )
            card_button = (
                InlineKeyboardButton(
                    text=translate(card_button_key),
                    url=card_link,
                )
                if card_link
                else InlineKeyboardButton(
                    text=translate(card_button_key),
                    callback_data=f"admin_user_card_from_list:{user_id}:0",
                )
            )
        for identity, key in (
            (telegram_id, profile_button_key),
            (referrer_telegram_id, "log_open_referrer_profile_button"),
        ):
            if identity and identity > 0:
                buttons.append(
                    [InlineKeyboardButton(text=translate(key), url=f"tg://user?id={identity}")]
                )
        if card_button is not None:
            buttons.append([card_button])
        return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    async def _registration_inviter_context(
        self,
        translate: Callable[..., str],
        *,
        referred_by_id: int | None,
        partner_user_id: int | None,
        profile_keyboard: InlineKeyboardMarkup | None,
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        inviter_id = partner_user_id if partner_user_id is not None else referred_by_id
        if inviter_id is None:
            return "", profile_keyboard

        is_partner = partner_user_id is not None
        display, inviter_keyboard = await self._user_log_context(
            translate,
            inviter_id,
            profile_button_key=(
                "log_open_partner_profile_button"
                if is_partner
                else "log_open_referrer_profile_button"
            ),
            card_button_key=(
                "log_open_partner_card_button" if is_partner else "log_open_referrer_card_button"
            ),
        )
        text = (
            translate("log_partner_suffix", partner_link=display or "—")
            if is_partner
            else translate("log_referral_suffix", referrer_link=display or "—")
        )
        rows = list(profile_keyboard.inline_keyboard) if profile_keyboard else []
        if inviter_keyboard:
            rows.extend(inviter_keyboard.inline_keyboard)
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
        return text, keyboard

    async def _user_log_context(
        self,
        translate: Callable[..., str],
        user_id: int,
        *,
        minishop_id: str | None = None,
        username: str | None = None,
        email: str | None = None,
        telegram_id: int | None = None,
        first_name: str | None = None,
        profile_button_key: str = "log_open_profile_link",
        card_button_key: str = "log_open_user_card_button",
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        if self.session_factory is not None:
            try:
                async with self.session_factory() as session:
                    user = await user_dal.get_user_by_id(session, user_id)
                    if user is not None:
                        minishop_id = minishop_id or getattr(user, "minishop_id", None)
                        username = username or getattr(user, "username", None)
                        email = email or getattr(user, "email", None)
                        telegram_id = telegram_id or getattr(user, "telegram_id", None)
                        first_name = first_name or getattr(user, "first_name", None)
            except Exception:
                logger.exception("Failed to resolve log identity for user %s.", user_id)
        public_id = await self._public_user_id(user_id, minishop_id)
        display = self._format_user_display(public_id, username, first_name, email, telegram_id)
        keyboard = self._build_profile_keyboard(
            translate,
            telegram_id,
            user_id=user_id,
            minishop_id=public_id,
            profile_button_key=profile_button_key,
            card_button_key=card_button_key,
        )
        return display, keyboard
