"""Render a blacklist alert in the style of the Minishop registration log."""

from datetime import UTC, datetime
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.plugins.spec import PluginContext
from bot.utils.mini_app_url import bot_start_deep_link, subscription_mini_app_path_url
from db.models import User

from .localization import plugin_i18n
from .settings import EventName
from .storage import Match


def render_alert(
    ctx: PluginContext, event: EventName, user: User, telegram_id: int, match: Match
) -> tuple[str, InlineKeyboardMarkup]:
    lang = (ctx.settings.DEFAULT_LANGUAGE or "ru").lower().split("-")[0]
    catalog = plugin_i18n(ctx)

    def text(key: str) -> str:
        return catalog.gettext(lang, f"admin_minishop_blacklist_alert_{key}")

    user_id = str(user.minishop_id or user.user_id)
    lines = [
        f"👤 <b>{text('title')}</b>",
        "",
        f"<b>{text(event)}</b>",
        f"ID: <code>{escape(user_id)}</code>",
        f"Telegram ID: <code>{telegram_id}</code>",
    ]
    if user.username:
        username = escape(str(user.username).lstrip("@")[:80])
        lines.append(f"{text('username')}: <code>@{username}</code>")
    name = " ".join(value for value in (user.first_name, user.last_name) if value)
    if name:
        lines.append(f"{text('name')}: {escape(name[:160])}")
    reasons = "\n".join(
        f"• {reason.text or ', '.join(reason.links)}"
        for reason in match.reasons
        if reason.text or reason.links
    )
    if reasons:
        lines.extend(("", f"<b>{text('reasons')}</b>", escape(reasons[:2200])))
        if len(reasons) > 2200:
            lines.append(text("more"))
    if match.stale:
        lines.append(f"<i>{text('stale')}</i>")
    lines.extend(("", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")))

    notifier = ctx.notification_service
    bot_username = notifier.bot_username if notifier is not None else None
    card_url = bot_start_deep_link(bot_username, f"admin_user_{user_id}")
    if card_url is None:
        card_url = subscription_mini_app_path_url(ctx.settings, f"admin/users/{user_id}")
    card = (
        InlineKeyboardButton(text=text("card"), url=card_url)
        if card_url
        else InlineKeyboardButton(
            text=text("card"), callback_data=f"admin_user_card_from_list:{user.user_id}:0"
        )
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text("profile"), url=f"tg://user?id={telegram_id}")],
            [card],
        ]
    )
    return "\n".join(lines), keyboard
