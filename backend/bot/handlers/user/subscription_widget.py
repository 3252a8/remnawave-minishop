import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from html import escape

from aiogram import Bot, F, types
from aiogram.exceptions import TelegramBadRequest, TelegramNotFound
from aiogram.filters import Command
from aiogram.methods import TelegramMethod
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import message_from_user
from bot.utils.mini_app_url import bot_start_deep_link
from config.settings import Settings
from db.dal import user_dal

from .start_common import router

logger = logging.getLogger(__name__)

CONNECT_START = "widget_connect"
RENEW_START = "widget_renew"

_CARD_STYLE = """
<style>
main{padding:12px;color:var(--tg-theme-text-color)}
h3{margin:0 0 10px}
p{margin:4px 0}
small{color:var(--tg-theme-hint-color)}
nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
nav a{flex:1 0 auto;text-align:center;padding:12px 8px;border-radius:10px;
text-decoration:none;color:var(--tg-theme-link-color);
border:1px solid var(--tg-theme-link-color)}
nav a.primary{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color);
border-color:var(--tg-theme-button-color)}
</style>
"""

_STATUS_KEYS = {
    "ACTIVE": "status_active",
    "TRIAL": "subscription_widget_status_trial",
    "EXPIRED": "subscription_widget_status_expired",
    "DISABLED": "subscription_widget_status_disabled",
    "LIMITED": "subscription_widget_status_limited",
}


class SendSubscriptionWidget(TelegramMethod[types.Message]):
    """Send a Bot API 10.4 widget through the configured aiogram session."""

    __api_method__ = "sendWidget"
    __returning__ = types.Message

    chat_id: int
    html: str
    caption: str
    reply_markup: types.InlineKeyboardMarkup
    message_thread_id: int | None = None


def _traffic_size(value: object, i18n: JsonI18n, language: str) -> str:
    if isinstance(value, (int, float)):
        return i18n.gettext(language, "subscription_widget_gib", amount=f"{value / 2**30:.2f}")
    return i18n.gettext(language, "traffic_na")


def _subscription_summary(
    active: Mapping[str, object] | None, i18n: JsonI18n, language: str
) -> tuple[str, str, str]:
    if active is None:
        return (
            i18n.gettext(language, "subscription_widget_status_inactive"),
            "—",
            "—",
        )

    status_key = _STATUS_KEYS.get(
        str(active.get("status_from_panel")).upper(), "subscription_widget_status_unknown"
    )
    end_date = active.get("end_date")
    limit = active.get("traffic_limit_bytes")
    used = _traffic_size(active.get("traffic_used_bytes"), i18n, language)
    traffic = i18n.gettext(
        language,
        "subscription_widget_traffic_usage",
        used=used,
        limit=(
            i18n.gettext(language, "traffic_unlimited")
            if limit == 0
            else _traffic_size(limit, i18n, language)
        ),
    )
    return (
        i18n.gettext(language, status_key),
        end_date.date().isoformat() if isinstance(end_date, datetime) else "—",
        traffic,
    )


@router.message(Command("widget"), F.chat.type == "private")
async def subscription_widget_command(
    message: types.Message,
    bot: Bot,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    if not settings.TELEGRAM_SUBSCRIPTION_WIDGET_ENABLED:
        return
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if i18n is None:
        return

    language = i18n_data.get("current_language") or settings.DEFAULT_LANGUAGE
    text = lambda key, **kwargs: i18n.gettext(language, key, **kwargs)
    user = await user_dal.get_user_by_telegram_id(session, message_from_user(message).id)
    if user is None:
        await message.answer(text("subscription_widget_start_required"))
        return

    active = await subscription_service.get_active_subscription_details(session, user.user_id)
    status, end_date, traffic = _subscription_summary(active, i18n, language)
    title = text("subscription_widget_title")
    rows = [
        text("subscription_widget_status", value=status),
        text("subscription_widget_expiry", value=end_date),
        text("subscription_widget_traffic", value=traffic),
    ]
    updated = text("subscription_widget_updated", time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"))
    caption = "\n".join((title, *rows, updated))
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=text("subscription_widget_menu"),
                    callback_data="main_action:back_to_main_keep",
                )
            ]
        ]
    )

    username = (await bot.me()).username
    renew_url = bot_start_deep_link(username, RENEW_START)
    if not renew_url:
        await message.answer(caption, parse_mode=None, reply_markup=markup)
        return

    connect_url = bot_start_deep_link(username, CONNECT_START) if active else None
    renew_label = text("subscription_widget_renew" if active else "subscription_widget_buy")
    buttons = []
    if connect_url:
        buttons.append(
            f'<a class="primary" href="{escape(connect_url)}">'
            f"{escape(text('subscription_widget_connect'))}</a>"
        )
    buttons.append(f'<a href="{escape(renew_url)}">{escape(renew_label)}</a>')
    html = (
        f"{_CARD_STYLE}<main><h3>{escape(title)}</h3>"
        + "".join(f"<p>{escape(row)}</p>" for row in rows)
        + f"<small>{escape(updated)}</small><nav>{''.join(buttons)}</nav></main>"
    )

    try:
        await bot(
            SendSubscriptionWidget(
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id if message.is_topic_message else None,
                html=html,
                caption=caption,
                reply_markup=markup,
            )
        )
    except (TelegramBadRequest, TelegramNotFound) as exc:
        logger.info("Telegram rejected the subscription widget (%s)", type(exc).__name__)
        await message.answer(caption, parse_mode=None, reply_markup=markup)
