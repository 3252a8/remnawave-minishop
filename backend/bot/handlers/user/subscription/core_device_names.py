"""Bot flow for naming HWID devices; the Web App offers the same action."""

import contextlib
import html
import logging
import time
from collections.abc import Callable
from typing import Any

from aiogram import Bot, F, types
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.device_names import DEVICE_NAME_MAX_LENGTH, normalize_device_name
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.telegram_account import require_telegram_account_id
from bot.states.user_states import UserDeviceRenameStates
from bot.utils.callback_answer import callback_data, callback_message, message_from_user
from config.settings import Settings
from db.dal import device_name_dal

from .core_common import _hwid_callback_token, router
from .core_status import _devices_list_from_panel_response, my_devices_command_handler

logger = logging.getLogger(__name__)

RENAME_LIST_CALLBACK = "rename_device:list"
RENAME_CANCEL_CALLBACK = "rename_device:cancel"
RENAME_PICK_PREFIX = "rename_device:pick:"
RENAME_RESET_PREFIX = "rename_device:reset:"
# An abandoned prompt stops claiming the user's messages after this long.
RENAME_PROMPT_TTL_SECONDS = 15 * 60
_BUTTON_LABEL_MAX_LENGTH = 40

GetText = Callable[..., str]
OwnedDevice = tuple[int, int, dict[str, Any]]


def _get_text(i18n_data: dict, settings: Settings) -> GetText:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    return lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key


def _default_device_name(device: dict[str, Any], get_text: GetText) -> str:
    return str(
        device.get("deviceModel")
        or device.get("platform")
        or get_text("device_notification_unknown_device")
    )


async def _load_devices(
    session: AsyncSession,
    telegram_user_id: int,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
) -> tuple[int, list[dict[str, Any]]] | None:
    account_user_id = await require_telegram_account_id(session, telegram_user_id)
    active = await subscription_service.get_active_subscription_details(session, account_user_id)
    if not active or not active.get("user_id"):
        return None
    devices = await panel_service.get_user_devices(active.get("user_id"))
    if devices is None:
        return None
    return account_user_id, _devices_list_from_panel_response(devices)


async def _find_owned_device(
    session: AsyncSession,
    telegram_user_id: int,
    token: str,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
) -> OwnedDevice | None:
    loaded = await _load_devices(session, telegram_user_id, subscription_service, panel_service)
    if loaded is None:
        return None
    account_user_id, devices = loaded
    for index, device in enumerate(devices, start=1):
        hwid = str(device.get("hwid") or "").strip()
        if hwid and _hwid_callback_token(hwid) == token:
            return account_user_id, index, device
    return None


async def _show(callback: types.CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback_message(callback).edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await callback_message(callback).answer(text, reply_markup=markup, parse_mode="HTML")


async def _alert(callback: types.CallbackQuery, text: str) -> None:
    with contextlib.suppress(Exception):
        await callback.answer(text, show_alert=True)


@router.callback_query(F.data == RENAME_LIST_CALLBACK)
async def rename_device_list_callback(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
) -> None:
    get_text = _get_text(i18n_data, settings)
    if not settings.MY_DEVICES_SECTION_ENABLED:
        await _alert(callback, get_text("my_devices_feature_disabled"))
        return
    loaded = await _load_devices(
        session, callback.from_user.id, subscription_service, panel_service
    )
    if loaded is None:
        await _alert(callback, get_text("subscription_not_active"))
        return
    account_user_id, devices = loaded
    names = await device_name_dal.get_device_names(session, account_user_id)

    rows: list[list[InlineKeyboardButton]] = []
    for index, device in enumerate(devices, start=1):
        hwid = str(device.get("hwid") or "").strip()
        if not hwid:
            continue
        token = _hwid_callback_token(hwid)
        label = names.get(token) or _default_device_name(device, get_text)
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text(
                        "rename_device_pick_button",
                        index=index,
                        name=label[:_BUTTON_LABEL_MAX_LENGTH],
                    ),
                    callback_data=f"{RENAME_PICK_PREFIX}{token}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_text("back_to_main_menu_button"), callback_data="main_action:my_devices"
            )
        ]
    )
    with contextlib.suppress(Exception):
        await callback.answer()
    await _show(
        callback, get_text("rename_device_pick_prompt"), InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data.startswith(RENAME_PICK_PREFIX))
async def rename_device_pick_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
) -> None:
    get_text = _get_text(i18n_data, settings)
    if not settings.MY_DEVICES_SECTION_ENABLED:
        await _alert(callback, get_text("my_devices_feature_disabled"))
        return
    token = callback_data(callback).removeprefix(RENAME_PICK_PREFIX)
    owned = await _find_owned_device(
        session, callback.from_user.id, token, subscription_service, panel_service
    )
    if owned is None:
        await _alert(callback, get_text("error_try_again"))
        return
    account_user_id, _index, device = owned
    current_name = (await device_name_dal.get_device_names(session, account_user_id)).get(token)

    await state.set_state(UserDeviceRenameStates.waiting_for_name)
    await state.update_data(device_rename_token=token, device_rename_requested_at=time.time())

    rows: list[list[InlineKeyboardButton]] = []
    if current_name:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text("rename_device_reset_button"),
                    callback_data=f"{RENAME_RESET_PREFIX}{token}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=get_text("cancel_button"), callback_data=RENAME_CANCEL_CALLBACK)]
    )
    with contextlib.suppress(Exception):
        await callback.answer()
    await _show(
        callback,
        get_text(
            "rename_device_prompt",
            device=html.escape(current_name or _default_device_name(device, get_text)),
            max=DEVICE_NAME_MAX_LENGTH,
        ),
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith(RENAME_RESET_PREFIX))
async def rename_device_reset_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
) -> None:
    get_text = _get_text(i18n_data, settings)
    await state.clear()
    token = callback_data(callback).removeprefix(RENAME_RESET_PREFIX)
    owned = await _find_owned_device(
        session, callback.from_user.id, token, subscription_service, panel_service
    )
    if owned is None:
        await _alert(callback, get_text("error_try_again"))
        return
    await device_name_dal.set_device_name(session, owned[0], token, "")
    await session.commit()
    with contextlib.suppress(Exception):
        await callback.answer(get_text("rename_device_reset_done"))
    await my_devices_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.callback_query(F.data == RENAME_CANCEL_CALLBACK)
async def rename_device_cancel_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
) -> None:
    await state.clear()
    await my_devices_command_handler(
        callback, i18n_data, settings, panel_service, subscription_service, session, bot
    )


@router.message(UserDeviceRenameStates.waiting_for_name, F.text, ~F.text.startswith("/"))
async def rename_device_name_message(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
) -> None:
    data = await state.get_data()
    token = str(data.get("device_rename_token") or "")
    requested_at = float(data.get("device_rename_requested_at") or 0)
    if not token or time.time() - requested_at > RENAME_PROMPT_TTL_SECONDS:
        # A forgotten prompt must not swallow an unrelated message.
        await state.clear()
        raise SkipHandler()

    get_text = _get_text(i18n_data, settings)
    name = normalize_device_name(message.text)
    if not name or len(name) > DEVICE_NAME_MAX_LENGTH:
        await message.answer(get_text("rename_device_invalid", max=DEVICE_NAME_MAX_LENGTH))
        return

    await state.clear()
    owned = await _find_owned_device(
        session, message_from_user(message).id, token, subscription_service, panel_service
    )
    if owned is None:
        await message.answer(get_text("error_try_again"))
        return
    await device_name_dal.set_device_name(session, owned[0], token, name)
    await session.commit()
    await message.answer(get_text("rename_device_saved", name=html.escape(name)), parse_mode="HTML")
    await my_devices_command_handler(
        message, i18n_data, settings, panel_service, subscription_service, session, bot
    )
