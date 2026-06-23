import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hcode
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.utils.telegram_markup import (
    is_profile_link_error,
    remove_profile_link_buttons,
)
from bot.utils.text_sanitizer import (
    sanitize_display_name,
    sanitize_username,
    username_for_display,
)
from config.settings import Settings
from config.tariffs_config import default_payment_currency_code_for_settings
from db.dal import message_log_dal, user_dal
from db.models import User

from .user_management_common import (
    _admin_user_reference_label,
    _format_traffic_period,
    _format_used_with_period,
)


def get_user_card_keyboard(
    user_id: int, i18n_instance: JsonI18n, lang: str, referrer_id: Optional[int] = None
) -> InlineKeyboardBuilder:
    """Generate keyboard for user management actions"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    # Row 1: Trial and Subscription actions
    builder.button(
        text=_(key="admin_user_reset_trial_button"),
        callback_data=f"user_action:reset_trial:{user_id}",
    )
    builder.button(
        text=_(key="admin_user_add_subscription_button"),
        callback_data=f"user_action:add_subscription:{user_id}",
    )
    builder.button(
        text=_(key="admin_user_change_tariff_button"),
        callback_data=f"user_action:change_tariff:{user_id}",
    )

    # Row 2: Block/Unblock and Message
    builder.button(
        text=_(key="admin_user_toggle_ban_button"),
        callback_data=f"user_action:toggle_ban:{user_id}",
    )
    builder.button(
        text=_(key="admin_user_send_message_button"),
        callback_data=f"user_action:send_message:{user_id}",
    )

    # Row 3: View actions
    builder.button(
        text=_(key="admin_user_view_logs_button"), callback_data=f"user_action:view_logs:{user_id}"
    )
    builder.button(
        text=_(key="admin_user_refresh_button"), callback_data=f"user_action:refresh:{user_id}"
    )

    # Row 3b: Referral details
    builder.button(
        text=_(key="admin_user_invitees_button"),
        callback_data=f"user_action:invitees:{user_id}:0",
    )

    # Row 4: Premium override + traffic grant
    builder.button(
        text=_(key="admin_user_premium_override_button"),
        callback_data=f"user_action:premium_override:{user_id}",
    )
    builder.button(
        text=_(key="admin_user_traffic_grant_button"),
        callback_data=f"user_action:traffic_grant:{user_id}",
    )
    builder.button(
        text=_(key="admin_user_hwid_limit_button"),
        callback_data=f"user_action:hwid_limit:{user_id}",
    )

    # Row 4: Quick links — only for users with a real Telegram profile
    # (synthetic email-only users have a negative user_id with no tg profile).
    has_self_link = user_id > 0
    has_referrer_link = referrer_id is not None and referrer_id > 0
    if has_self_link:
        builder.button(text=_(key="user_card_open_profile_button"), url=f"tg://user?id={user_id}")
    if has_referrer_link:
        builder.button(
            text=_(key="user_card_open_referrer_profile_button"), url=f"tg://user?id={referrer_id}"
        )

    # Row 5: Destructive action
    builder.button(
        text=_(key="admin_user_delete_button"), callback_data=f"user_action:delete_user:{user_id}"
    )

    # Row 6: Navigation
    builder.button(
        text=_(key="admin_user_search_new_button"), callback_data="admin_action:users_search_prompt"
    )
    builder.button(text=_(key="back_to_admin_panel_button"), callback_data="admin_action:main")

    quick_links_count = (1 if has_self_link else 0) + (1 if has_referrer_link else 0)
    if quick_links_count == 0:
        builder.adjust(2, 1, 2, 2, 1, 3, 1, 2)
    else:
        builder.adjust(2, 1, 2, 2, 1, 3, quick_links_count, 1, 2)
    return builder


async def _send_with_profile_link_fallback(
    sender: Callable[..., Awaitable[Any]],
    *,
    text: str,
    markup: Optional[types.InlineKeyboardMarkup],
    user_id: int,
    parse_mode: Optional[str] = "HTML",
) -> None:
    """Send text with markup and fallback if Telegram rejects tg://user buttons."""
    send_kwargs: Dict[str, Any] = {"text": text, "reply_markup": markup}
    if parse_mode is not None:
        send_kwargs["parse_mode"] = parse_mode

    try:
        await sender(**send_kwargs)
    except TelegramBadRequest as exc:
        if not is_profile_link_error(exc):
            raise

        logging.warning(
            "Telegram rejected profile buttons for user %s: %s. Retrying without tg:// links.",
            user_id,
            getattr(exc, "message", "") or str(exc),
        )
        fallback_markup = remove_profile_link_buttons(markup)
        send_kwargs["reply_markup"] = fallback_markup
        await sender(**send_kwargs)


async def format_user_card(
    user: User,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    i18n_instance: JsonI18n,
    lang: str,
    referral_service: Optional[ReferralService] = None,
    *,
    settings: Optional[Settings] = None,
    bot_username: Optional[str] = None,
) -> str:
    """Format user information as a detailed card"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)

    # Basic user info
    card_parts = []
    card_parts.append(f"👤 <b>{_('admin_user_card_title')}</b>\n")

    # User details
    na_value = _("admin_user_na_value")
    safe_first_name = sanitize_display_name(user.first_name) if user.first_name else None
    user_name = safe_first_name or na_value
    if user.username:
        sanitized_username = sanitize_username(user.username)
        if sanitized_username:
            username_display = f"@{sanitized_username}"
        else:
            username_display = username_for_display(user.username, with_at=False)
    else:
        username_display = na_value
    registration_date = (
        user.registration_date.strftime("%Y-%m-%d %H:%M") if user.registration_date else na_value
    )

    card_parts.append(f"{_('admin_user_id_label')} {hcode(str(user.user_id))}")
    card_parts.append(f"{_('admin_user_name_label')} {hcode(user_name)}")
    card_parts.append(f"{_('admin_user_username_label')} {hcode(username_display)}")
    if user.email:
        card_parts.append(f"{_('admin_user_email_label')} {hcode(user.email)}")
    if user.telegram_id and int(user.telegram_id) != int(user.user_id):
        card_parts.append(f"{_('admin_user_telegram_id_label')} {hcode(str(user.telegram_id))}")
    card_parts.append(f"{_('admin_user_language_label')} {hcode(user.language_code or na_value)}")
    card_parts.append(f"{_('admin_user_registration_label')} {hcode(registration_date)}")

    # Ban status
    ban_status = _("admin_user_status_banned") if user.is_banned else _("admin_user_status_active")
    card_parts.append(f"{_('admin_user_status_label')} {ban_status}")

    # Referral info
    if user.referred_by_id:
        referrer = await user_dal.get_referrer_for_user(session, user)
        card_parts.append(
            f"{_('admin_user_invited_by_label')} "
            f"{hcode(_admin_user_reference_label(referrer, user.referred_by_id))}"
        )

    # Panel info
    if user.panel_user_uuid:
        card_parts.append(
            f"{_('admin_user_panel_uuid_label')} {hcode(user.panel_user_uuid[:8] + '...' if len(user.panel_user_uuid) > 8 else user.panel_user_uuid)}"  # noqa: E501
        )

    card_parts.append("")  # Empty line

    # Subscription info
    try:
        subscription_details = await subscription_service.get_active_subscription_details(
            session, user.user_id
        )
        if subscription_details:
            card_parts.append(f"💳 <b>{_('admin_user_subscription_info')}</b>")

            end_date = subscription_details.get("end_date")
            if end_date:
                end_date_str = (
                    end_date.strftime("%Y-%m-%d %H:%M")
                    if isinstance(end_date, datetime)
                    else str(end_date)
                )
                card_parts.append(
                    f"{_('admin_user_subscription_active_until')} {hcode(end_date_str)}"
                )

            status = subscription_details.get("status_from_panel", "UNKNOWN")
            card_parts.append(f"{_('admin_user_panel_status_label')} {hcode(status)}")

            traffic_limit = subscription_details.get("traffic_limit_bytes")
            traffic_used = subscription_details.get("traffic_used_bytes")
            traffic_strategy = subscription_details.get("traffic_limit_strategy")
            period_label = _format_traffic_period(traffic_strategy, _)
            if traffic_used is not None or traffic_limit is not None:
                used_display = _("traffic_na")
                if traffic_used is not None:
                    traffic_used_gb = traffic_used / (1024**3)
                    used_display = f"{traffic_used_gb:.2f}GB"
                used_display = _format_used_with_period(_, used_display, period_label)

                if traffic_limit:
                    traffic_limit_gb = traffic_limit / (1024**3)
                    limit_display = f"{traffic_limit_gb:.2f}GB"
                else:
                    limit_display = _("traffic_unlimited")

                card_parts.append(
                    f"{_('admin_user_traffic_label')} {hcode(f'{used_display} / {limit_display}')}"
                )

            max_devices = subscription_details.get("max_devices")
            extra_hwid_devices = int(subscription_details.get("extra_hwid_devices") or 0)
            if max_devices is not None:
                if int(max_devices) == 0:
                    devices_display = _("admin_hwid_limit_state_unlimited")
                elif extra_hwid_devices > 0:
                    base_hwid_limit = subscription_details.get("base_hwid_device_limit")
                    if base_hwid_limit is None:
                        devices_display = _("admin_hwid_limit_state_count", count=int(max_devices))
                    else:
                        devices_display = _(
                            "admin_hwid_limit_state_with_extra",
                            total=int(max_devices),
                            base=int(base_hwid_limit),
                            extra=extra_hwid_devices,
                        )
                else:
                    devices_display = _("admin_hwid_limit_state_count", count=int(max_devices))
                card_parts.append(f"{_('admin_user_hwid_limit_label')} {hcode(devices_display)}")

            premium_unlimited = bool(subscription_details.get("premium_unlimited_override"))
            premium_bonus_bytes = int(subscription_details.get("premium_bonus_bytes") or 0)
            if premium_unlimited:
                card_parts.append(
                    f"{_('admin_user_premium_override_label')} {hcode(_('admin_user_premium_override_unlimited'))}"  # noqa: E501
                )
            elif premium_bonus_bytes > 0:
                bonus_gb = premium_bonus_bytes / (1024**3)
                card_parts.append(
                    f"{_('admin_user_premium_override_label')} {hcode(_('admin_user_premium_override_bonus_value', gb=f'{bonus_gb:.2f}'))}"  # noqa: E501
                )
        else:
            card_parts.append(
                f"{_('admin_user_subscription_label')} {hcode(_('admin_user_subscription_none'))}"
            )
    except Exception as e:
        logging.error(f"Error getting subscription details for user {user.user_id}: {e}")
        card_parts.append(
            f"{_('admin_user_subscription_label')} {hcode(_('admin_user_subscription_error'))}"
        )

    # Statistics
    try:
        # Count user logs
        logs_count = await message_log_dal.count_user_message_logs(session, user.user_id)
        card_parts.append(f"{_('admin_user_actions_count_label')} {hcode(str(logs_count))}")

        # Check if user had any subscriptions
        had_subscriptions = await subscription_service.has_had_any_subscription(
            session, user.user_id
        )
        trial_status = (
            _("admin_user_trial_used") if had_subscriptions else _("admin_user_trial_not_used")
        )
        card_parts.append(f"{_('admin_user_trial_label')} {hcode(trial_status)}")

        # Financial analytics (admin-only)
        try:
            from db.dal import payment_dal

            currency = default_payment_currency_code_for_settings(settings)

            # Total amount paid by this user
            total_paid = await payment_dal.get_user_total_paid(session, user.user_id)
            card_parts.append(
                f"{_('admin_user_total_paid_label')} {hcode(f'{total_paid:.2f} {currency}')}"
            )

            # Total revenue from referrals
            referral_revenue = await payment_dal.get_referral_revenue(session, user.user_id)
            referral_revenue_text = hcode(f"{referral_revenue:.2f} {currency}")
            card_parts.append(f"{_('admin_user_referral_revenue_label')} {referral_revenue_text}")
        except Exception as e_fin:
            logging.error(
                f"Failed to build financial analytics for admin card {user.user_id}: {e_fin}"
            )

        # Referral stats
        if referral_service is not None:
            try:
                stats = await referral_service.get_referral_stats(session, user.user_id)
                invited_count = stats.get("invited_count", 0)
                purchased_count = stats.get("purchased_count", 0)
                card_parts.append(
                    f"{_('admin_user_invited_friends_label')} {hcode(str(invited_count))}"
                )
                card_parts.append(
                    f"{_('admin_user_ref_purchased_label')} {hcode(str(purchased_count))}"
                )
            except Exception as e_rs:
                logging.error(
                    f"Failed to build referral stats for admin card {user.user_id}: {e_rs}"
                )

    except Exception as e:
        logging.error(f"Error getting user statistics for {user.user_id}: {e}")

    # Links section: subscription page + both referral links.
    link_lines: list[str] = []

    # Subscription URL — the user's panel-issued config link.
    if user.panel_user_uuid:
        try:
            panel_data = await subscription_service.panel_service.get_user_by_uuid(
                user.panel_user_uuid
            )
            sub_url = panel_data.get("subscriptionUrl") if panel_data else None
            if sub_url:
                link_lines.append(f"{_('admin_user_subscription_url_label')} {sub_url}")
        except Exception as exc_sub:
            logging.warning(
                "Failed to fetch subscriptionUrl for user %s: %s", user.user_id, exc_sub
            )

    # Referral links — bot deep-link + webapp deep-link.
    if referral_service is not None and bot_username:
        try:
            bot_ref_link = await referral_service.generate_referral_link(
                session, bot_username, user.user_id
            )
            if bot_ref_link:
                link_lines.append(f"{_('admin_user_ref_bot_link_label')} {bot_ref_link}")
        except Exception as exc_bot_ref:
            logging.warning(
                "Failed to build bot referral link for %s: %s", user.user_id, exc_bot_ref
            )

    if settings is not None:
        webapp_base = settings.SUBSCRIPTION_MINI_APP_URL
        if webapp_base:
            try:
                code = await user_dal.ensure_referral_code(session, user)
                if code:
                    from urllib.parse import parse_qsl, urlsplit, urlunsplit

                    parts = urlsplit(webapp_base)
                    query = dict(parse_qsl(parts.query, keep_blank_values=True))
                    query["ref"] = f"u{code}"
                    webapp_ref_link = urlunsplit(
                        (
                            parts.scheme,
                            parts.netloc,
                            parts.path,
                            "&".join(f"{k}={v}" for k, v in query.items()),
                            parts.fragment,
                        )
                    )
                    link_lines.append(f"{_('admin_user_ref_webapp_link_label')} {webapp_ref_link}")
            except Exception as exc_web_ref:
                logging.warning(
                    "Failed to build webapp referral link for %s: %s", user.user_id, exc_web_ref
                )

    if link_lines:
        card_parts.append("")
        card_parts.append(_("admin_user_links_section_title"))
        card_parts.extend(link_lines)

    return "\n".join(card_parts)
