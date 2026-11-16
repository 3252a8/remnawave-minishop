"""Render the account's payment history inside the Telegram chat."""

from html import escape

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.payment_providers import provider_label_map
from bot.services.telegram_account import require_telegram_account_id
from bot.utils.callback_answer import callback_message, message_from_user, safe_answer_callback
from config.settings import Settings
from db.dal.payment_history_dal import list_user_payments
from db.payment_history import active_checkout_url, payment_history_state

_PAGE_SIZE = 5
_CALLBACK = "main_action:bot_payment_history"


async def send_payment_history(
    event: types.Message | types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    page: int = 0,
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if i18n is None:
        if isinstance(event, types.CallbackQuery):
            await safe_answer_callback(event)
        return
    lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    translate = lambda key, **values: i18n.gettext(lang, key, **values)
    telegram = (
        event.from_user if isinstance(event, types.CallbackQuery) else message_from_user(event)
    )
    account_id = await require_telegram_account_id(session, telegram.id)
    payments, total = await list_user_payments(
        session, account_id, limit=_PAGE_SIZE, offset=page * _PAGE_SIZE
    )
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    if page >= pages:
        page = pages - 1
        payments, _ = await list_user_payments(
            session, account_id, limit=_PAGE_SIZE, offset=page * _PAGE_SIZE
        )

    providers = provider_label_map(settings, lang)
    lines = [f"<b>{escape(translate('menu_payment_history_button'))}</b>"]
    builder = InlineKeyboardBuilder()
    for payment in payments:
        state = payment_history_state(payment)
        provider = payment.provider or "—"
        lines.append(
            translate(
                "bot_payment_history_item",
                number=payment.payment_id,
                amount=escape(f"{payment.amount:.2f}".removesuffix(".00")),
                currency=escape(payment.currency or "—"),
                provider=escape(providers.get(provider, provider)[:80]),
                status=escape(translate(f"wa_payment_history_state_{state}")),
                date=payment.created_at.strftime("%Y-%m-%d %H:%M") if payment.created_at else "—",
            )
        )
        if url := active_checkout_url(payment, state):
            builder.row(
                types.InlineKeyboardButton(
                    text=translate("bot_payment_history_resume", number=payment.payment_id), url=url
                )
            )
    if not payments:
        lines.append(translate("wa_payment_history_empty"))
    if pages > 1:
        lines.append(translate("bot_payment_history_page", page=page + 1, pages=pages))
        nav = []
        if page:
            nav.append(
                types.InlineKeyboardButton(
                    text=translate("prev_page_button"), callback_data=f"{_CALLBACK}:{page - 1}"
                )
            )
        if page + 1 < pages:
            nav.append(
                types.InlineKeyboardButton(
                    text=translate("next_page_button"), callback_data=f"{_CALLBACK}:{page + 1}"
                )
            )
        builder.row(*nav)
    builder.row(
        types.InlineKeyboardButton(
            text=translate("back_to_main_menu_button"), callback_data="main_action:bot_interface"
        )
    )

    text = "\n\n".join(lines)
    if isinstance(event, types.CallbackQuery):
        await safe_answer_callback(event)
        await callback_message(event).edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    else:
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
