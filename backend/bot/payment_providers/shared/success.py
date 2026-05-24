from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import get_connect_and_main_keyboard
from bot.services.notification_service import NotificationService
from bot.utils.config_link import prepare_config_links
from bot.utils.install_links import (
    append_install_share_link_text,
    ensure_user_install_guide_links,
)
from bot.utils.text_sanitizer import sanitize_display_name, username_for_display
from db.dal import payment_dal, user_dal
from db.models import Payment, User

from .common import Translator, format_human_units, make_translator, sale_mode_base

_TRAFFIC_MODES = {"traffic", "traffic_package", "topup", "premium_topup"}
_HWID_DEVICE_MODES = {"hwid_device", "hwid_devices"}


def is_traffic_sale_base(sale_base: str) -> bool:
    return sale_base in _TRAFFIC_MODES


async def resolve_user_language(
    session: AsyncSession,
    *,
    user_id: int,
    db_user: Optional[User],
    settings: Any,
) -> tuple[Optional[User], str]:
    """Return the loaded user and the language to use for messaging."""
    if db_user is None:
        db_user = await user_dal.get_user_by_id(session, user_id)
    language = (
        db_user.language_code if db_user and db_user.language_code else settings.DEFAULT_LANGUAGE
    )
    return db_user, language


async def resolve_inviter_name(
    session: AsyncSession,
    translator: Translator,
    db_user: Optional[User],
) -> str:
    """Return a display name for the user's inviter, or the localized placeholder."""
    placeholder = translator("friend_placeholder")
    if not db_user or not db_user.referred_by_id:
        return placeholder
    inviter = await user_dal.get_user_by_id(session, db_user.referred_by_id)
    if not inviter:
        return placeholder
    if inviter.first_name:
        safe_name = sanitize_display_name(inviter.first_name)
        if safe_name:
            return safe_name
    if inviter.username:
        return username_for_display(inviter.username, with_at=False)
    return placeholder


@dataclass
class SuccessMessage:
    """Inputs for ``build_success_message``."""

    translator: Translator
    sale_mode: str
    months: Any
    base_end_date: Optional[datetime]
    final_end_date: Optional[datetime]
    config_link_text: str
    applied_referee_bonus_days: int = 0
    applied_promo_bonus_days: int = 0
    inviter_name: Optional[str] = None
    fallback_date_text: str = ""


def _fmt_date(dt: Optional[datetime], fallback: str) -> str:
    return dt.strftime("%Y-%m-%d") if dt else fallback


def build_success_message(payload: SuccessMessage) -> str:
    """Render the post-payment user-facing text.

    Picks one of: ``payment_successful_traffic_full`` /
    ``payment_successful_with_referral_bonus_full`` /
    ``payment_successful_with_promo_full`` / ``payment_successful_full``.
    """
    base = sale_mode_base(payload.sale_mode)
    _ = payload.translator
    end_text = _fmt_date(payload.final_end_date, payload.fallback_date_text)

    if is_traffic_sale_base(base):
        return _(
            "payment_successful_traffic_full",
            traffic_gb=format_human_units(payload.months),
            end_date=end_text,
            config_link=payload.config_link_text,
        )
    if base in _HWID_DEVICE_MODES:
        return _(
            "payment_successful_hwid_devices_full",
            count=format_human_units(payload.months),
            config_link=payload.config_link_text,
        )
    if payload.applied_referee_bonus_days and payload.final_end_date:
        base_end_text = _fmt_date(payload.base_end_date or payload.final_end_date, end_text)
        return _(
            "payment_successful_with_referral_bonus_full",
            months=payload.months,
            base_end_date=base_end_text,
            bonus_days=payload.applied_referee_bonus_days,
            final_end_date=end_text,
            inviter_name=payload.inviter_name or _("friend_placeholder"),
            config_link=payload.config_link_text,
        )
    if payload.applied_promo_bonus_days and payload.final_end_date:
        return _(
            "payment_successful_with_promo_full",
            months=payload.months,
            bonus_days=payload.applied_promo_bonus_days,
            end_date=end_text,
            config_link=payload.config_link_text,
        )
    return _(
        "payment_successful_full",
        months=payload.months,
        end_date=end_text,
        config_link=payload.config_link_text,
    )


async def send_success_message_to_user(
    *,
    bot: Bot,
    user_id: int,
    text: str,
    language: str,
    i18n: Any,
    settings: Any,
    config_link_display: Optional[str],
    connect_button_url: Optional[str],
    install_share_url: Optional[str] = None,
    include_keyboard: bool = True,
    log_prefix: str = "payment_providers",
) -> None:
    """Send the rendered success text with the standard connect keyboard."""
    markup = None
    if include_keyboard:
        markup = get_connect_and_main_keyboard(
            language,
            i18n,
            settings,
            config_link_display,
            connect_button_url=connect_button_url,
            install_share_url=install_share_url,
            preserve_message=True,
        )
    try:
        await bot.send_message(
            user_id,
            text,
            reply_markup=markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        logging.exception("%s: failed to notify user %s.", log_prefix, user_id)


async def notify_admins_payment_received(
    *,
    bot: Bot,
    settings: Any,
    i18n: Any,
    user_id: int,
    amount: float,
    currency: str,
    months_for_admin: int,
    traffic_gb_for_admin: Optional[float],
    payment_provider: str,
    username: Optional[str],
    traffic_is_premium: bool,
    tariff_key: Optional[str],
    log_prefix: str = "payment_providers",
    email: Optional[str] = None,
) -> None:
    """Push the standard ``notify_payment_received`` to the admin log channel."""
    try:
        notification_service = NotificationService(bot, settings, i18n)
        await notification_service.notify_payment_received(
            user_id=user_id,
            amount=amount,
            currency=currency,
            months=months_for_admin,
            traffic_gb=traffic_gb_for_admin,
            payment_provider=payment_provider,
            username=username,
            email=email,
            traffic_is_premium=traffic_is_premium,
            tariff_key=tariff_key,
        )
    except Exception:
        logging.exception("%s: failed to notify admins.", log_prefix)


@dataclass
class PaymentSuccessRequest:
    """All the inputs ``finalize_successful_payment`` needs."""

    bot: Bot
    settings: Any
    i18n: Any
    session: AsyncSession
    subscription_service: Any
    referral_service: Any

    payment: Payment
    user_id: int
    amount: float
    currency: str

    sale_mode: str
    months: Any
    traffic_amount: Optional[float]

    provider_subscription: str
    provider_notification: str

    db_user: Optional[User] = None
    log_prefix: str = "payment_providers"
    activation_extra_kwargs: dict = field(default_factory=dict)
    skip_keyboard: bool = False
    text_prefix: Optional[str] = None


@dataclass
class PaymentSuccessOutcome:
    activation: Optional[dict]
    referral_bonus: Optional[dict]
    final_end_date: Optional[datetime]
    applied_referee_bonus_days: int
    applied_promo_bonus_days: int
    db_user: Optional[User]
    language: str


async def finalize_successful_payment(
    req: PaymentSuccessRequest,
) -> Optional[PaymentSuccessOutcome]:
    """Activate the subscription, apply referral bonus, notify user + admins.

    Returns ``None`` if the activation pipeline failed mid-way (errors are
    logged and the session is rolled back). On success returns an outcome
    object so callers can drive extra side-effects (e.g. yookassa LKNPD
    receipts) using the same activation result.
    """
    base = sale_mode_base(req.sale_mode)
    is_subscription = base == "subscription"
    is_traffic = is_traffic_sale_base(base)

    activation_months = (
        int(float(req.months)) if is_subscription else int(float(req.traffic_amount or req.months))
    )
    traffic_gb_for_activation = float(req.traffic_amount or req.months) if is_traffic else None

    try:
        activation = await req.subscription_service.activate_subscription(
            req.session,
            req.user_id,
            activation_months,
            req.amount,
            req.payment.payment_id,
            provider=req.provider_subscription,
            sale_mode=req.sale_mode,
            traffic_gb=traffic_gb_for_activation,
            **req.activation_extra_kwargs,
        )
        referral_bonus = None
        if is_subscription:
            referral_bonus = await req.referral_service.apply_referral_bonuses_for_payment(
                req.session,
                req.user_id,
                activation_months or 1,
                current_payment_db_id=req.payment.payment_id,
                skip_if_active_before_payment=False,
            )
        await req.session.commit()
    except Exception:
        await req.session.rollback()
        logging.exception(
            "%s: failed to activate subscription for payment %s.",
            req.log_prefix,
            req.payment.payment_id,
        )
        return None

    db_user, language = await resolve_user_language(
        req.session,
        user_id=req.user_id,
        db_user=req.db_user,
        settings=req.settings,
    )
    translator = make_translator(req.i18n, language)

    raw_config_link = activation.get("subscription_url") if activation else None
    config_link_display, connect_button_url = await prepare_config_links(
        req.settings, raw_config_link
    )
    config_link_text = config_link_display or translator("config_link_not_available")

    base_end_date = activation.get("end_date") if activation else None
    final_end_date = base_end_date
    applied_referee_bonus_days = 0
    applied_promo_bonus_days = activation.get("applied_promo_bonus_days", 0) if activation else 0

    inviter_name: Optional[str] = None
    if referral_bonus and referral_bonus.get("referee_new_end_date"):
        final_end_date = referral_bonus["referee_new_end_date"]
        applied_referee_bonus_days = referral_bonus.get("referee_bonus_applied_days", 0) or 0
        inviter_name = await resolve_inviter_name(req.session, translator, db_user)

    success_text = build_success_message(
        SuccessMessage(
            translator=translator,
            sale_mode=req.sale_mode,
            months=(
                activation_months
                if is_subscription
                else format_human_units(req.traffic_amount or req.months)
            ),
            base_end_date=base_end_date,
            final_end_date=final_end_date,
            config_link_text=config_link_text,
            applied_referee_bonus_days=applied_referee_bonus_days,
            applied_promo_bonus_days=applied_promo_bonus_days,
            inviter_name=inviter_name,
        )
    )
    if req.text_prefix:
        success_text = f"{req.text_prefix}\n{success_text}"

    install_share_url = None
    if not req.skip_keyboard:
        install_links = await ensure_user_install_guide_links(
            req.session,
            req.settings,
            req.user_id,
        )
        install_share_url = install_links.public_share_url
        if install_share_url:
            try:
                await req.session.commit()
                success_text = append_install_share_link_text(
                    success_text,
                    translator,
                    install_share_url,
                )
            except Exception:
                await req.session.rollback()
                logging.exception(
                    "%s: failed to persist install guide share token for user %s.",
                    req.log_prefix,
                    req.user_id,
                )
                install_share_url = None

    await send_success_message_to_user(
        bot=req.bot,
        user_id=req.user_id,
        text=success_text,
        language=language,
        i18n=req.i18n,
        settings=req.settings,
        config_link_display=config_link_display,
        connect_button_url=connect_button_url,
        install_share_url=install_share_url,
        include_keyboard=not req.skip_keyboard,
        log_prefix=req.log_prefix,
    )

    refreshed_payment = await payment_dal.get_payment_by_db_id(req.session, req.payment.payment_id)
    tariff_key = getattr(refreshed_payment or req.payment, "tariff_key", None)

    await notify_admins_payment_received(
        bot=req.bot,
        settings=req.settings,
        i18n=req.i18n,
        user_id=req.user_id,
        amount=req.amount,
        currency=req.currency,
        months_for_admin=activation_months if is_subscription else 0,
        traffic_gb_for_admin=traffic_gb_for_activation,
        payment_provider=req.provider_notification,
        username=db_user.username if db_user else None,
        email=getattr(db_user, "email", None) if db_user else None,
        traffic_is_premium=base == "premium_topup",
        tariff_key=tariff_key,
        log_prefix=req.log_prefix,
    )

    return PaymentSuccessOutcome(
        activation=activation,
        referral_bonus=referral_bonus,
        final_end_date=final_end_date,
        applied_referee_bonus_days=applied_referee_bonus_days,
        applied_promo_bonus_days=applied_promo_bonus_days,
        db_user=db_user,
        language=language,
    )
