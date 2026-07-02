import contextlib
import html
import logging
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import (
    get_back_to_main_menu_markup,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import (
    callback_message,
)
from bot.utils.install_links import (
    append_install_share_link_text,
    ensure_user_install_guide_links,
)
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
)
from db.dal import subscription_dal

from .core_common import (
    _auto_renew_control_visible,
    _event_user_id,
    _format_premium_usage_limit,
    _has_multiple_enabled_tariffs,
    _hwid_callback_token,
    _shorten_hwid_for_display,
    router,
)


def _devices_list_from_panel_response(devices: Any) -> list[dict[str, Any]]:
    if isinstance(devices, dict):
        response = devices.get("response")
        if isinstance(response, dict):
            raw_devices = response.get("devices")
        elif isinstance(response, list):
            raw_devices = response
        else:
            raw_devices = devices.get("devices")
            if raw_devices is None:
                raw_devices = devices.get("data")
    else:
        raw_devices = devices

    if not isinstance(raw_devices, list):
        return []
    return [device for device in raw_devices if isinstance(device, dict)]


def _devices_count_from_panel_response(devices: Any) -> int | None:
    if devices is None:
        return None
    if isinstance(devices, dict):
        response = devices.get("response")
        response_dict = response if isinstance(response, dict) else devices
        total_value = response_dict.get("total")
        if isinstance(total_value, int):
            return total_value
        devices_value = response_dict.get("devices")
        if isinstance(devices_value, int):
            return devices_value
        if isinstance(devices_value, list):
            return len(devices_value)
    return len(_devices_list_from_panel_response(devices))


async def my_subscription_command_handler(
    event: types.Message | types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
    back_callback: str = "main_action:back_to_main",
) -> None:
    target = event.message if isinstance(event, types.CallbackQuery) else event
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)

    if not i18n or not target:
        if isinstance(event, types.Message):
            await event.answer(get_text("error_occurred_try_again"))
        return

    if not panel_service or not subscription_service:
        await target.answer(get_text("error_service_unavailable"))
        return

    active = await subscription_service.get_active_subscription_details(
        session, _event_user_id(event)
    )

    if not active:
        text = get_text("subscription_not_active")

        buy_button = InlineKeyboardButton(
            text=get_text("menu_subscribe_inline"), callback_data="main_action:subscribe"
        )
        back_markup = get_back_to_main_menu_markup(
            current_lang,
            i18n,
            callback_data=back_callback,
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[[buy_button], *back_markup.inline_keyboard])

        if isinstance(event, types.CallbackQuery):
            with contextlib.suppress(Exception):
                await event.answer()
            try:
                await callback_message(event).edit_text(text, reply_markup=kb)
            except Exception:
                await callback_message(event).answer(text, reply_markup=kb)
        else:
            await event.answer(text, reply_markup=kb)
        return

    end_date = active.get("end_date")
    days_left = (end_date.date() - datetime.now(UTC).date()).days if end_date else 0
    traffic_mode = bool(settings.traffic_sale_mode)
    config_link_display = active.get("config_link")
    connect_button_url = active.get("connect_button_url")
    config_link_value = config_link_display or get_text("config_link_not_available")

    def _fmt_gb(val: float | None) -> str:
        if val is None:
            return str(get_text("traffic_na"))
        try:
            if isinstance(val, (int, float)):
                val_gb = float(val) / (2**30)
                return f"{val_gb:.2f} GB"
        except Exception:
            pass
        return str(val)

    def _format_traffic_period(strategy: str | None) -> str | None:
        if not strategy:
            return None
        strategy_upper = str(strategy).upper()
        key_map = {
            "MONTH": "traffic_period_month",
            "WEEK": "traffic_period_week",
            "DAY": "traffic_period_day",
            "NO_RESET": "traffic_period_no_reset",
        }
        label_key = key_map.get(strategy_upper)
        return get_text(label_key) if label_key else strategy_upper

    def _format_used_with_period(used_display: str, period_label: str | None) -> str:
        if not period_label:
            return used_display
        return str(
            get_text(
                "traffic_used_with_period", traffic_used=used_display, traffic_period=period_label
            )
        )

    period_label = _format_traffic_period(active.get("traffic_limit_strategy"))
    period_label = period_label or get_text("traffic_period_unknown")

    if traffic_mode:
        limit_display = _fmt_gb(active.get("traffic_limit_bytes"))
        used_display = _format_used_with_period(
            _fmt_gb(active.get("traffic_used_bytes")), period_label
        )
        remaining_display = get_text("traffic_na")
        try:
            limit_val = active.get("traffic_limit_bytes") or 0
            used_val = active.get("traffic_used_bytes") or 0
            remaining_val = max(0, float(limit_val) - float(used_val))
            remaining_display = _fmt_gb(remaining_val)
        except Exception:
            pass
        text = get_text(
            "my_traffic_details",
            status=active.get("status_from_panel", get_text("status_active")).capitalize(),
            end_date=end_date.strftime("%Y-%m-%d") if end_date else get_text("traffic_no_expiry"),
            traffic_limit=limit_display,
            traffic_used=used_display,
            traffic_left=remaining_display,
            traffic_period=period_label,
            config_link=config_link_value,
        )
    else:
        tariff_prefix = ""
        if _has_multiple_enabled_tariffs(settings) and active.get("tariff_name"):
            tariff_prefix = f"🎟 {active.get('tariff_name')}\n"
            if active.get("tariff_description"):
                tariff_prefix += f"{active.get('tariff_description')}\n"
        text = get_text(
            "my_subscription_details",
            end_date=end_date.strftime("%Y-%m-%d") if end_date else "N/A",
            days_left=max(0, days_left),
            status=active.get("status_from_panel", get_text("status_active")).capitalize(),
            config_link=config_link_value,
            traffic_limit=(
                f"{active['traffic_limit_bytes'] / 2**30:.2f} GB"
                if active.get("traffic_limit_bytes")
                else get_text("traffic_unlimited")
            ),
            traffic_used=(
                _format_used_with_period(
                    f"{active['traffic_used_bytes'] / 2**30:.2f} GB"
                    if active.get("traffic_used_bytes") is not None
                    else get_text("traffic_na"),
                    period_label,
                )
            ),
            traffic_period=period_label,
        )
        if tariff_prefix:
            text = tariff_prefix + "\n" + text

    if int(active.get("premium_limit_bytes") or 0) > 0:
        premium_limit = int(active.get("premium_limit_bytes") or 0)
        premium_used = int(active.get("premium_used_bytes") or 0)
        premium_left = max(0, premium_limit - premium_used)
        premium_balance = int(active.get("premium_topup_balance_bytes") or 0)
        premium_status = "ограничен" if active.get("premium_is_limited") else "активен"
        labels = active.get("premium_node_labels") or active.get("premium_squad_labels") or []
        if labels:
            visible = [html.escape(str(label)) for label in labels[:8]]
            label_block = "\n".join(f"• {label}" for label in visible)
            if len(labels) > len(visible):
                label_block += f"\n• ... еще {len(labels) - len(visible)}"
        else:
            label_block = "• premium-серверы тарифа"
        text += (
            "\n\n🚀 <b>Premium-серверы</b>\n"
            f"Статус: <b>{premium_status}</b>\n"
            f"Лимит: <b>{_format_premium_usage_limit(active)}</b>\n"
            f"Осталось: <b>{premium_left / 2**30:.2f} GB</b>\n"
            f"Докупленный остаток: <b>{premium_balance / 2**30:.2f} GB</b>\n"
            "Отдельный лимит действует на:\n"
            f"{label_block}\n\n"
            "Premium-докупка не сгорает: сначала расходуется месячный лимит premium-серверов, затем докупленный premium-трафик."  # noqa: E501
        )

    base_markup = get_back_to_main_menu_markup(
        current_lang,
        i18n,
        callback_data=back_callback,
    )
    kb = base_markup.inline_keyboard
    try:
        local_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, _event_user_id(event)
        )
        install_links = await ensure_user_install_guide_links(
            session,
            settings,
            _event_user_id(event),
            local_subscription=local_sub,
        )
        install_url = install_links.personal_url
        install_share_url = install_links.public_share_url
        if install_share_url:
            try:
                await session.commit()
                text = append_install_share_link_text(text, get_text, install_share_url)
            except Exception:
                await session.rollback()
                logging.exception(
                    "Failed to persist install guide share token for user %s.",
                    _event_user_id(event),
                )
                install_share_url = None

        # Build rows to prepend above the base "back" markup
        prepend_rows = []

        # 1) Connect button: prefer the actual subscription URL; fall back to mini-app
        cfg_link_val = connect_button_url or config_link_display
        if install_url:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("connect_button"),
                        web_app=WebAppInfo(url=install_url),
                    )
                ]
            )
            if install_share_url:
                prepend_rows.append(
                    [
                        InlineKeyboardButton(
                            text=get_text("install_guide_share_button"),
                            url=install_share_url,
                        )
                    ]
                )
        elif cfg_link_val:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("connect_button"),
                        url=cfg_link_val,
                    )
                ]
            )
        elif settings.SUBSCRIPTION_MINI_APP_URL:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("connect_button"),
                        web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
                    )
                ]
            )

        if settings.MY_DEVICES_SECTION_ENABLED:
            max_devices_value = active.get("max_devices")
            max_devices_display = get_text("devices_unlimited_label")
            if max_devices_value not in (None, 0):
                try:
                    max_devices_int = int(max_devices_value)
                    if max_devices_int >= 0:
                        max_devices_display = str(max_devices_int)
                except (TypeError, ValueError):
                    max_devices_display = str(max_devices_value)
            current_devices_display = "?"
            user_uuid = active.get("user_id")
            devices_response = None
            if user_uuid:
                try:
                    devices_response = await panel_service.get_user_devices(user_uuid)
                except Exception:
                    logging.exception("Failed to load devices for user %s", user_uuid)
            if devices_response is not None:
                devices_count = _devices_count_from_panel_response(devices_response)
                if devices_count is not None:
                    current_devices_display = str(devices_count)
            devices_button_text = get_text(
                "devices_button",
                current_devices=current_devices_display,
                max_devices=max_devices_display,
            )
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=devices_button_text,
                        callback_data="main_action:my_devices",
                    )
                ]
            )
            # Skip the buy-devices button entirely when the user has unlimited
            # devices (max_devices == 0). Otherwise the button leads to an
            # alert "hwid_devices_unlimited_no_topup" — confusing dead end.
            devices_topup_allowed = (
                settings.tariffs_config
                and local_sub
                and local_sub.tariff_key
                and max_devices_value not in (None, 0)
            )
            if devices_topup_allowed:
                try:
                    tariff_for_devices = settings.tariffs_config.require(local_sub.tariff_key)
                    if (
                        tariff_for_devices.billing_model == "period"
                        and tariff_for_devices.hwid_device_packages
                        and tariff_for_devices.hwid_device_packages.for_currency(
                            default_currency_key_for_settings(settings)
                        )
                    ):
                        prepend_rows.append(
                            [
                                InlineKeyboardButton(
                                    text=get_text("buy_hwid_devices_menu_button"),
                                    callback_data="hwid_devices:list",
                                )
                            ]
                        )
                except Exception:
                    pass

        # 2) Auto-renew toggle
        if (
            not traffic_mode
            and local_sub
            and _auto_renew_control_visible(subscription_service, local_sub)
        ):
            toggle_text = (
                get_text("autorenew_disable_button")
                if local_sub.auto_renew_enabled
                else get_text("autorenew_enable_button")
            )
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=toggle_text,
                        callback_data=f"toggle_autorenew:{local_sub.subscription_id}:{1 if not local_sub.auto_renew_enabled else 0}",  # noqa: E501
                    )
                ]
            )

        # 3) Payment methods management (when autopayments enabled)
        if not traffic_mode and settings.yookassa_autopayments_active:
            prepend_rows.append(
                [
                    InlineKeyboardButton(
                        text=get_text("payment_methods_manage_button"), callback_data="pm:manage"
                    )
                ]
            )

        if settings.tariffs_config and local_sub and local_sub.tariff_key:
            tariff_actions = []
            if _has_multiple_enabled_tariffs(settings):
                tariff_actions.append(
                    InlineKeyboardButton(text="Сменить тариф", callback_data="tariff_change:list")
                )
            try:
                tariff = settings.tariffs_config.require(local_sub.tariff_key)
                topup_packages = settings.tariffs_config.topup_packages_for(tariff)
                has_topup_packages = bool(
                    (topup_packages and topup_packages.has_any())
                    or (tariff.premium_topup_packages and tariff.premium_topup_packages.has_any())
                )
            except Exception:
                has_topup_packages = False
            if has_topup_packages:
                tariff_actions.append(
                    InlineKeyboardButton(text="Докупить трафик", callback_data="tariff_topup:list")
                )
            if tariff_actions:
                prepend_rows.append(tariff_actions)

        if prepend_rows:
            kb = prepend_rows + kb
    except Exception:
        pass
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(event, types.CallbackQuery):
        with contextlib.suppress(Exception):
            await event.answer()
        try:
            await callback_message(event).edit_text(
                text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True
            )
        except Exception:
            await bot.send_message(
                chat_id=target.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    else:
        await target.answer(
            text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True
        )


@router.callback_query(F.data == "main_action:my_devices")
async def my_devices_command_handler(
    event: types.Message | types.CallbackQuery,
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
) -> None:
    target = event.message if isinstance(event, types.CallbackQuery) else event
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)

    if not i18n or not target:
        if isinstance(event, types.Message):
            await event.answer(get_text("error_occurred_try_again"))
        return

    if not settings.MY_DEVICES_SECTION_ENABLED:
        if isinstance(event, types.CallbackQuery):
            with contextlib.suppress(Exception):
                await event.answer(get_text("my_devices_feature_disabled"), show_alert=True)
        else:
            await target.answer(get_text("my_devices_feature_disabled"))
        return

    active = await subscription_service.get_active_subscription_details(
        session, _event_user_id(event)
    )
    if not active or not active.get("user_id"):
        message = get_text("subscription_not_active")
        if isinstance(event, types.CallbackQuery):
            with contextlib.suppress(Exception):
                await event.answer(message, show_alert=True)
        else:
            await target.answer(message)
        return

    devices = await panel_service.get_user_devices(active.get("user_id")) if active else None
    if devices is None:
        if isinstance(event, types.CallbackQuery):
            with contextlib.suppress(Exception):
                await event.answer(get_text("no_devices_found"), show_alert=True)
        else:
            await target.answer(get_text("no_devices_found"))
        return

    devices_list_raw = _devices_list_from_panel_response(devices)

    max_devices_value = active.get("max_devices")
    max_devices_display = get_text("devices_unlimited_label")
    if max_devices_value not in (None, 0):
        try:
            max_devices_int = int(max_devices_value)
            if max_devices_int >= 0:
                max_devices_display = str(max_devices_int)
        except (TypeError, ValueError):
            max_devices_display = str(max_devices_value)

    if not devices_list_raw:
        text = get_text("no_devices_details_found_message", max_devices=max_devices_display)
    else:
        devices_list = []
        current_devices = len(devices_list_raw)
        for index, device in enumerate(devices_list_raw, start=1):
            device_model = device.get("deviceModel") or None
            platform = device.get("platform") or None
            user_agent = device.get("userAgent") or None
            os_version = device.get("osVersion") or None
            created_at = device.get("createdAt")
            hwid = device.get("hwid")
            try:
                created_at_str = (
                    datetime.fromisoformat(created_at).strftime("%d.%m.%Y %H:%M")
                    if created_at
                    else "-"
                )
            except Exception:
                created_at_str = str(created_at)

            device_details = get_text(
                "device_details",
                index=index,
                device_model=device_model,
                platform=platform,
                os_version=os_version,
                created_at_str=created_at_str,
                user_agent=user_agent,
                hwid=hwid,
            )
            devices_list.append(device_details)

        text = get_text(
            "my_devices_details",
            devices="\n\n".join(devices_list),
            current_devices=current_devices,
            max_devices=max_devices_display,
        )

    base_markup = get_back_to_main_menu_markup(
        current_lang, i18n, callback_data="main_action:my_subscription"
    )
    kb = base_markup.inline_keyboard

    devices_kb = []
    if settings.tariffs_config and active.get("tariff_key") and max_devices_value != 0:
        try:
            tariff_for_devices = settings.tariffs_config.require(active["tariff_key"])
            if (
                tariff_for_devices.billing_model == "period"
                and tariff_for_devices.hwid_device_packages
                and tariff_for_devices.hwid_device_packages.for_currency(
                    default_currency_key_for_settings(settings)
                )
            ):
                devices_kb.append(
                    [
                        InlineKeyboardButton(
                            text=get_text("buy_hwid_devices_menu_button"),
                            callback_data="hwid_devices:list",
                        )
                    ]
                )
        except Exception:
            pass
    for index, device in enumerate(devices_list_raw, start=1):
        hwid = device.get("hwid")
        if not hwid:
            continue
        device_button_text = get_text(
            "disconnect_device_button", hwid=_shorten_hwid_for_display(hwid), index=index
        )
        hwid_token = _hwid_callback_token(hwid)

        devices_kb.append(
            [
                InlineKeyboardButton(
                    text=device_button_text, callback_data=f"disconnect_device:{hwid_token}"
                )
            ]
        )
    kb = devices_kb + kb
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(event, types.CallbackQuery):
        with contextlib.suppress(Exception):
            await event.answer()
        try:
            await callback_message(event).edit_text(text, reply_markup=markup)
        except Exception:
            await callback_message(event).answer(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)
