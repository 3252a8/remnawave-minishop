from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import (
    PaymentSucceededPayload,
    ReferralBonusGrantedPayload,
    SubscriptionCreatedPayload,
    SubscriptionExtendedPayload,
)
from bot.infra.payment_events import build_payment_succeeded_payload
from bot.keyboards.inline.user_keyboards import get_connect_and_main_keyboard
from bot.utils.config_link import prepare_config_links
from bot.utils.install_links import ensure_user_install_guide_links
from bot.utils.text_sanitizer import sanitize_display_name, username_for_display
from db.dal import payment_dal, user_dal
from db.models import Payment, User

from .common import (
    Translator,
    format_human_units,
    make_translator,
    payment_units_for_activation,
    sale_mode_base,
    sale_mode_tariff_key,
)

logger = logging.getLogger(__name__)

_TRAFFIC_MODES = {"traffic", "traffic_package", "topup", "premium_topup"}
_HWID_DEVICE_MODES = {"hwid_device", "hwid_devices", "hwid_devices_renewal"}
PAYMENT_STATUS_PENDING_FINALIZATION = "succeeded_pending_finalization"


def is_traffic_sale_base(sale_base: str) -> bool:
    return sale_base in _TRAFFIC_MODES


async def resolve_user_language(
    session: AsyncSession,
    *,
    user_id: int,
    db_user: User | None,
    settings: Any,
) -> tuple[User | None, str]:
    """Return the loaded user and the language to use for messaging."""
    if db_user is None:
        db_user = await user_dal.get_user_by_id(session, user_id)
    language = (
        db_user.language_code if db_user and db_user.language_code else settings.DEFAULT_LANGUAGE
    )
    return db_user, str(language)


async def resolve_inviter_name(
    session: AsyncSession,
    translator: Translator,
    db_user: User | None,
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
            return str(safe_name)
    if inviter.username:
        return str(username_for_display(inviter.username, with_at=False))
    return placeholder


@dataclass
class SuccessMessage:
    """Inputs for ``build_success_message``."""

    translator: Translator
    sale_mode: str
    months: Any
    base_end_date: datetime | None
    final_end_date: datetime | None
    applied_referee_bonus_days: int = 0
    applied_promo_bonus_days: int = 0
    inviter_name: str | None = None
    fallback_date_text: str = ""


def _fmt_date(dt: datetime | None, fallback: str) -> str:
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
        )
    if base in _HWID_DEVICE_MODES:
        return _(
            "payment_successful_hwid_devices_full",
            count=format_human_units(payload.months),
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
        )
    if payload.applied_promo_bonus_days and payload.final_end_date:
        return _(
            "payment_successful_with_promo_full",
            months=payload.months,
            bonus_days=payload.applied_promo_bonus_days,
            end_date=end_text,
        )
    return _(
        "payment_successful_full",
        months=payload.months,
        end_date=end_text,
    )


def append_hwid_renewal_note(
    text: str,
    translator: Translator,
    *,
    count: Any,
    valid_until: datetime | None,
) -> str:
    try:
        count_int = int(count or 0)
    except (TypeError, ValueError):
        count_int = 0
    if count_int <= 0:
        return text
    date_text = valid_until.strftime("%Y-%m-%d") if valid_until else ""
    note = translator(
        "payment_successful_hwid_devices_renewal_note",
        count=format_human_units(count_int),
        date=date_text,
    )
    return f"{text}\n\n{note}"


def append_hwid_renewed_note(
    text: str,
    translator: Translator,
    *,
    count: Any,
    valid_until: datetime | None,
) -> str:
    try:
        count_int = int(count or 0)
    except (TypeError, ValueError):
        count_int = 0
    if count_int <= 0:
        return text
    date_text = valid_until.strftime("%Y-%m-%d") if valid_until else ""
    note = translator(
        "payment_successful_hwid_devices_renewed_note",
        count=format_human_units(count_int),
        date=date_text,
    )
    return f"{text}\n\n{note}"


async def send_success_message_to_user(
    *,
    bot: Bot,
    user_id: int,
    text: str,
    language: str,
    i18n: Any,
    settings: Any,
    config_link_display: str | None,
    connect_button_url: str | None,
    install_share_url: str | None = None,
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
        logger.exception("%s: failed to notify user %s.", log_prefix, user_id)


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
    traffic_amount: float | None

    provider_subscription: str
    provider_notification: str

    db_user: User | None = None
    log_prefix: str = "payment_providers"
    activation_extra_kwargs: dict = field(default_factory=dict)
    skip_keyboard: bool = False
    skip_user_notification: bool = False
    text_prefix: str | None = None


@dataclass
class PaymentSuccessOutcome:
    activation: dict | None
    referral_bonus: dict | None
    final_end_date: datetime | None
    applied_referee_bonus_days: int
    applied_promo_bonus_days: int
    db_user: User | None
    language: str


async def _mark_activation_failed(req: PaymentSuccessRequest, payment_id: int) -> None:
    await req.session.rollback()
    try:
        await payment_dal.update_payment_status_by_db_id(
            req.session,
            payment_id,
            "activation_failed",
        )
        await req.session.commit()
    except Exception:
        await req.session.rollback()
        logger.exception(
            "%s: failed to mark payment %s activation_failed.",
            req.log_prefix,
            payment_id,
        )


async def finalize_successful_payment(
    req: PaymentSuccessRequest,
) -> PaymentSuccessOutcome | None:
    """Activate the subscription, apply referral bonus, notify user, and emit events.

    Returns ``None`` if the activation pipeline failed mid-way (errors are
    logged and the session is rolled back). On success returns an outcome
    object so callers can drive extra side-effects (e.g. yookassa LKNPD
    receipts) using the same activation result.
    """
    requested_payment_id = int(req.payment.payment_id)
    locked_payment = await payment_dal.get_payment_by_db_id_for_update(
        req.session, requested_payment_id
    )
    if locked_payment is None:
        logger.error(
            "%s: payment %s disappeared before finalization.",
            req.log_prefix,
            requested_payment_id,
        )
        return None
    payment_id = int(locked_payment.payment_id)
    if str(locked_payment.status or "").strip().lower() == "succeeded":
        logger.info(
            "%s: skipping duplicate finalization for payment %s.",
            req.log_prefix,
            payment_id,
        )
        return None
    req.payment = locked_payment

    # Payment callbacks are adapter boundaries.  Entitlement identity and
    # quantity must come from the server-created invoice, never from callback
    # metadata passed by an individual provider implementation.
    locked_user = await user_dal.lock_user_by_id(req.session, int(locked_payment.user_id))
    if locked_user is None:
        logger.error(
            "%s: payment %s references missing user %s.",
            req.log_prefix,
            payment_id,
            locked_payment.user_id,
        )
        return None
    req.user_id = int(locked_payment.user_id)
    req.db_user = locked_user
    stored_amount = getattr(locked_payment, "amount", None)
    if stored_amount is not None:
        req.amount = float(stored_amount)
    stored_currency = str(getattr(locked_payment, "currency", "") or "").strip()
    if stored_currency:
        req.currency = stored_currency
    stored_sale_mode = str(getattr(locked_payment, "sale_mode", "") or "").strip()
    if stored_sale_mode:
        req.sale_mode = stored_sale_mode
    stored_provider = str(getattr(locked_payment, "provider", "") or "").strip()
    if stored_provider:
        req.provider_subscription = stored_provider
    req.months = payment_units_for_activation(locked_payment, req.sale_mode)
    req.traffic_amount = (
        float(req.months) if is_traffic_sale_base(sale_mode_base(req.sale_mode)) else None
    )

    base = sale_mode_base(req.sale_mode)
    is_subscription = base == "subscription"
    is_traffic = is_traffic_sale_base(base)

    activation_months = (
        int(float(req.months)) if is_subscription else int(float(req.traffic_amount or req.months))
    )
    traffic_gb_for_activation = float(req.traffic_amount or req.months) if is_traffic else None
    effective_tariff_key = str(
        getattr(req.payment, "tariff_key", "") or ""
    ).strip() or sale_mode_tariff_key(req.sale_mode)
    activation_extra_kwargs = dict(req.activation_extra_kwargs or {})
    if effective_tariff_key:
        activation_extra_kwargs["tariff_key"] = effective_tariff_key
    else:
        activation_extra_kwargs.pop("tariff_key", None)

    try:
        activation = await req.subscription_service.activate_subscription(
            req.session,
            req.user_id,
            activation_months,
            req.amount,
            payment_id,
            provider=req.provider_subscription,
            sale_mode=req.sale_mode,
            traffic_gb=traffic_gb_for_activation,
            promo_code_id_from_payment=getattr(req.payment, "promo_code_id", None),
            **activation_extra_kwargs,
        )
        if not activation or (is_subscription and not activation.get("end_date")):
            logger.error(
                "%s: activation returned no usable subscription state for payment %s.",
                req.log_prefix,
                payment_id,
            )
            await _mark_activation_failed(req, payment_id)
            return None
        referral_bonus = None
        if is_subscription:
            try:
                referral_savepoint = await req.session.begin_nested()
                try:
                    referral_bonus = await req.referral_service.apply_referral_bonuses_for_payment(
                        req.session,
                        req.user_id,
                        activation_months or 1,
                        current_payment_db_id=payment_id,
                        skip_if_active_before_payment=False,
                        tariff_key=effective_tariff_key,
                    )
                except Exception:
                    await referral_savepoint.rollback()
                    raise
                else:
                    await referral_savepoint.commit()
            except Exception:
                referral_bonus = None
                logger.exception(
                    "%s: referral bonus failed for payment %s; keeping the paid entitlement.",
                    req.log_prefix,
                    payment_id,
                )
        await payment_dal.update_payment_status_by_db_id(
            req.session,
            payment_id,
            "succeeded",
        )
        await req.session.commit()
    except Exception:
        logger.exception(
            "%s: failed to activate subscription for payment %s.",
            req.log_prefix,
            payment_id,
        )
        await _mark_activation_failed(req, payment_id)
        return None

    await events.emit_model(
        PaymentSucceededPayload.model_validate(
            build_payment_succeeded_payload(
                user_id=req.user_id,
                payment_db_id=payment_id,
                provider=req.provider_subscription,
                notification_provider=req.provider_notification,
                amount=req.amount,
                currency=req.currency,
                sale_mode=req.sale_mode,
                tariff_key=effective_tariff_key,
                months=activation_months if is_subscription else None,
                traffic_gb=traffic_gb_for_activation,
                payment=req.payment,
                activation=activation,
                end_date=events.iso(activation.get("end_date") if activation else None),
                is_auto_renew=False,
            )
        )
    )
    if is_subscription and activation:
        subscription_payload_cls = (
            SubscriptionExtendedPayload
            if activation.get("was_extension")
            else SubscriptionCreatedPayload
        )
        await events.emit_model(
            subscription_payload_cls(
                user_id=req.user_id,
                subscription_id=activation.get("subscription_id"),
                tariff_key=activation.get("tariff_key"),
                end_date=activation.get("end_date"),
                provider=req.provider_subscription,
                months=activation_months,
                payment_db_id=payment_id,
            )
        )
    referral_event_payload = (
        referral_bonus.get("event_payload") if isinstance(referral_bonus, dict) else None
    )
    if referral_event_payload:
        await events.emit_model(ReferralBonusGrantedPayload.model_validate(referral_event_payload))

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

    base_end_date = activation.get("end_date") if activation else None
    final_end_date = base_end_date
    applied_referee_bonus_days = 0
    applied_promo_bonus_days = activation.get("applied_promo_bonus_days", 0) if activation else 0
    displayed_traffic_amount = (
        activation.get("traffic_gb")
        if is_traffic and activation and activation.get("traffic_gb") is not None
        else req.traffic_amount
    )

    inviter_name: str | None = None
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
                else format_human_units(displayed_traffic_amount or req.months)
            ),
            base_end_date=base_end_date,
            final_end_date=final_end_date,
            applied_referee_bonus_days=applied_referee_bonus_days,
            applied_promo_bonus_days=applied_promo_bonus_days,
            inviter_name=inviter_name,
        )
    )
    if is_subscription and activation:
        if activation.get("hwid_devices_renewed_count"):
            success_text = append_hwid_renewed_note(
                success_text,
                translator,
                count=activation.get("hwid_devices_renewed_count"),
                valid_until=final_end_date or activation.get("hwid_devices_renewed_until"),
            )
        else:
            success_text = append_hwid_renewal_note(
                success_text,
                translator,
                count=activation.get("hwid_devices_renewal_recommended_count"),
                valid_until=activation.get("hwid_devices_valid_until"),
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
            except Exception:
                await req.session.rollback()
                logger.exception(
                    "%s: failed to persist install guide share token for user %s.",
                    req.log_prefix,
                    req.user_id,
                )
                install_share_url = None

    if not req.skip_user_notification:
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

    return PaymentSuccessOutcome(
        activation=activation,
        referral_bonus=referral_bonus,
        final_end_date=final_end_date,
        applied_referee_bonus_days=applied_referee_bonus_days,
        applied_promo_bonus_days=applied_promo_bonus_days,
        db_user=db_user,
        language=language,
    )
