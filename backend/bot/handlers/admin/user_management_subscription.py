import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.states.admin_states import AdminStates
from bot.utils.callback_answer import (
    callback_message,
)
from config.settings import Settings
from db.dal import message_log_dal, subscription_dal, user_dal
from db.models import User

from .user_management_common import (
    _admin_tariff_label,
    _enabled_admin_period_tariffs,
    _resolve_admin_period_tariff_key,
)
from .user_management_info import handle_refresh_user_card


async def handle_traffic_grant_menu(
    callback: types.CallbackQuery,
    user: User,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Show traffic-grant menu (regular vs premium)."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    text = "\n".join(
        [
            f"<b>{_('admin_traffic_grant_title')}</b>",
            "",
            _("admin_traffic_grant_hint"),
        ]
    )
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_("admin_traffic_grant_btn_regular"),
        callback_data=f"user_action:traffic_grant_regular:{user.user_id}",
    )
    builder.button(
        text=_("admin_traffic_grant_btn_premium"),
        callback_data=f"user_action:traffic_grant_premium:{user.user_id}",
    )
    builder.button(
        text=_("admin_user_back_to_card_button"),
        callback_data=f"user_action:refresh:{user.user_id}",
    )
    builder.adjust(1, 1, 1)

    try:
        await callback_message(callback).edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    except Exception:
        await callback_message(callback).answer(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    await callback.answer()


async def handle_traffic_grant_prompt(
    callback: types.CallbackQuery,
    state: FSMContext,
    user: User,
    kind: str,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Ask the admin for the amount of GB to grant (regular or premium)."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    kind_normalized = "premium" if kind == "premium" else "regular"
    await state.update_data(target_user_id=user.user_id, traffic_grant_kind=kind_normalized)
    await state.set_state(AdminStates.waiting_for_traffic_grant_gb)
    prompt_key = (
        "admin_traffic_grant_prompt_premium"
        if kind_normalized == "premium"
        else "admin_traffic_grant_prompt_regular"
    )
    prompt = _(prompt_key, user_id=user.user_id)
    try:
        await callback_message(callback).edit_text(prompt)
    except Exception:
        await callback_message(callback).answer(prompt)
    await callback.answer()


# `process_traffic_grant_gb_handler` is declared near the other FSM-bound
# handlers at the bottom of the module, so the router decorator can attach to
# the same `router` instance the premium override flow uses.


async def handle_reset_trial(
    callback: types.CallbackQuery,
    user: User,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Reset user's trial eligibility"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    try:
        await user_dal.mark_trial_eligibility_reset(session, user.user_id)
        await session.commit()

        await callback.answer(_("admin_user_trial_reset_success"), show_alert=True)

        # Refresh user card
        await handle_refresh_user_card(
            callback, user, subscription_service, session, settings, i18n_instance, lang
        )

    except Exception as e:
        logging.error(f"Error resetting trial for user {user.user_id}: {e}")
        await session.rollback()
        await callback.answer(_("admin_user_trial_reset_error"), show_alert=True)


async def handle_add_subscription_prompt(
    callback: types.CallbackQuery,
    state: FSMContext,
    user: User,
    settings: Settings,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Prompt admin to choose tariff when required, then enter subscription days."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    tariff_key, tariff_error = _resolve_admin_period_tariff_key(settings)
    if tariff_error == "admin_user_tariff_required":
        period_tariffs = _enabled_admin_period_tariffs(settings)
        builder = InlineKeyboardBuilder()
        for tariff in period_tariffs:
            builder.button(
                text=_admin_tariff_label(tariff, lang),
                callback_data=f"user_action:add_subscription_tariff:{user.user_id}:{tariff.key}",
            )
        builder.button(
            text=_("admin_user_back_to_card_button"),
            callback_data=f"user_action:refresh:{user.user_id}",
        )
        builder.adjust(1)
        prompt_text = _("admin_user_add_subscription_tariff_prompt", user_id=user.user_id)
        try:
            await callback_message(callback).edit_text(
                prompt_text, reply_markup=builder.as_markup()
            )
        except Exception:
            await callback_message(callback).answer(prompt_text, reply_markup=builder.as_markup())
        await callback.answer()
        return
    if tariff_error:
        await callback.answer(_(tariff_error), show_alert=True)
        return

    await handle_add_subscription_days_prompt(
        callback,
        state,
        user,
        settings,
        i18n_instance,
        lang,
        tariff_key=tariff_key,
    )


async def handle_add_subscription_days_prompt(
    callback: types.CallbackQuery,
    state: FSMContext,
    user: User,
    settings: Settings,
    i18n_instance: JsonI18n,
    lang: str,
    *,
    tariff_key: Optional[str],
) -> None:
    """Prompt admin to enter subscription days to add after tariff resolution."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    tariff_key, tariff_error = _resolve_admin_period_tariff_key(settings, tariff_key)
    if tariff_error:
        await callback.answer(_(tariff_error), show_alert=True)
        return

    await state.update_data(target_user_id=user.user_id)
    await state.update_data(subscription_tariff_key=tariff_key)
    await state.set_state(AdminStates.waiting_for_subscription_days_to_add)

    prompt_key = (
        "admin_user_add_subscription_prompt_with_tariff"
        if tariff_key
        else "admin_user_add_subscription_prompt"
    )
    prompt_text = _(
        prompt_key,
        user_id=user.user_id,
        tariff=tariff_key or "",
    )

    try:
        await callback_message(callback).edit_text(prompt_text)
    except Exception:
        await callback_message(callback).answer(prompt_text)

    await callback.answer()


async def handle_change_tariff_menu(
    callback: types.CallbackQuery,
    user: User,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Show period tariff choices for an active subscription."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    active_sub = await subscription_dal.get_active_subscription_by_user_id(session, user.user_id)
    if not active_sub:
        await callback.answer(_("admin_user_tariff_no_subscription"), show_alert=True)
        return

    period_tariffs = _enabled_admin_period_tariffs(settings)
    if not period_tariffs:
        await callback.answer(_("admin_user_tariff_no_period_tariffs"), show_alert=True)
        return

    current_key = str(getattr(active_sub, "tariff_key", "") or "")
    builder = InlineKeyboardBuilder()
    for tariff in period_tariffs:
        marker = "✓ " if str(tariff.key) == current_key else ""
        builder.button(
            text=f"{marker}{_admin_tariff_label(tariff, lang)}",
            callback_data=f"user_action:set_tariff:{user.user_id}:{tariff.key}",
        )
    builder.button(
        text=_("admin_user_back_to_card_button"),
        callback_data=f"user_action:refresh:{user.user_id}",
    )
    builder.adjust(1)
    text = "\n".join(
        [
            f"<b>{_('admin_user_tariff_change_title')}</b>",
            "",
            _("admin_user_tariff_change_hint"),
            _("admin_user_tariff_current", tariff=current_key or _("admin_user_tariff_none")),
        ]
    )
    try:
        await callback_message(callback).edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    except Exception:
        await callback_message(callback).answer(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    await callback.answer()


async def handle_change_tariff_apply(
    callback: types.CallbackQuery,
    user: User,
    settings: Settings,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    i18n_instance: JsonI18n,
    lang: str,
    *,
    tariff_key: str,
) -> None:
    """Apply an admin-selected tariff to the current active subscription."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    resolved_tariff_key, tariff_error = _resolve_admin_period_tariff_key(settings, tariff_key)
    if tariff_error or not resolved_tariff_key:
        await callback.answer(_(tariff_error or "admin_user_tariff_required"), show_alert=True)
        return

    active_sub = await subscription_dal.get_active_subscription_by_user_id(session, user.user_id)
    if not active_sub:
        await callback.answer(_("admin_user_tariff_no_subscription"), show_alert=True)
        return

    try:
        result = await subscription_service.switch_tariff_without_payment(
            session,
            user.user_id,
            resolved_tariff_key,
            "admin_assign",
        )
        if not result:
            await session.rollback()
            await callback.answer(_("admin_user_tariff_change_error"), show_alert=True)
            return
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": callback.from_user.id if callback.from_user else user.user_id,
                "event_type": "admin:change_tariff",
                "content": f"tariff={resolved_tariff_key}",
                "is_admin_event": True,
                "target_user_id": user.user_id,
                "timestamp": datetime.now(timezone.utc),
            },
        )
        await session.commit()
        await callback.answer(
            _("admin_user_tariff_change_success", tariff=resolved_tariff_key),
            show_alert=False,
        )
        await handle_refresh_user_card(
            callback,
            user,
            subscription_service,
            session,
            settings,
            i18n_instance,
            lang,
        )
    except Exception as exc:
        logging.error(
            "Error changing tariff for user %s to %s: %s",
            user.user_id,
            resolved_tariff_key,
            exc,
            exc_info=True,
        )
        await session.rollback()
        await callback.answer(_("admin_user_tariff_change_error"), show_alert=True)


async def handle_toggle_ban(
    callback: types.CallbackQuery,
    user: User,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Toggle user ban status"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    try:
        new_ban_status = not user.is_banned

        # Update in database
        await user_dal.update_user(session, user.user_id, {"is_banned": new_ban_status})

        # Update on panel if user has panel UUID
        if user.panel_user_uuid:
            await panel_service.update_user_status_on_panel(
                user.panel_user_uuid, not new_ban_status
            )

        await session.commit()

        status_text = (
            _("admin_user_ban_action_banned")
            if new_ban_status
            else _("admin_user_ban_action_unbanned")
        )
        await callback.answer(
            _("admin_user_ban_toggle_success", status=status_text), show_alert=True
        )

        # Refresh user card with updated ban status
        user.is_banned = new_ban_status  # Update local object
        await handle_refresh_user_card(
            callback, user, subscription_service, session, settings, i18n_instance, lang
        )

    except Exception as e:
        logging.error(f"Error toggling ban for user {user.user_id}: {e}")
        await session.rollback()
        await callback.answer(_("admin_user_ban_toggle_error"), show_alert=True)


async def handle_send_message_prompt(
    callback: types.CallbackQuery, state: FSMContext, user: User, i18n_instance: JsonI18n, lang: str
) -> None:
    """Prompt admin to enter message to send to user"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    await state.update_data(target_user_id=user.user_id)
    await state.set_state(AdminStates.waiting_for_direct_message_to_user)

    prompt_text = _("admin_user_send_message_prompt", user_id=user.user_id)

    try:
        await callback_message(callback).edit_text(prompt_text)
    except Exception:
        await callback_message(callback).answer(prompt_text)

    await callback.answer()
