import logging
import re
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import ReferralBonusGrantedPayload
from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.registration_invite_gate import evaluate_registration_invite
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.telegram_notifications import TELEGRAM_NOTIFICATIONS_ENABLED
from bot.utils.callback_answer import (
    message_bot,
    message_from_user,
)
from bot.utils.install_links import (
    append_install_share_link_text,
    ensure_user_install_guide_links,
)
from bot.utils.mini_app_url import subscription_mini_app_checkout_code_url
from bot.utils.text_sanitizer import sanitize_display_name, sanitize_username
from config.settings import Settings
from db.dal import user_dal

from .start_channel import ensure_required_channel_subscription
from .start_common import (
    _resolve_referrer_from_start_ref,
    router,
)
from .start_menus import send_main_menu


@router.message(CommandStart())
@router.message(CommandStart(magic=F.args.regexp(r"^ref_([A-Za-z0-9_-]{1,64})$").as_("ref_match")))
@router.message(
    CommandStart(magic=F.args.regexp(r"^promo_([A-Za-z0-9_-]{1,100})$").as_("promo_match"))
)
@router.message(CommandStart(magic=F.args.regexp(r"^admin_user_(\d+)$").as_("admin_user_match")))
@router.message(CommandStart(magic=F.args.regexp(r"^ticket_(\d+)$").as_("ticket_match")))
@router.message(CommandStart(magic=F.args.regexp(r"^notifications$").as_("notifications_match")))
@router.message(CommandStart(magic=F.args.regexp(r"^page_ref$").as_("page_ref_match")))
@router.message(
    CommandStart(
        magic=F.args.regexp(
            r"^(?!ref_|promo_|admin_user_|ticket_|notifications$|page_ref$|webapp_auth_)([A-Za-z0-9_\-]{2,64})$"
        ).as_("ad_param_match")
    )
)
async def start_command_handler(
    message: types.Message,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    referral_service: ReferralService,
    session: AsyncSession,
    ref_match: Optional[re.Match] = None,
    promo_match: Optional[re.Match] = None,
    page_ref_match: Optional[re.Match] = None,
    ad_param_match: Optional[re.Match] = None,
    admin_user_match: Optional[re.Match] = None,
    ticket_match: Optional[re.Match] = None,
    notifications_match: Optional[re.Match] = None,
) -> None:
    await state.clear()
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    user = message_from_user(message)
    user_id = user.id

    if admin_user_match and user_id in settings.ADMIN_IDS:
        target_user_id = int(admin_user_match.group(1))
        target_user = await user_dal.get_user_by_id(session, target_user_id)
        if not target_user:
            await message.answer(_("admin_user_not_found", input=hd.quote(str(target_user_id))))
            return

        try:
            from bot.handlers.admin.user_management import (
                _send_with_profile_link_fallback,
                format_user_card,
                get_user_card_keyboard,
            )

            referral_service = ReferralService(
                settings, subscription_service, message_bot(message), i18n
            )
            user_card_text = await format_user_card(
                target_user,
                session,
                subscription_service,
                i18n,
                current_lang,
                referral_service,
            )
            keyboard = get_user_card_keyboard(
                target_user.user_id,
                i18n,
                current_lang,
                target_user.referred_by_id,
            )

            await _send_with_profile_link_fallback(
                message.answer,
                text=user_card_text,
                markup=keyboard.as_markup(),
                user_id=target_user.user_id,
                parse_mode="HTML",
            )
            return
        except Exception as e_admin_card:
            logging.error(
                "Failed to open admin user card via deep-link for %s: %s",
                target_user_id,
                e_admin_card,
                exc_info=True,
            )
            await message.answer(_("admin_user_card_error"))
            return

    if ticket_match:
        ticket_id = int(ticket_match.group(1))
        base_url = (settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
        if base_url:
            ticket_url = f"{base_url.rstrip('/')}/support/{ticket_id}"
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=i18n.gettext(current_lang, "wa_support_open_ticket")
                            if i18n
                            else "Открыть тикет",
                            web_app=types.WebAppInfo(url=ticket_url),
                        )
                    ]
                ]
            )
            await message.answer(
                i18n.gettext(current_lang, "wa_support_open_ticket_hint")
                if i18n
                else "Откройте тикет в Mini App.",
                reply_markup=keyboard,
            )
            return

    referred_by_user_id: Optional[int] = None
    raw_ref_value: Optional[str] = None
    promo_code_to_apply: Optional[str] = None
    should_open_referral_from_start = False
    ad_start_param: Optional[str] = None
    notifications_start_requested = bool(notifications_match)

    if ref_match:
        raw_ref_value = ref_match.group(1)
    elif promo_match:
        promo_code_to_apply = promo_match.group(1)
        logging.info(f"User {user_id} started with promo code: {promo_code_to_apply}")
    elif notifications_start_requested:
        logging.info("User %s started bot from notifications deep-link.", user_id)
    elif page_ref_match:
        should_open_referral_from_start = True
        logging.info(f"User {user_id} started with page_ref deep-link.")
    elif ad_param_match:
        ad_start_param = ad_param_match.group(1)
        logging.info(f"User {user_id} started with ad start param: {ad_start_param}")

    sanitized_username = sanitize_username(user.username)
    sanitized_first_name = sanitize_display_name(user.first_name)
    sanitized_last_name = sanitize_display_name(user.last_name)
    notification_status_now = datetime.now(timezone.utc)

    db_user = await user_dal.get_user_by_id(session, user_id)
    is_existing_user = db_user is not None
    if db_user:
        if raw_ref_value:
            referred_by_user_id = await _resolve_referrer_from_start_ref(
                session,
                raw_ref_value,
                settings=settings,
                current_user_id=user_id,
            )
    else:
        invite_check = await evaluate_registration_invite(
            session,
            raw_ref_value,
            settings=settings,
            current_user_id=user_id,
            source="telegram_start",
        )
        if invite_check.requires_invite:
            await message.answer(_("registration_invite_required"))
            return
        referred_by_user_id = invite_check.referrer_user_id

    if not db_user:
        user_data_to_create = {
            "user_id": user_id,
            "telegram_id": user_id,
            "username": sanitized_username,
            "first_name": sanitized_first_name,
            "last_name": sanitized_last_name,
            "language_code": current_lang,
            "referred_by_id": referred_by_user_id,
            "registration_date": datetime.now(timezone.utc),
            "telegram_notifications_status": TELEGRAM_NOTIFICATIONS_ENABLED,
            "telegram_notifications_checked_at": notification_status_now,
            "telegram_notifications_enabled_at": notification_status_now,
            "telegram_notifications_blocked_at": None,
        }
        try:
            db_user, created = await user_dal.create_user(session, user_data_to_create)

            if created:
                try:
                    await session.commit()
                except Exception as commit_error:
                    await session.rollback()
                    logging.error(
                        f"Failed to commit new user {user_id}: {commit_error}",
                        exc_info=True,
                    )
                    await message.answer(_("error_occurred_processing_request"))
                    return

                logging.info(
                    f"New user {user_id} added to session. Referred by: {referred_by_user_id or 'N/A'}."  # noqa: E501
                )

                # Auto-grant referral welcome bonus to newly registered referred users.
                referral_welcome_days = max(0, int(settings.referral_settings.welcome_bonus_days))
                if referred_by_user_id and referral_welcome_days > 0:
                    try:
                        default_tariff_key = None
                        tariffs_config = settings.tariffs_config
                        if tariffs_config:
                            default_tariff_key = getattr(tariffs_config, "default_tariff", None)
                        referral_bonus_end_date = (
                            await subscription_service.extend_active_subscription_days(
                                session,
                                user_id,
                                referral_welcome_days,
                                reason="referral_welcome_bonus",
                                tariff_key=default_tariff_key,
                            )
                        )
                        if referral_bonus_end_date:
                            # Mark the welcome bonus as claimed so it cannot be
                            # re-granted later (e.g. via the WebApp claim route
                            # once this grant expires).
                            db_user.referral_welcome_bonus_claimed_at = datetime.now(timezone.utc)
                            await session.commit()
                            await events.emit_model(
                                ReferralBonusGrantedPayload(
                                    referee_user_id=user_id,
                                    referee_bonus_days=referral_welcome_days,
                                    referee_new_end_date=referral_bonus_end_date,
                                    inviter_bonus_applied=False,
                                    payment_db_id=None,
                                    reason="welcome",
                                ),
                                exclude_unset=True,
                            )
                            logging.info(
                                "Referral welcome bonus applied: user %s got %s days, new end date %s.",  # noqa: E501
                                user_id,
                                referral_welcome_days,
                                referral_bonus_end_date.isoformat(),
                            )
                            await message.answer(
                                _(
                                    "referral_welcome_bonus_applied",
                                    days=referral_welcome_days,
                                    end_date=referral_bonus_end_date.strftime("%d.%m.%Y %H:%M:%S"),
                                ),
                                parse_mode="HTML",
                            )
                        else:
                            await session.rollback()
                            logging.warning(
                                "Referral welcome bonus was not applied for user %s (referred by %s).",  # noqa: E501
                                user_id,
                                referred_by_user_id,
                            )
                    except Exception as referral_bonus_error:
                        await session.rollback()
                        logging.error(
                            "Failed to apply referral welcome bonus for user %s: %s",
                            user_id,
                            referral_bonus_error,
                            exc_info=True,
                        )

        except Exception as e_create:
            logging.error(f"Failed to add new user {user_id} to session: {e_create}", exc_info=True)
            await message.answer(_("error_occurred_processing_request"))
            return
    else:
        update_payload = {}
        if db_user.language_code != current_lang:
            update_payload["language_code"] = current_lang
        if db_user.telegram_id != user_id:
            update_payload["telegram_id"] = user_id
        if db_user.telegram_notifications_status != TELEGRAM_NOTIFICATIONS_ENABLED:
            update_payload["telegram_notifications_status"] = TELEGRAM_NOTIFICATIONS_ENABLED
            update_payload["telegram_notifications_checked_at"] = notification_status_now
            update_payload["telegram_notifications_enabled_at"] = notification_status_now
            update_payload["telegram_notifications_blocked_at"] = None
        # Set referral only if not already set AND user is not currently active.
        # This allows previously subscribed but currently inactive users to be attributed.
        if referred_by_user_id and db_user.referred_by_id is None:
            try:
                is_active_now = await subscription_service.has_active_subscription(session, user_id)
            except Exception:
                is_active_now = False
            if not is_active_now:
                update_payload["referred_by_id"] = referred_by_user_id
        if sanitized_username != db_user.username:
            update_payload["username"] = sanitized_username
        if sanitized_first_name != db_user.first_name:
            update_payload["first_name"] = sanitized_first_name
        if sanitized_last_name != db_user.last_name:
            update_payload["last_name"] = sanitized_last_name

        if update_payload:
            try:
                await user_dal.update_user(session, user_id, update_payload)

                logging.info(f"Updated existing user {user_id} in session: {update_payload}")
            except Exception as e_update:
                logging.error(
                    f"Failed to update existing user {user_id} in session: {e_update}",
                    exc_info=True,
                )

    # Attribute user to ad campaign if start param provided
    if ad_start_param:
        try:
            from db.dal import ad_dal as _ad_dal

            campaign = await _ad_dal.get_campaign_by_start_param(session, ad_start_param)
            if campaign and campaign.is_active:
                await _ad_dal.ensure_attribution(
                    session, user_id=user_id, campaign_id=campaign.ad_campaign_id
                )
                await session.commit()
        except Exception as e_attr:
            logging.error(f"Failed to attribute user {user_id} to ad '{ad_start_param}': {e_attr}")
            try:
                await session.rollback()
            except Exception:
                pass

    if not await ensure_required_channel_subscription(
        message, settings, i18n, current_lang, session, db_user
    ):
        return

    open_referral_page_for_existing_user = should_open_referral_from_start and is_existing_user

    # Send welcome message if not disabled
    if (
        not settings.DISABLE_WELCOME_MESSAGE
        and not open_referral_page_for_existing_user
        and not notifications_start_requested
    ):
        await message.answer(_(key="welcome", user_name=hd.quote(user.full_name)))

    if notifications_start_requested:
        await message.answer(_("telegram_notifications_started"), parse_mode="HTML")

    # Auto-apply promo code if provided via start parameter
    if promo_code_to_apply:
        try:
            from bot.services.promo_code_service import PromoCheckoutRequired, PromoCodeService

            promo_code_service = PromoCodeService(
                settings, subscription_service, message_bot(message), i18n
            )

            success, result = await promo_code_service.apply_promo_code(
                session, user_id, promo_code_to_apply, current_lang
            )

            if success and isinstance(result, PromoCheckoutRequired):
                await session.commit()
                checkout_url = subscription_mini_app_checkout_code_url(
                    settings,
                    result.code or promo_code_to_apply,
                )
                if checkout_url:
                    keyboard = types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                types.InlineKeyboardButton(
                                    text=_("open_mini_app"),
                                    web_app=types.WebAppInfo(url=checkout_url),
                                )
                            ]
                        ]
                    )
                    await message.answer(
                        _(
                            "promo_code_requires_checkout",
                            effect=result.effect_summary,
                        ),
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    )
                    return
                await message.answer(
                    _(
                        "promo_code_requires_checkout",
                        effect=result.effect_summary,
                    ),
                    parse_mode="HTML",
                )
                return

            if success:
                await session.commit()
                logging.info(f"Auto-applied promo code '{promo_code_to_apply}' for user {user_id}")

                # Get updated subscription details
                active = await subscription_service.get_active_subscription_details(
                    session, user_id
                )
                config_link_display = active.get("config_link") if active else None
                connect_button_url = active.get("connect_button_url") if active else None
                config_link_text = config_link_display or _("config_link_not_available")

                new_end_date = result if isinstance(result, datetime) else None

                promo_success_text = _(
                    "promo_code_applied_success_full",
                    end_date=(
                        new_end_date.strftime("%d.%m.%Y %H:%M:%S") if new_end_date else "N/A"
                    ),
                    config_link=config_link_text,
                )
                install_links = await ensure_user_install_guide_links(session, settings, user_id)
                install_share_url = install_links.public_share_url
                if install_share_url:
                    try:
                        await session.commit()
                        promo_success_text = append_install_share_link_text(
                            promo_success_text,
                            _,
                            install_share_url,
                        )
                    except Exception:
                        await session.rollback()
                        logging.exception(
                            "Failed to persist install guide share token for promo user %s.",
                            user_id,
                        )
                        install_share_url = None

                from bot.keyboards.inline.user_keyboards import get_connect_and_main_keyboard

                await message.answer(
                    promo_success_text,
                    reply_markup=get_connect_and_main_keyboard(
                        current_lang,
                        i18n,
                        settings,
                        config_link_display,
                        connect_button_url=connect_button_url,
                        install_share_url=install_share_url,
                    ),
                    parse_mode="HTML",
                )

                # Don't show main menu if promo was successfully applied
                return
            else:
                await session.commit()
                logging.warning(
                    f"Failed to auto-apply promo code '{promo_code_to_apply}' for user {user_id}: {result}"  # noqa: E501
                )
                await message.answer(str(result), parse_mode="HTML")
                # Continue to show main menu if promo failed

        except Exception as e:
            logging.error(
                f"Error auto-applying promo code '{promo_code_to_apply}' for user {user_id}: {e}"
            )
            await session.rollback()

    if open_referral_page_for_existing_user:
        from . import referral as user_referral_handlers

        await user_referral_handlers.referral_command_handler(
            message, settings, i18n_data, referral_service, message_bot(message), session
        )
        return

    await send_main_menu(message, settings, i18n_data, subscription_service, session, is_edit=False)
