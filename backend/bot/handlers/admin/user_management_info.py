import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hcode
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.states.admin_states import AdminStates
from bot.utils.callback_answer import (
    callback_message,
)
from config.settings import Settings
from db.dal import message_log_dal, user_dal
from db.models import User

from .user_management_cards import (
    _send_with_profile_link_fallback,
    format_user_card,
    get_user_card_keyboard,
)
from .user_management_common import (
    _admin_user_button_label,
    _admin_user_reference_label,
    _resolve_bot_username,
    router,
)


async def handle_view_user_logs(
    callback: types.CallbackQuery,
    user: User,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Show recent user logs"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    try:
        # Get recent logs for user
        logs = await message_log_dal.get_user_message_logs(
            session, user.user_id, limit=10, offset=0
        )

        if not logs:
            await callback.answer(_("admin_user_no_logs"), show_alert=True)
            return

        logs_text_parts = [f"{_('admin_user_recent_actions_title', user_id=user.user_id)}\n"]

        for log in logs:
            timestamp = log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else "N/A"
            event_type = log.event_type or "N/A"
            content_preview = (log.content or "")[:50] + (
                "..." if len(log.content or "") > 50 else ""
            )

            logs_text_parts.append(
                f"🕐 {hcode(timestamp)} - {hcode(event_type)}\n   {content_preview}"
            )

        logs_text = "\n\n".join(logs_text_parts)

        # Create inline keyboard for full logs
        builder = InlineKeyboardBuilder()
        builder.button(
            text=_(key="admin_user_view_all_logs_button"),
            callback_data=f"admin_logs:view_user:{user.user_id}:0",
        )
        builder.button(
            text=_(key="admin_user_back_to_card_button"),
            callback_data=f"user_action:refresh:{user.user_id}",
        )
        builder.adjust(1)

        try:
            await callback_message(callback).edit_text(
                logs_text, reply_markup=builder.as_markup(), parse_mode="HTML"
            )
        except Exception:
            await callback_message(callback).answer(
                logs_text, reply_markup=builder.as_markup(), parse_mode="HTML"
            )

        await callback.answer()

    except Exception as e:
        logging.error(f"Error viewing logs for user {user.user_id}: {e}")
        await callback.answer(_("admin_user_logs_error"), show_alert=True)


async def handle_view_user_invitees(
    callback: types.CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n_instance: JsonI18n,
    lang: str,
    *,
    page: int = 0,
) -> None:
    """Show users invited by the selected account."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    page_size = 10
    safe_page = max(0, int(page or 0))

    try:
        total = await user_dal.count_users_referred_by(session, user.user_id)
        total_pages = max(1, (total + page_size - 1) // page_size)
        if safe_page >= total_pages:
            safe_page = total_pages - 1
        invitees = await user_dal.get_users_referred_by(
            session,
            user.user_id,
            limit=page_size,
            offset=safe_page * page_size,
        )

        header = _(
            "admin_user_invitees_message_title",
            user=hcode(_admin_user_reference_label(user)),
            total=total,
            current=safe_page + 1,
            total_pages=total_pages,
        )
        if total <= 0:
            invitees_text = f"{header}\n\n{_('admin_user_invitees_empty')}"
        else:
            lines = []
            for index, invitee in enumerate(invitees, start=safe_page * page_size + 1):
                registered = (
                    invitee.registration_date.strftime("%Y-%m-%d")
                    if invitee.registration_date
                    else ""
                )
                suffix = (
                    _("admin_user_invitee_registered_suffix", date=registered) if registered else ""
                )
                lines.append(
                    _(
                        "admin_user_invitee_item",
                        index=index,
                        user=hcode(_admin_user_reference_label(invitee)),
                        suffix=suffix,
                    )
                )
            invitees_text = "\n".join([header, "", *lines])

        builder = InlineKeyboardBuilder()
        for invitee in invitees:
            builder.row(
                types.InlineKeyboardButton(
                    text=_admin_user_button_label(invitee),
                    callback_data=f"user_action:refresh:{invitee.user_id}",
                )
            )

        pagination_buttons = []
        if safe_page > 0:
            pagination_buttons.append(
                types.InlineKeyboardButton(
                    text=_("prev_page_button"),
                    callback_data=f"user_action:invitees:{user.user_id}:{safe_page - 1}",
                )
            )
        if safe_page < total_pages - 1:
            pagination_buttons.append(
                types.InlineKeyboardButton(
                    text=_("next_page_button"),
                    callback_data=f"user_action:invitees:{user.user_id}:{safe_page + 1}",
                )
            )
        if pagination_buttons:
            builder.row(*pagination_buttons)
        builder.row(
            types.InlineKeyboardButton(
                text=_("admin_user_back_to_card_button"),
                callback_data=f"user_action:refresh:{user.user_id}",
            )
        )
        builder.row(
            types.InlineKeyboardButton(
                text=_("back_to_admin_panel_button"), callback_data="admin_action:main"
            )
        )

        try:
            await callback_message(callback).edit_text(
                invitees_text, reply_markup=builder.as_markup(), parse_mode="HTML"
            )
        except Exception:
            await callback_message(callback).answer(
                invitees_text, reply_markup=builder.as_markup(), parse_mode="HTML"
            )

        await callback.answer()
    except Exception as exc:
        logging.error(
            "Error viewing invitees for user %s: %s",
            user.user_id,
            exc,
            exc_info=True,
        )
        await callback.answer(_("admin_user_invitees_error"), show_alert=True)


async def handle_refresh_user_card(
    callback: types.CallbackQuery,
    user: User,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
    lang: str,
) -> None:
    """Refresh user card with latest information"""
    try:
        # Reload user from database
        fresh_user = await user_dal.get_user_by_id(session, user.user_id)
        if not fresh_user:
            await callback.answer("User not found", show_alert=True)
            return

        referral_service = ReferralService(
            settings, subscription_service, callback_message(callback).bot, i18n_instance
        )
        bot_username = await _resolve_bot_username(callback_message(callback).bot)
        user_card_text = await format_user_card(
            fresh_user,
            session,
            subscription_service,
            i18n_instance,
            lang,
            referral_service,
            settings=settings,
            bot_username=bot_username,
        )
        keyboard = get_user_card_keyboard(
            fresh_user.user_id, i18n_instance, lang, fresh_user.referred_by_id
        )
        markup = keyboard.as_markup()

        try:
            await _send_with_profile_link_fallback(
                callback_message(callback).edit_text,
                text=user_card_text,
                markup=markup,
                user_id=fresh_user.user_id,
                parse_mode="HTML",
            )
        except Exception:
            await _send_with_profile_link_fallback(
                callback_message(callback).answer,
                text=user_card_text,
                markup=markup,
                user_id=fresh_user.user_id,
                parse_mode="HTML",
            )

        await callback.answer()

    except Exception as e:
        logging.error(f"Error refreshing user card for {user.user_id}: {e}")
        await callback.answer("Error refreshing user card", show_alert=True)


# Destructive deletion flow
async def handle_delete_user_prompt(
    callback: types.CallbackQuery,
    state: FSMContext,
    user: User,
    settings: Settings,
    i18n_instance: JsonI18n,
    lang: str,
    session: AsyncSession,
) -> None:
    """Trigger confirmation workflow for destructive deletion."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    admin = callback.from_user
    admin_id = admin.id if admin else None
    if not admin_id or admin_id not in settings.ADMIN_IDS:
        logging.warning(f"Unauthorized delete attempt by user {admin_id} targeting {user.user_id}.")
        await callback.answer(
            _(
                "admin_user_delete_not_allowed",
            ),
            show_alert=True,
        )
        return

    await state.update_data(
        target_user_id=user.user_id,
        delete_initiator_id=admin_id,
    )
    await state.set_state(AdminStates.waiting_for_user_delete_confirmation)

    prompt_text = _(
        "admin_user_delete_confirmation_prompt",
        user_id=hcode(str(user.user_id)),
    )

    try:
        await callback_message(callback).answer(prompt_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Failed to send delete confirmation prompt for user {user.user_id}: {e}")
        await callback_message(callback).reply(prompt_text, parse_mode="HTML")

    await callback.answer()


async def _log_admin_user_deletion(
    session: AsyncSession,
    admin_id: int,
    admin_user: Optional[types.User],
    target_user_id: int,
) -> None:
    """Store audit log for successful deletion."""
    try:
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": admin_id,
                "telegram_username": admin_user.username if admin_user else None,
                "telegram_first_name": admin_user.first_name if admin_user else None,
                "event_type": "admin:user_deleted",
                "content": f"Admin {admin_id} deleted user {target_user_id}",
                "raw_update_preview": None,
                "is_admin_event": True,
                "target_user_id": target_user_id,
                "timestamp": datetime.now(timezone.utc),
            },
        )
    except Exception as e:
        logging.error(
            f"Failed to log deletion audit for admin {admin_id} -> user {target_user_id}: {e}",
            exc_info=True,
        )


# Message handlers for state-based inputs


@router.message(AdminStates.waiting_for_user_delete_confirmation, F.text)
async def process_delete_user_confirmation_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    panel_service: PanelApiService,
    session: AsyncSession,
) -> None:
    """Confirm and execute destructive user deletion."""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        await message.reply("Language service error.")
        await state.clear()
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    admin = message.from_user
    admin_id = admin.id if admin else None
    if not admin_id or admin_id not in settings.ADMIN_IDS:
        logging.warning(f"Unauthorized delete confirmation attempt by user {admin_id}.")
        await message.answer(
            _(
                "admin_user_delete_not_allowed",
            )
        )
        await state.clear()
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        await message.answer(
            _(
                "admin_user_delete_state_missing",
            )
        )
        await state.clear()
        return

    confirmation_input = (message.text or "").strip() if message.text else ""
    if confirmation_input.lower() in {"/cancel", "cancel", "отмена"}:
        await message.answer(
            _(
                "admin_user_delete_cancelled",
            )
        )
        await state.clear()
        return

    if confirmation_input != str(target_user_id):
        await message.answer(
            _(
                "admin_user_delete_mismatch",
            )
        )
        await state.clear()
        return

    user_model = await user_dal.get_user_by_id(session, target_user_id)
    if not user_model:
        await message.answer(
            _(
                "admin_user_delete_already_removed",
            )
        )
        await state.clear()
        return

    try:
        panel_user_uuids = await user_dal.get_panel_user_uuids_for_user(
            session,
            target_user_id,
            user=user_model,
        )
        for panel_uuid in panel_user_uuids:
            panel_deleted = await panel_service.delete_user_from_panel(panel_uuid)
            if not panel_deleted:
                await message.answer(
                    _(
                        "admin_user_delete_panel_error",
                    )
                )
                await session.rollback()
                await state.clear()
                return

        deleted = await user_dal.delete_user_and_relations(session, target_user_id)
        if not deleted:
            await message.answer(
                _(
                    "admin_user_delete_already_removed",
                )
            )
            await state.clear()
            return

        await _log_admin_user_deletion(session, admin_id, admin, target_user_id)
        await session.commit()

        await message.answer(
            _(
                "admin_user_delete_success",
                user_id=hcode(str(target_user_id)),
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"Error deleting user {target_user_id}: {e}", exc_info=True)
        await session.rollback()
        await message.answer(
            _(
                "admin_user_delete_error",
            )
        )
    finally:
        await state.clear()
