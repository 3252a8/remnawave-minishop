import logging
from typing import Optional

from aiogram import Bot, F, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_autorenew_confirm_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.payment_providers import provider_supports_recurring
from bot.payment_providers.shared import service_supports_recurring
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import (
    callback_data,
    callback_message,
    message_from_user,
)
from config.settings import Settings
from db.dal import subscription_dal, user_billing_dal
from db.models import Subscription

from .core_common import (
    _hwid_callback_token,
    _recurring_service_for_subscription,
    router,
)
from .core_status import (
    _devices_list_from_panel_response,
    my_devices_command_handler,
    my_subscription_command_handler,
)


@router.callback_query(F.data.startswith("disconnect_device:"))
async def disconnect_device_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not settings.MY_DEVICES_SECTION_ENABLED:
        try:
            await callback.answer(get_text("my_devices_feature_disabled"), show_alert=True)
        except Exception:
            pass
        return

    try:
        _, hwid_token = callback_data(callback).split(":", 1)
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    active = await subscription_service.get_active_subscription_details(
        session, callback.from_user.id
    )
    if not active or not active.get("user_id"):
        await callback.answer(get_text("subscription_not_active"), show_alert=True)
        return

    devices = await panel_service.get_user_devices(active.get("user_id"))
    if devices is None:
        await callback.answer(get_text("no_devices_found"), show_alert=True)
        return

    devices_list_raw = _devices_list_from_panel_response(devices)

    hwid = None
    for device in devices_list_raw:
        hwid_candidate = device.get("hwid")
        if hwid_candidate and _hwid_callback_token(hwid_candidate) == hwid_token:
            hwid = hwid_candidate
            break

    if not hwid:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return

    success = await panel_service.disconnect_device(active.get("user_id"), hwid)
    if not success:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    await session.commit()
    try:
        await callback.answer(get_text("device_disconnected"))
    except Exception:
        pass
    await my_devices_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.callback_query(F.data.startswith("toggle_autorenew:"))
async def toggle_autorenew_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    try:
        _, payload = callback_data(callback).split(":", 1)
        sub_id_str, enable_str = payload.split(":")
        sub_id = int(sub_id_str)
        enable = bool(int(enable_str))
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    sub = await session.get(Subscription, sub_id)
    if not sub or sub.user_id != callback.from_user.id:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    provider = str(getattr(sub, "provider", "") or "").strip().lower()
    if not provider_supports_recurring(provider):
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if enable:
        service = _recurring_service_for_subscription(subscription_service, sub)
        if not service_supports_recurring(service):
            await callback.answer(get_text("autorenew_unavailable"), show_alert=True)
            return
        has_saved_card = await user_billing_dal.user_has_saved_payment_method(
            session, callback.from_user.id, provider=provider
        )
        if not has_saved_card:
            try:
                await callback.answer(get_text("autorenew_enable_requires_card"), show_alert=True)
            except Exception:
                pass
            return

    # Show confirmation popup and inline buttons
    confirm_text = (
        get_text("autorenew_confirm_enable") if enable else get_text("autorenew_confirm_disable")
    )
    kb = get_autorenew_confirm_keyboard(enable, sub.subscription_id, current_lang, i18n)
    try:
        await callback_message(callback).edit_text(confirm_text, reply_markup=kb)
    except Exception:
        try:
            await callback_message(callback).answer(confirm_text, reply_markup=kb)
        except Exception:
            pass
    try:
        await callback.answer()
    except Exception:
        pass
    return


@router.callback_query(F.data.startswith("autorenew:confirm:"))
async def confirm_autorenew_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    try:
        _, _, sub_id_str, enable_str = callback_data(callback).split(":", 3)
        sub_id = int(sub_id_str)
        enable = bool(int(enable_str))
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    sub = await session.get(Subscription, sub_id)
    if not sub or sub.user_id != callback.from_user.id:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    provider = str(getattr(sub, "provider", "") or "").strip().lower()
    if not provider_supports_recurring(provider):
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if enable:
        service = _recurring_service_for_subscription(subscription_service, sub)
        if not service_supports_recurring(service):
            await callback.answer(get_text("autorenew_unavailable"), show_alert=True)
            try:
                await my_subscription_command_handler(
                    callback, i18n_data, settings, panel_service, subscription_service, session, bot
                )
            except Exception:
                pass
            return
        has_saved_card = await user_billing_dal.user_has_saved_payment_method(
            session, callback.from_user.id, provider=provider
        )
        if not has_saved_card:
            try:
                await callback.answer(get_text("autorenew_enable_requires_card"), show_alert=True)
            except Exception:
                pass
            try:
                await my_subscription_command_handler(
                    callback, i18n_data, settings, panel_service, subscription_service, session, bot
                )
            except Exception:
                pass
            return

    await subscription_dal.update_subscription(
        session, sub.subscription_id, {"auto_renew_enabled": enable}
    )
    await session.commit()
    try:
        await callback.answer(get_text("subscription_autorenew_updated"))
    except Exception:
        pass
    await my_subscription_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.callback_query(F.data == "autorenew:cancel")
async def autorenew_cancel_from_webhook_button(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    # Disable auto-renew on the active subscription
    from db.dal import subscription_dal

    sub = await subscription_dal.get_active_subscription_by_user_id(session, callback.from_user.id)
    if not sub:
        try:
            await callback.answer(get_text("subscription_not_active"), show_alert=True)
        except Exception:
            pass
        return
    if not provider_supports_recurring(getattr(sub, "provider", None)):
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return
    await subscription_dal.update_subscription(
        session, sub.subscription_id, {"auto_renew_enabled": False}
    )
    await session.commit()
    try:
        await callback.answer(get_text("subscription_autorenew_updated"))
    except Exception:
        pass
    await my_subscription_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.message(Command("connect"))
async def connect_command_handler(
    message: types.Message,
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
) -> None:
    logging.info(f"User {message_from_user(message).id} used /connect command.")
    await my_subscription_command_handler(
        message, i18n_data, settings, panel_service, subscription_service, session, bot
    )
