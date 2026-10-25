"""Explicit, private-chat redemption of the existing gift entitlement."""

import logging
import re

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.webapp.cache_helpers import invalidate_webapp_user_caches
from bot.middlewares.i18n import JsonI18n
from bot.services.checkout_addons import checkout_addon_grants
from bot.services.gift_links import GIFT_TOKEN_PATTERN
from bot.services.subscription_gifts import GiftError, activation_conflict, claim_gift
from bot.services.subscription_order_terms import read_subscription_terms
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.callback_answer import callback_message, safe_answer_callback
from config.settings import Settings
from db.dal import gift_dal, payment_dal, subscription_dal, user_dal
from db.models import User

from .start_channel import ensure_required_channel_subscription

router = Router(name="user_gifts")
logger = logging.getLogger(__name__)


async def show_gift_preview(
    message: types.Message,
    *,
    token: str,
    user: User,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    language = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    _ = lambda key, **kw: i18n.gettext(language, key, **kw) if i18n else key
    error = ""
    gift = await gift_dal.by_token(session, token)
    payment = (
        await payment_dal.get_payment_by_db_id(session, int(gift.payment_id)) if gift else None
    )
    if user.is_banned:
        error = "user_is_banned"
    elif gift is None or payment is None:
        error = "wa_gift_not_found"
    elif payment.status != "succeeded" or gift.status == "revoked":
        error = "wa_gift_unavailable"
    elif gift.status in {"activating", "activated"} and gift.recipient_id != user.user_id:
        error = "wa_gift_used"
    elif gift.status == "activated":
        error = "wa_gift_activated_title"
    elif gift.purchaser_id == user.user_id:
        error = "wa_gift_own"
    if error:
        await message.answer(_(error))
        return
    assert gift is not None and payment is not None
    terms = read_subscription_terms(payment)
    if terms is None:
        await message.answer(_("wa_gift_unavailable"))
        return
    active = await subscription_dal.get_active_subscription_by_user_id(session, int(user.user_id))
    catalog = settings.tariffs_config
    conflict = (
        activation_conflict(
            gift,
            payment,
            active,
            catalog.get(payment.tariff_key) if catalog else None,
            settings.USER_TRAFFIC_STRATEGY,
        )
        if gift.status == "ready"
        else ""
    )
    tariff = terms.tariff
    addons = checkout_addon_grants(payment.checkout_bundle_snapshot)
    title = tariff.name(language) if tariff else str(payment.tariff_key or "")
    lines = [
        _("wa_gift_received_title"),
        hd.quote(title),
        _("wa_gift_days", days=terms.duration_days),
        _("wa_gift_confirm_account", account=hd.quote(str(user.minishop_id or user.user_id))),
    ]
    devices = (
        (int(tariff.hwid_device_limit or 0) + addons.device_count)
        if tariff
        else (terms.legacy_limits.get("devices") if terms.legacy_limits else None)
    )
    if devices is not None:
        lines.append(
            _("wa_gift_devices", count=devices) if devices else _("wa_gift_devices_unlimited")
        )
    regular = (
        addons.regular_limit_gb
        if addons.regular_limit_gb is not None
        else (
            tariff.monthly_gb
            if tariff
            else (
                (terms.legacy_limits.get("traffic", 0) or 0) / 1024**3
                if terms.legacy_limits
                else None
            )
        )
    )
    if regular is not None:
        lines.append(
            _("wa_gift_traffic", gb=regular) if regular else _("wa_gift_traffic_unlimited")
        )
    premium = (
        addons.premium_limit_gb
        if addons.premium_limit_gb is not None
        else (tariff.premium_monthly_gb if tariff else None)
    )
    if tariff and tariff.premium_unlimited:
        lines.append(_("wa_gift_premium_unlimited"))
    elif premium is not None:
        lines.append(_("wa_gift_premium", gb=premium))
    if gift.bonus_days:
        lines.append(_("wa_gift_bonus_days", days=gift.bonus_days))
    if gift.regular_bonus_gb:
        lines.append(_("wa_gift_bonus_traffic", gb=gift.regular_bonus_gb))
    if gift.premium_bonus_gb:
        lines.append(_("wa_gift_bonus_premium_traffic", gb=gift.premium_bonus_gb))
    if conflict:
        lines.append(_(f"wa_{conflict}"))
    elif active is not None and str(active.provider) != "trial":
        lines.append(_("wa_gift_extension_note"))
    if gift.status == "activating":
        lines.append(_("wa_gift_activation_retry"))
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            *(
                []
                if conflict
                else [
                    [
                        types.InlineKeyboardButton(
                            text=_(
                                "wa_gift_retry"
                                if gift.status == "activating"
                                else "wa_gift_activate"
                            ),
                            callback_data=f"gift:claim:{token}",
                        )
                    ]
                ]
            ),
            [
                types.InlineKeyboardButton(
                    text=_("wa_gift_later"), callback_data="main_action:back_to_main"
                )
            ],
        ]
    )
    await message.answer("\n\n".join(lines), parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("gift:claim:"))
async def claim_gift_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
) -> None:
    token = str(callback.data or "").removeprefix("gift:claim:")
    if not callback.message or callback.message.chat.type != "private":
        await safe_answer_callback(callback)
        return
    message = callback_message(callback)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    language = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    _ = lambda key: i18n.gettext(language, key) if i18n else key
    user = await user_dal.get_user_by_telegram_id(session, callback.from_user.id)
    if user is None or user.is_banned or not re.fullmatch(GIFT_TOKEN_PATTERN, token):
        await safe_answer_callback(callback, _("wa_gift_unavailable"), show_alert=True)
        return
    user_id = int(user.user_id)
    await state.update_data(pending_gift_token=token)
    if not await ensure_required_channel_subscription(
        callback, settings, i18n, language, session, user
    ):
        return
    await safe_answer_callback(callback)
    try:
        await claim_gift(session, token=token, user_id=user_id, service=subscription_service)
    except GiftError as exc:
        key = f"wa_{exc.code}" if exc.code.startswith("gift_") else "user_is_banned"
        await message.answer(_(key))
        return
    except Exception:
        await session.rollback()
        # Exception text and callback payload may contain the bearer token.
        logger.error("Telegram gift activation failed for recipient %s", user_id)
        await message.answer(_("wa_gift_activation_retry"))
        return
    await state.update_data(pending_gift_token=None)
    await invalidate_webapp_user_caches(settings, user_id, include_devices=True)
    await message.answer(_("wa_gift_activated_title"))
    from .start_menus import send_main_menu

    await send_main_menu(
        callback, settings, i18n_data, subscription_service, session, is_edit=False
    )
