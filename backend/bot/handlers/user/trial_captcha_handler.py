"""Telegram rendering for the same challenge/proof used by Mini App."""

import base64
from contextlib import suppress

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards_context import (
    BOT_MENU_CONTEXT,
    callback_suffix_for_context,
    telegram_bot_menu_enabled_for_user,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.telegram_account import require_telegram_account_id
from bot.services.trial_captcha import (
    TrialCaptchaError,
    captcha_verified,
    create_trial_challenge,
    verify_trial_challenge,
)
from config.settings import Settings

from .start_menus import send_bot_interface_menu, send_main_menu

router = Router(name="trial_captcha")


class TrialCaptchaState(StatesGroup):
    answer = State()


async def ensure_bot_trial_captcha(
    callback: types.CallbackQuery,
    settings: Settings,
    user_id: int,
    i18n: JsonI18n,
    language: str,
    state: FSMContext | None,
    *,
    context: str | None = None,
) -> bool:
    try:
        if await captcha_verified(settings, user_id):
            return True
        if state is None or not isinstance(callback.message, types.Message):
            raise TrialCaptchaError("trial_captcha_unavailable", 503)
        challenge = await create_trial_challenge(settings, user_id)
        await state.set_state(TrialCaptchaState.answer)
        await state.update_data(
            trial_challenge_id=challenge.challenge_id, trial_user_id=user_id, trial_context=context
        )
        await callback.message.answer_photo(
            types.BufferedInputFile(
                base64.b64decode(challenge.image.split(",", 1)[1]), "captcha.png"
            ),
            caption=i18n.gettext(language, "trial_captcha_bot_prompt"),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=i18n.gettext(language, "trial_captcha_bot_cancel"),
                            callback_data=f"trial_captcha:cancel:{challenge.challenge_id}",
                        ),
                    ]
                ]
            ),
        )
        await callback.answer()
    except TrialCaptchaError as exc:
        await callback.answer(i18n.gettext(language, exc.code), show_alert=True)
    return False


@router.callback_query(F.data.startswith("trial_captcha:cancel:"))
async def cancel_trial_captcha(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    i18n_data: dict,
) -> None:
    data = await state.get_data()
    active = await state.get_state() == TrialCaptchaState.answer.state and (
        callback.data or ""
    ).rsplit(":", 1)[-1] == data.get("trial_challenge_id")
    if active:
        await state.clear()
    if isinstance(callback.message, types.Message):
        with suppress(TelegramBadRequest):
            await callback.message.delete()
    await callback.answer()
    if active:
        show_menu = (
            send_bot_interface_menu
            if data.get("trial_context") == BOT_MENU_CONTEXT
            and telegram_bot_menu_enabled_for_user(settings)
            else send_main_menu
        )
        await show_menu(callback, settings, i18n_data, subscription_service, session)


@router.message(TrialCaptchaState.answer, F.text, ~F.text.startswith("/"))
async def answer_trial_captcha(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    session: AsyncSession,
    i18n_data: dict,
) -> None:
    if message.from_user is None:
        return
    i18n: JsonI18n = i18n_data["i18n_instance"]
    language = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    data = await state.get_data()
    user_id = await require_telegram_account_id(session, message.from_user.id)
    await state.clear()
    try:
        if user_id != data.get("trial_user_id"):
            raise TrialCaptchaError("trial_captcha_expired")
        await verify_trial_challenge(
            settings, user_id, str(data.get("trial_challenge_id", "")), message.text or ""
        )
        key = "trial_captcha_bot_success"
    except TrialCaptchaError as exc:
        key = exc.code
    suffix = callback_suffix_for_context(data.get("trial_context"))
    await message.answer(
        i18n.gettext(language, key),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=i18n.gettext(language, "trial_captcha_bot_continue"),
                        callback_data=f"main_action:request_trial{suffix}",
                    ),
                ]
            ]
        ),
    )
