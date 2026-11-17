from collections.abc import Awaitable, Callable
from secrets import token_urlsafe
from typing import Any

from aiogram import BaseMiddleware
from aiogram.client.default import Default
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject

from bot.utils.callback_answer import safe_answer_callback

_PREFIX = "confirm:"
_DRAFT = "telegram_confirmation"
_DEFAULT_PARSE_MODE = Default("parse_mode")
_ACTIONS = (
    "autorenew:confirm:",
    "tariff_change:apply:",
    "tariff_change:pay:",
    "pm:delete:",
    "pay_yk_use_saved:",
    "admin_ads:delete_confirm:",
    "user_action:set_tariff:",
    "promo_delete_confirm:",
)
_EXACT_ACTIONS = {
    "trial_action:confirm_activate",
    "broadcast_final_action:send",
    "promo_unlimited_validity",
    "bulk_promo_unlimited_validity",
}
_DRAFT_CONTROLS = (
    "broadcast_target:",
    "broadcast_final_action:cancel",
    "promo_set_validity",
    "bulk_promo_set_validity",
)


def _requires_confirmation(action: str) -> bool:
    return action in _EXACT_ACTIONS or action.startswith(_ACTIONS)


async def protect_confirmation(
    state: FSMContext | None, markup: InlineKeyboardMarkup, *, message_id: int | None = None
) -> InlineKeyboardMarkup:
    """Issue one-use callback tokens for the current chat's confirmation."""
    if state is None:
        return markup
    actions: dict[str, str] = {}
    protected = markup.model_copy(deep=True)
    for row in protected.inline_keyboard:
        for button in row:
            action = button.callback_data
            if action and _requires_confirmation(action):
                token = token_urlsafe(12)
                actions[token] = action
                button.callback_data = f"{_PREFIX}{token}"
    await state.update_data(**{_DRAFT: {"message_id": message_id, "actions": actions}})
    return protected


async def bind_confirmation_message(state: FSMContext | None, message_id: int) -> None:
    if state is None:
        return
    draft = (await state.get_data()).get(_DRAFT)
    if draft:
        await state.update_data(**{_DRAFT: {**draft, "message_id": message_id}})


async def answer_confirmation(
    message: Message,
    state: FSMContext | None,
    text: str,
    markup: InlineKeyboardMarkup,
    *,
    parse_mode: str | Default = _DEFAULT_PARSE_MODE,
) -> Message:
    protected = await protect_confirmation(state, markup)
    prompt = await message.answer(text, reply_markup=protected, parse_mode=parse_mode)
    if state is not None:
        await bind_confirmation_message(state, prompt.message_id)
    return prompt


async def edit_confirmation(
    message: Message,
    state: FSMContext | None,
    text: str,
    markup: InlineKeyboardMarkup,
    *,
    parse_mode: str | Default = _DEFAULT_PARSE_MODE,
) -> Message:
    protected = await protect_confirmation(
        state, markup, message_id=message.message_id if state is not None else None
    )
    try:
        await message.edit_text(text, reply_markup=protected, parse_mode=parse_mode)
    except TelegramBadRequest:
        return await answer_confirmation(message, state, text, markup, parse_mode=parse_mode)
    return message


class ConfirmationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)
        callback = event.data or ""
        state = data.get("state")
        state = state if isinstance(state, FSMContext) else None
        draft = (await state.get_data()).get(_DRAFT) if state is not None else None
        if callback.startswith(_PREFIX):
            if state is not None and draft and event.message:
                action = draft["actions"].get(callback.removeprefix(_PREFIX))
                if action and event.message.message_id == draft["message_id"]:
                    # The dispatcher isolates updates for this FSM key. Consume before dispatch.
                    await state.update_data(**{_DRAFT: None})
                    return await handler(event.model_copy(update={"data": action}), data)
        elif not _requires_confirmation(callback):
            if (
                state is not None
                and draft
                and not (
                    callback.startswith(_DRAFT_CONTROLS)
                    and event.message
                    and event.message.message_id != draft["message_id"]
                )
            ):
                await state.update_data(**{_DRAFT: None})
            return await handler(event, data)

        i18n = data["i18n_instance"]
        lang = data.get("current_language", data["settings"].DEFAULT_LANGUAGE)
        await safe_answer_callback(
            event, i18n.gettext(lang, "telegram_confirmation_expired"), show_alert=True
        )
        return None
