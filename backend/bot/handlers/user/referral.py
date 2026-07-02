import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.utils.callback_answer import callback_data, callback_message, message_from_user
from config.settings import Settings
from db.dal import user_dal

router = Router(name="user_referral_router")


async def referral_command_handler(
    event: types.Message | types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    referral_service: ReferralService,
    bot: Bot,
    session: AsyncSession,
    back_callback: str = "main_action:back_to_main",
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")

    target_message_obj = event.message if isinstance(event, types.CallbackQuery) else event
    if not target_message_obj:
        logging.error(
            "Target message is None in referral_command_handler (possibly from callback without message)."  # noqa: E501
        )
        if isinstance(event, types.CallbackQuery):
            await event.answer("Error displaying referral info.", show_alert=True)
        return

    if not i18n or not referral_service:
        logging.error("Dependencies (i18n or ReferralService) missing in referral_command_handler")
        await target_message_obj.answer("Service error. Please try again later.")
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
    except Exception as e_bot_info:
        logging.error(f"Failed to get bot info for referral link: {e_bot_info}")
        await target_message_obj.answer(_("error_generating_referral_link"))
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    if not bot_username:
        logging.error("Bot username is None, cannot generate referral link.")
        await target_message_obj.answer(_("error_generating_referral_link"))
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    inviter_user_id = (
        event.from_user.id
        if isinstance(event, types.CallbackQuery)
        else message_from_user(event).id
    )
    referral_link = await referral_service.generate_referral_link(
        session, bot_username, inviter_user_id
    )

    if not referral_link:
        logging.error(
            "Failed to generate referral link for user %s (probably missing DB record).",
            inviter_user_id,
        )
        await target_message_obj.answer(_("error_generating_referral_link"))
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    if settings.traffic_sale_mode:
        bonus_details_str = _("referral_not_available_for_traffic")
    else:
        bonus_details_str = _build_referral_bonus_details_text(settings, _, current_lang)

    referral_stats = await referral_service.get_referral_stats(session, inviter_user_id)

    webapp_referral_link = await _generate_webapp_referral_link(
        session,
        settings,
        inviter_user_id,
    )
    webapp_link_section = (
        _(
            "referral_webapp_link_line",
            webapp_referral_link=webapp_referral_link,
        )
        if webapp_referral_link
        else ""
    )

    text = _(
        "referral_program_info_new",
        referral_link=referral_link,
        webapp_link_section=webapp_link_section,
        bonus_details=bonus_details_str,
        invited_count=referral_stats["invited_count"],
        purchased_count=referral_stats["purchased_count"],
    )

    from bot.keyboards.inline.user_keyboards import get_referral_link_keyboard

    reply_markup_val = get_referral_link_keyboard(
        current_lang,
        i18n,
        back_callback=back_callback,
    )

    if isinstance(event, types.Message):
        await event.answer(text, reply_markup=reply_markup_val, disable_web_page_preview=True)
    elif isinstance(event, types.CallbackQuery) and event.message:
        try:
            await callback_message(event).edit_text(
                text, reply_markup=reply_markup_val, disable_web_page_preview=True
            )
        except Exception as e_edit:
            logging.warning(f"Failed to edit message for referral info: {e_edit}. Sending new one.")
            await callback_message(event).answer(
                text, reply_markup=reply_markup_val, disable_web_page_preview=True
            )
        await event.answer()


@router.callback_query(F.data.startswith("referral_action:"))
async def referral_action_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    referral_service: ReferralService,
    bot: Bot,
    session: AsyncSession,
) -> None:
    action = callback_data(callback).split(":")[1]
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        await callback.answer("Language service error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    if action == "share_message":
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            if not bot_username:
                await callback.answer(_("error_generating_referral_link"), show_alert=True)
                return

            inviter_user_id = callback.from_user.id
            referral_link = await referral_service.generate_referral_link(
                session, bot_username, inviter_user_id
            )

            if not referral_link:
                logging.error(
                    "Failed to generate referral link for user %s via inline button.",
                    inviter_user_id,
                )
                await callback.answer(_("error_generating_referral_link"), show_alert=True)
                return

            webapp_referral_link = await _generate_webapp_referral_link(
                session,
                settings,
                inviter_user_id,
            )
            if webapp_referral_link:
                friend_message = _(
                    "referral_friend_message_with_webapp",
                    referral_link=referral_link,
                    webapp_referral_link=webapp_referral_link,
                )
            else:
                friend_message = _("referral_friend_message", referral_link=referral_link)

            await callback_message(callback).answer(friend_message, disable_web_page_preview=True)

        except Exception as e:
            logging.error(f"Error in referral share message: {e}")
            await callback.answer(_("error_occurred_try_again"), show_alert=True)

    await callback.answer()


Translator = Callable[..., str]


def _period_bonus_text(
    translator: Translator,
    *,
    months: int,
    inviter_days: int | None,
    referee_days: int | None,
) -> str:
    return translator(
        "referral_bonus_per_period",
        months=months,
        inviter_bonus_days=(
            inviter_days if inviter_days is not None else translator("no_bonus_placeholder")
        ),
        referee_bonus_days=(
            referee_days if referee_days is not None else translator("no_bonus_placeholder")
        ),
    )


def _tariff_period_bonus_entries(tariff: Any) -> list[dict[str, int | None]]:
    entries: list[dict[str, int | None]] = []
    for months in sorted(int(month) for month in getattr(tariff, "enabled_periods", [])):
        inviter_days = tariff.referral_inviter_bonus_days(months)
        referee_days = tariff.referral_referee_bonus_days(months)
        if inviter_days is None and referee_days is None:
            continue
        entries.append(
            {
                "months": months,
                "inviter_days": inviter_days,
                "referee_days": referee_days,
            }
        )
    return entries


def _legacy_period_bonus_entries(settings: Settings) -> list[dict[str, int | None]]:
    entries: list[dict[str, int | None]] = []
    for months, _price in sorted(settings.subscription_options.items()):
        inviter_days = settings.referral_bonus_inviter.get(months)
        referee_days = settings.referral_bonus_referee.get(months)
        if inviter_days is None and referee_days is None:
            continue
        entries.append(
            {
                "months": int(months),
                "inviter_days": inviter_days,
                "referee_days": referee_days,
            }
        )
    return entries


def _bonus_days_range(translator: Translator, values: list[int]) -> str:
    return translator(
        "referral_bonus_days_range",
        min_days=min(values),
        max_days=max(values),
    )


def _build_referral_bonus_details_text(
    settings: Settings, translator: Translator, current_lang: str
) -> str:
    tariffs_config = settings.tariffs_config
    if not tariffs_config:
        bonus_info_parts = [
            _period_bonus_text(
                translator,
                months=int(entry["months"] or 0),
                inviter_days=entry["inviter_days"],
                referee_days=entry["referee_days"],
            )
            for entry in _legacy_period_bonus_entries(settings)
        ]
        return (
            "\n".join(bonus_info_parts)
            if bonus_info_parts
            else translator("referral_no_bonuses_configured")
        )

    period_tariffs = [
        tariff for tariff in tariffs_config.enabled_tariffs if tariff.billing_model == "period"
    ]
    if len(period_tariffs) <= 1:
        entries = _tariff_period_bonus_entries(period_tariffs[0]) if period_tariffs else []
        bonus_info_parts = [
            _period_bonus_text(
                translator,
                months=int(entry["months"] or 0),
                inviter_days=entry["inviter_days"],
                referee_days=entry["referee_days"],
            )
            for entry in entries
        ]
        return (
            "\n".join(bonus_info_parts)
            if bonus_info_parts
            else translator("referral_no_bonuses_configured")
        )

    bonus_info_parts = []
    for tariff in period_tariffs:
        entries = _tariff_period_bonus_entries(tariff)
        if not entries:
            continue
        inviter_values = [int(entry["inviter_days"] or 0) for entry in entries]
        referee_values = [int(entry["referee_days"] or 0) for entry in entries]
        bonus_info_parts.append(
            translator(
                "referral_bonus_tariff_range",
                tariff_name=tariff.name(current_lang),
                inviter_bonus_range=_bonus_days_range(translator, inviter_values),
                referee_bonus_range=_bonus_days_range(translator, referee_values),
            )
        )
    return (
        "\n".join(bonus_info_parts)
        if bonus_info_parts
        else translator("referral_no_bonuses_configured")
    )


def _build_webapp_referral_link(base_url: str | None, referral_code: str | None) -> str | None:
    if not base_url or not referral_code:
        return None
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ref"] = f"u{referral_code}"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            urlencode(query),
            parts.fragment,
        )
    )


async def _generate_webapp_referral_link(
    session: AsyncSession,
    settings: Settings,
    inviter_user_id: int,
) -> str | None:
    if not settings.SUBSCRIPTION_MINI_APP_URL:
        return None
    db_user = await user_dal.get_user_by_id(session, inviter_user_id)
    referral_code = await user_dal.ensure_referral_code(session, db_user) if db_user else None
    return _build_webapp_referral_link(
        settings.SUBSCRIPTION_MINI_APP_URL,
        referral_code,
    )


@router.message(Command("referral"))
async def referral_command_message_handler(
    message: types.Message,
    settings: Settings,
    i18n_data: dict,
    referral_service: ReferralService,
    bot: Bot,
    session: AsyncSession,
) -> None:
    await referral_command_handler(message, settings, i18n_data, referral_service, bot, session)
