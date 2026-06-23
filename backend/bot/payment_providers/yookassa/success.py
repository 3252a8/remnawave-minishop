import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import (
    PaymentCanceledPayload,
    PaymentSucceededPayload,
    ReferralBonusGrantedPayload,
    SubscriptionCreatedPayload,
    SubscriptionExtendedPayload,
)
from bot.infra.payment_events import build_payment_succeeded_payload
from bot.middlewares.i18n import JsonI18n
from bot.services.lknpd_service import LknpdService
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.utils.config_link import prepare_config_links
from bot.utils.install_links import ensure_user_install_guide_links
from config.settings import Settings
from db.dal import payment_dal, user_billing_dal, user_dal

from ..shared import (
    SuccessMessage,
    append_hwid_renewal_note,
    build_success_message,
    format_human_units,
    is_traffic_sale_base,
    make_translator,
    parse_positive_int_units,
    resolve_inviter_name,
    send_success_message_to_user,
)
from ..shared import (
    sale_mode_tariff_key as _sale_mode_tariff_key,
)

payment_processing_lock = asyncio.Lock()

YOOKASSA_EVENT_PAYMENT_SUCCEEDED = "payment.succeeded"
YOOKASSA_EVENT_PAYMENT_CANCELED = "payment.canceled"
YOOKASSA_EVENT_PAYMENT_WAITING_FOR_CAPTURE = "payment.waiting_for_capture"
YOOKASSA_WEBHOOK_ALLOWED_IPS = [
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11",
    "77.75.156.35",
    "77.75.154.128/25",
    "2a02:5180::/32",
]
HWID_DEVICE_SALE_BASES = {"hwid_device", "hwid_devices", "hwid_devices_renewal"}
DEFERRED_EVENTS_KEY = "_deferred_events"
DEFERRED_SUCCESS_MESSAGE_KEY = "_deferred_success_message"


def _is_hwid_device_sale_base(sale_mode_base: str) -> bool:
    return sale_mode_base in HWID_DEVICE_SALE_BASES


async def emit_yookassa_success_events(event_payload: dict) -> None:
    deferred_events = []
    deferred_success_message = None
    if isinstance(event_payload, dict):
        deferred_events = list(event_payload.pop(DEFERRED_EVENTS_KEY, []) or [])
        deferred_success_message = event_payload.pop(DEFERRED_SUCCESS_MESSAGE_KEY, None)
    await events.emit_model(PaymentSucceededPayload.model_validate(event_payload))
    for item in deferred_events:
        if isinstance(item, dict) and item.get("event") and isinstance(item.get("payload"), dict):
            event_name = item["event"]
            payload = item["payload"]
            if event_name == events.SUBSCRIPTION_EXTENDED:
                await events.emit_model(SubscriptionExtendedPayload.model_validate(payload))
            elif event_name == events.SUBSCRIPTION_CREATED:
                await events.emit_model(SubscriptionCreatedPayload.model_validate(payload))
            elif event_name == events.REFERRAL_BONUS_GRANTED:
                await events.emit_model(ReferralBonusGrantedPayload.model_validate(payload))
            else:
                await events.emit(event_name, payload)
    if isinstance(deferred_success_message, dict):
        await send_success_message_to_user(**deferred_success_message)


def _metadata_value_present(value: Optional[Any]) -> bool:
    return value is not None and str(value).strip() != ""


def _metadata_int(value: Optional[Any]) -> Optional[int]:
    if not _metadata_value_present(value):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _metadata_float(value: Optional[Any]) -> Optional[float]:
    if not _metadata_value_present(value):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _metadata_datetime(value: Optional[Any]) -> Optional[datetime]:
    if not _metadata_value_present(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _resolve_yookassa_activation_amounts(
    *,
    sale_mode_base: str,
    subscription_months_raw: Optional[Any],
    traffic_gb_raw: Optional[Any],
    hwid_devices_raw: Optional[Any],
) -> tuple[float, float, int, int, Optional[float]]:
    subscription_months = float(subscription_months_raw or 0)
    traffic_amount_gb = (
        float(traffic_gb_raw or 0)
        if _metadata_value_present(traffic_gb_raw)
        else subscription_months
    )
    hwid_devices_count = 0
    if _metadata_value_present(hwid_devices_raw):
        parsed_hwid_devices = parse_positive_int_units(hwid_devices_raw)
        if parsed_hwid_devices is None:
            raise ValueError("Invalid HWID device count")
        hwid_devices_count = parsed_hwid_devices
    elif _is_hwid_device_sale_base(sale_mode_base):
        parsed_hwid_devices = parse_positive_int_units(subscription_months_raw)
        if parsed_hwid_devices is None:
            raise ValueError("Invalid HWID device count")
        hwid_devices_count = parsed_hwid_devices

    if sale_mode_base == "subscription":
        months_for_activation = int(subscription_months)
    elif _is_hwid_device_sale_base(sale_mode_base):
        months_for_activation = hwid_devices_count
    else:
        months_for_activation = int(traffic_amount_gb)

    traffic_gb_for_activation = traffic_amount_gb if is_traffic_sale_base(sale_mode_base) else None
    return (
        subscription_months,
        traffic_amount_gb,
        hwid_devices_count,
        months_for_activation,
        traffic_gb_for_activation,
    )


async def process_successful_payment(
    session: AsyncSession,
    bot: Bot,
    payment_info_from_webhook: dict[str, Any],
    i18n: JsonI18n,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    referral_service: ReferralService,
    lknpd_service: Optional[LknpdService] = None,
) -> Optional[dict[str, Any]]:
    metadata_raw = payment_info_from_webhook.get("metadata")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    user_id_str = metadata.get("user_id")
    subscription_months_str = metadata.get("subscription_months")
    traffic_gb_str = metadata.get("traffic_gb")
    hwid_devices_str = metadata.get("hwid_devices")
    sale_mode = metadata.get("sale_mode") or (
        "traffic" if settings.traffic_sale_mode else "subscription"
    )
    sale_mode_base = sale_mode.split("@", 1)[0].split("|", 1)[0]
    promo_code_id_str = metadata.get("promo_code_id")
    payment_db_id_str = metadata.get("payment_db_id")
    auto_renew_subscription_id_str = metadata.get("auto_renew_for_subscription_id")

    # For auto-renew payments, payment_db_id may be absent. In that case,
    # we will create/ensure a payment record idempotently using provider payment id.
    if (
        not user_id_str
        or not (
            _metadata_value_present(subscription_months_str)
            or _metadata_value_present(traffic_gb_str)
            or _metadata_value_present(hwid_devices_str)
        )
        or (not payment_db_id_str and not auto_renew_subscription_id_str)
    ):
        logging.error(
            f"Missing crucial metadata for payment: {payment_info_from_webhook.get('id')}, metadata: {metadata}"  # noqa: E501
        )
        return None

    db_user = None
    try:
        user_id = int(user_id_str)
        (
            subscription_months,
            traffic_amount_gb,
            hwid_devices_count,
            months_for_activation,
            traffic_gb_for_activation,
        ) = _resolve_yookassa_activation_amounts(
            sale_mode_base=sale_mode_base,
            subscription_months_raw=subscription_months_str,
            traffic_gb_raw=traffic_gb_str,
            hwid_devices_raw=hwid_devices_str,
        )
        payment_db_id = (
            int(payment_db_id_str) if payment_db_id_str and payment_db_id_str.isdigit() else None
        )
        is_auto_renew = bool(
            auto_renew_subscription_id_str
            and not payment_db_id
            and sale_mode_base == "subscription"
        )
        promo_code_id = (
            int(promo_code_id_str) if promo_code_id_str and promo_code_id_str.isdigit() else None
        )

        amount_data = payment_info_from_webhook.get("amount", {})
        months_for_record = int(subscription_months) if sale_mode_base == "subscription" else 0
        payment_value = float(amount_data.get("value", 0.0))
        yk_payment_id_from_hook = payment_info_from_webhook.get("id")
        hwid_valid_from = _metadata_datetime(metadata.get("hwid_valid_from"))
        hwid_valid_until = _metadata_datetime(metadata.get("hwid_valid_until"))
        hwid_pricing_period_months = _metadata_int(metadata.get("hwid_pricing_period_months"))
        hwid_proration_ratio = _metadata_float(metadata.get("hwid_proration_ratio"))
        hwid_full_price = _metadata_float(metadata.get("hwid_full_price"))
        payment_record = None
        if payment_db_id is not None:
            payment_record = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if not payment_record:
                logging.error(
                    f"Payment record {payment_db_id} not found for YK ID {yk_payment_id_from_hook}."
                )
                return None

        if payment_record and sale_mode_base == "subscription":
            if hwid_devices_count <= 0:
                record_hwid_devices = parse_positive_int_units(
                    getattr(payment_record, "purchased_hwid_devices", None)
                )
                if record_hwid_devices is not None:
                    hwid_devices_count = record_hwid_devices
            if hwid_devices_count > 0:
                if not hwid_valid_from:
                    hwid_valid_from = _metadata_datetime(
                        getattr(payment_record, "hwid_valid_from", None)
                    )
                if not hwid_valid_until:
                    hwid_valid_until = _metadata_datetime(
                        getattr(payment_record, "hwid_valid_until", None)
                    )
                if hwid_pricing_period_months is None:
                    hwid_pricing_period_months = _metadata_int(
                        getattr(payment_record, "hwid_pricing_period_months", None)
                    )
                if hwid_proration_ratio is None:
                    hwid_proration_ratio = _metadata_float(
                        getattr(payment_record, "hwid_proration_ratio", None)
                    )
                if hwid_full_price is None:
                    hwid_full_price = _metadata_float(
                        getattr(payment_record, "hwid_full_price", None)
                    )

        if _is_hwid_device_sale_base(sale_mode_base) and hwid_devices_count <= 0:
            logging.error(
                "YooKassa HWID payment %s has invalid device count in metadata: %s",
                yk_payment_id_from_hook,
                metadata,
            )
            if payment_db_id is not None:
                await payment_dal.update_payment_status_by_db_id(
                    session,
                    payment_db_id,
                    "failed_metadata_error",
                    yk_payment_id_from_hook,
                )
            return None
        if sale_mode_base == "subscription" and hwid_devices_count > 0:
            if (
                not hwid_valid_from
                or not hwid_valid_until
                or hwid_valid_from >= hwid_valid_until
                or hwid_full_price is None
            ):
                logging.error(
                    "YooKassa subscription+HWID payment %s has invalid HWID metadata: %s",
                    yk_payment_id_from_hook,
                    metadata,
                )
                return None

        # If this is an auto-renewal (no payment_db_id in metadata), ensure a payment record exists
        if payment_db_id is None and auto_renew_subscription_id_str:
            try:
                if not yk_payment_id_from_hook:
                    logging.error(
                        "Auto-renew webhook missing YooKassa payment id; cannot ensure payment record."  # noqa: E501
                    )
                    return None
                from db.dal import payment_dal as _payment_dal

                payment_record = await _payment_dal.get_payment_by_provider_payment_id(
                    session, yk_payment_id_from_hook
                )
                if not payment_record:
                    payment_record = await _payment_dal.ensure_payment_with_provider_id(
                        session,
                        user_id=user_id,
                        amount=payment_value,
                        currency=amount_data.get("currency", settings.DEFAULT_CURRENCY_SYMBOL),
                        months=months_for_record or 1,
                        description=payment_info_from_webhook.get("description")
                        or f"Auto-renewal for {months_for_record or subscription_months} months",
                        provider="yookassa",
                        provider_payment_id=yk_payment_id_from_hook,
                        sale_mode=sale_mode,
                        tariff_key=_sale_mode_tariff_key(sale_mode),
                        purchased_hwid_devices=(
                            hwid_devices_count if hwid_devices_count > 0 else None
                        ),
                        hwid_valid_from=hwid_valid_from,
                        hwid_valid_until=hwid_valid_until,
                        hwid_pricing_period_months=hwid_pricing_period_months,
                        hwid_proration_ratio=hwid_proration_ratio,
                        hwid_full_price=hwid_full_price,
                    )
                payment_db_id = payment_record.payment_id
            except Exception as e_ensure:
                logging.error(
                    f"Failed to ensure payment record for auto-renew webhook (YK {payment_info_from_webhook.get('id')}): {e_ensure}",  # noqa: E501
                    exc_info=True,
                )
                return None

        if payment_record and payment_record.status == "succeeded":
            logging.info(
                f"Skipping duplicate YooKassa webhook for payment {payment_db_id} (YK: {yk_payment_id_from_hook})."  # noqa: E501
            )
            return None

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(
                f"User {user_id} not found in DB during successful payment processing for YK ID {payment_info_from_webhook.get('id')}. Payment record {payment_db_id}."  # noqa: E501
            )

            await payment_dal.update_payment_status_by_db_id(
                session, payment_db_id, "failed_user_not_found", payment_info_from_webhook.get("id")
            )

            return None

    except (TypeError, ValueError) as e:
        logging.error(f"Invalid metadata format for payment processing: {metadata} - {e}")

        if payment_db_id_str and payment_db_id_str.isdigit():
            try:
                await payment_dal.update_payment_status_by_db_id(
                    session,
                    int(payment_db_id_str),
                    "failed_metadata_error",
                    payment_info_from_webhook.get("id"),
                )
            except Exception as e_upd:
                logging.error(f"Failed to update payment status after metadata error: {e_upd}")
        return None

    try:
        yk_payment_id_from_hook = payment_info_from_webhook.get("id")
        payment_before_update = None
        if payment_db_id is not None:
            payment_before_update = await payment_dal.get_payment_by_db_id(
                session,
                payment_db_id,
            )
        effective_tariff_key = (
            str(getattr(payment_before_update, "tariff_key", "") or "").strip()
            or str(getattr(payment_record, "tariff_key", "") or "").strip()
            or _sale_mode_tariff_key(sale_mode)
        )
        should_send_lknpd_receipt = bool(
            lknpd_service
            and lknpd_service.configured
            and payment_info_from_webhook.get("paid") is True
            and payment_info_from_webhook.get("status") == "succeeded"
            and payment_before_update
            and payment_before_update.status != "succeeded"
        )
        # Try to capture and save payment method for future charges if available
        try:
            payment_method = payment_info_from_webhook.get("payment_method")
            if (
                settings.yookassa_autopayments_active
                and isinstance(payment_method, dict)
                and payment_method.get("saved", False)
            ):
                pm_id = payment_method.get("id")
                pm_type = payment_method.get("type")
                title = payment_method.get("title")
                card = payment_method.get("card") or {}
                account_number = payment_method.get("account_number") or payment_method.get(
                    "account"
                )
                display_network = None
                display_last4 = None
                # Build generic display for various instrument types
                if (pm_type or "").lower() in {"bank_card", "bank-card", "card"}:
                    display_network = card.get("card_type") or title or "Card"
                    display_last4 = card.get("last4")
                elif (pm_type or "").lower() in {"yoo_money", "yoomoney", "yoo-money", "wallet"}:
                    # Normalize wallet display name to avoid leaking full account from title
                    display_network = "YooMoney"
                    if isinstance(account_number, str) and len(account_number) >= 4:
                        display_last4 = account_number[-4:]
                    else:
                        display_last4 = None
                else:
                    # Wallets, SBP, etc. — use provided title/type; no last4
                    display_network = title or (pm_type.upper() if pm_type else "Payment method")
                    display_last4 = None

                await user_billing_dal.upsert_yk_payment_method(
                    session,
                    user_id=user_id,
                    payment_method_id=pm_id,
                    card_last4=display_last4,
                    card_network=display_network,
                )
                try:
                    await user_billing_dal.upsert_user_payment_method(
                        session,
                        user_id=user_id,
                        provider_payment_method_id=pm_id,
                        provider="yookassa",
                        card_last4=display_last4,
                        card_network=display_network,
                        set_default=True,
                    )
                except Exception:
                    logging.exception("Failed to persist multi-card YooKassa method from webhook")
        except Exception:
            logging.exception("Failed to persist YooKassa payment method from webhook")
        activation_details = await subscription_service.activate_subscription(
            session,
            user_id,
            months_for_activation,
            payment_value,
            payment_db_id,
            promo_code_id_from_payment=promo_code_id,
            provider="yookassa",
            sale_mode=sale_mode,
            traffic_gb=traffic_gb_for_activation,
            tariff_key=effective_tariff_key,
        )

        if not activation_details or (
            sale_mode_base == "subscription" and not activation_details.get("end_date")
        ):
            logging.error(
                f"Failed to activate subscription for user {user_id} after payment {yk_payment_id_from_hook}"  # noqa: E501
            )
            raise Exception(f"Subscription Error: Failed to activate for user {user_id}")

        updated_payment_record = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status=payment_info_from_webhook.get("status", "succeeded"),
            yk_payment_id=yk_payment_id_from_hook,
        )
        if not updated_payment_record:
            logging.error(
                f"Failed to update payment record {payment_db_id} for yk_id {yk_payment_id_from_hook}"  # noqa: E501
            )
            raise Exception(f"DB Error: Could not update payment record {payment_db_id}")

        tariff_key_for_event = (
            str(getattr(updated_payment_record, "tariff_key", "") or "").strip()
            or effective_tariff_key
        )
        payment_succeeded_payload: dict[str, Any] = build_payment_succeeded_payload(
            user_id=user_id,
            payment_db_id=payment_db_id,
            provider="yookassa",
            notification_provider="yookassa",
            amount=payment_value,
            currency=str(amount_data.get("currency") or "RUB"),
            sale_mode=sale_mode,
            tariff_key=tariff_key_for_event,
            months=months_for_activation if sale_mode_base == "subscription" else None,
            traffic_gb=traffic_gb_for_activation,
            purchased_hwid_devices=hwid_devices_count if hwid_devices_count > 0 else None,
            payment=updated_payment_record,
            activation=activation_details,
            end_date=events.iso(activation_details.get("end_date")),
            is_auto_renew=is_auto_renew,
        )
        deferred_events = []
        if sale_mode_base == "subscription":
            deferred_events.append(
                {
                    "event": events.SUBSCRIPTION_EXTENDED
                    if activation_details.get("was_extension")
                    else events.SUBSCRIPTION_CREATED,
                    "payload": (
                        SubscriptionExtendedPayload
                        if activation_details.get("was_extension")
                        else SubscriptionCreatedPayload
                    )(
                        user_id=user_id,
                        subscription_id=activation_details.get("subscription_id"),
                        tariff_key=activation_details.get("tariff_key"),
                        end_date=activation_details.get("end_date"),
                        provider="yookassa",
                        months=months_for_activation,
                        payment_db_id=payment_db_id,
                    ).to_payload(),
                }
            )

        base_subscription_end_date = activation_details.get("end_date")
        final_end_date_for_user = base_subscription_end_date
        applied_promo_bonus_days = activation_details.get("applied_promo_bonus_days", 0)

        referral_bonus_info = None
        if sale_mode_base == "subscription":
            referral_bonus_info = await referral_service.apply_referral_bonuses_for_payment(
                session,
                user_id,
                months_for_activation or int(subscription_months) or 1,
                current_payment_db_id=payment_db_id,
                skip_if_active_before_payment=False,
                tariff_key=effective_tariff_key,
            )
        if isinstance(referral_bonus_info, dict) and referral_bonus_info.get("event_payload"):
            deferred_events.append(
                {
                    "event": events.REFERRAL_BONUS_GRANTED,
                    "payload": ReferralBonusGrantedPayload.model_validate(
                        referral_bonus_info["event_payload"]
                    ).to_payload(),
                }
            )
        if deferred_events:
            payment_succeeded_payload[DEFERRED_EVENTS_KEY] = deferred_events
        applied_referee_bonus_days_from_referral: Optional[int] = None
        if referral_bonus_info and referral_bonus_info.get("referee_new_end_date"):
            final_end_date_for_user = referral_bonus_info["referee_new_end_date"]
            applied_referee_bonus_days_from_referral = referral_bonus_info.get(
                "referee_bonus_applied_days"
            )

        # Use user's DB language for all user-facing messages
        user_lang = (
            db_user.language_code
            if db_user and db_user.language_code
            else settings.DEFAULT_LANGUAGE
        )
        translator = make_translator(i18n, user_lang)
        _ = translator

        traffic_label = format_human_units(traffic_amount_gb)
        if should_send_lknpd_receipt and lknpd_service is not None:
            receipt_item_name = payment_info_from_webhook.get("description")
            if not receipt_item_name:
                if is_traffic_sale_base(sale_mode_base):
                    receipt_item_name = settings.LKNPD_RECEIPT_NAME_TRAFFIC.format(gb=traffic_label)
                elif _is_hwid_device_sale_base(sale_mode_base):
                    receipt_item_name = _(
                        "payment_description_hwid_devices",
                        count=hwid_devices_count,
                    )
                else:
                    receipt_item_name = settings.LKNPD_RECEIPT_NAME_SUBSCRIPTION.format(
                        months=int(subscription_months)
                    )
            try:
                await lknpd_service.create_income_receipt(
                    item_name=receipt_item_name,
                    amount=payment_value,
                    quantity=1.0,
                    operation_time=datetime.now(timezone.utc),
                )
            except Exception:
                logging.exception(
                    "Failed to send LKNPD receipt for payment %s",
                    yk_payment_id_from_hook,
                )
        config_link_display, connect_button_url = await prepare_config_links(
            settings, activation_details.get("subscription_url") if activation_details else None
        )
        # Auto-renew charges show a concise message and skip the connect keyboard, so
        # they bypass the shared success-message builder.
        if sale_mode_base == "subscription" and is_auto_renew and final_end_date_for_user:
            details_message = _(
                "yookassa_auto_renewal",
                months=int(subscription_months),
                end_date=final_end_date_for_user.strftime("%Y-%m-%d"),
            )
            include_keyboard = False
        elif (
            sale_mode_base == "subscription"
            and not final_end_date_for_user
            and not is_traffic_sale_base(sale_mode_base)
        ):
            logging.error(
                f"Critical error: final_end_date_for_user is None for user {user_id} after successful payment logic."  # noqa: E501
            )
            details_message = _("payment_successful_error_details")
            include_keyboard = True
        else:
            inviter_name = None
            if applied_referee_bonus_days_from_referral and final_end_date_for_user:
                inviter_name = await resolve_inviter_name(session, translator, db_user)
            details_message = build_success_message(
                SuccessMessage(
                    translator=translator,
                    sale_mode=sale_mode,
                    months=(
                        traffic_label
                        if is_traffic_sale_base(sale_mode_base)
                        else (
                            hwid_devices_count
                            if _is_hwid_device_sale_base(sale_mode_base)
                            else int(subscription_months)
                        )
                    ),
                    base_end_date=base_subscription_end_date,
                    final_end_date=final_end_date_for_user,
                    applied_referee_bonus_days=applied_referee_bonus_days_from_referral or 0,
                    applied_promo_bonus_days=applied_promo_bonus_days,
                    inviter_name=inviter_name,
                    fallback_date_text="—",
                )
            )
            include_keyboard = True

        if sale_mode_base == "subscription" and activation_details:
            details_message = append_hwid_renewal_note(
                details_message,
                translator,
                count=activation_details.get("hwid_devices_renewal_recommended_count"),
                valid_until=activation_details.get("hwid_devices_valid_until"),
            )

        install_share_url = None
        if include_keyboard:
            install_links = await ensure_user_install_guide_links(session, settings, user_id)
            install_share_url = install_links.public_share_url
        payment_succeeded_payload[DEFERRED_SUCCESS_MESSAGE_KEY] = {
            "bot": bot,
            "user_id": user_id,
            "text": details_message,
            "language": user_lang,
            "i18n": i18n,
            "settings": settings,
            "config_link_display": config_link_display,
            "connect_button_url": connect_button_url,
            "install_share_url": install_share_url,
            "include_keyboard": include_keyboard,
            "log_prefix": "YooKassa webhook",
        }

        return payment_succeeded_payload

    except Exception as e_process:
        logging.error(
            f"Error during process_successful_payment main try block for user {user_id}: {e_process}",  # noqa: E501
            exc_info=True,
        )

        raise


async def process_cancelled_payment(
    session: AsyncSession,
    bot: Bot,
    payment_info_from_webhook: dict[str, Any],
    i18n: JsonI18n,
    settings: Settings,
) -> Optional[dict[str, Any]]:

    metadata_raw = payment_info_from_webhook.get("metadata")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    user_id_str = metadata.get("user_id")
    payment_db_id_str = metadata.get("payment_db_id")

    if not user_id_str or not payment_db_id_str:
        logging.warning(
            f"Missing metadata in cancelled payment webhook: {payment_info_from_webhook.get('id')}"
        )
        return None
    try:
        user_id = int(user_id_str)
        payment_db_id = int(payment_db_id_str)
    except ValueError:
        logging.error(f"Invalid metadata in cancelled payment webhook: {metadata}")
        return None

    try:
        updated_payment = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status=payment_info_from_webhook.get("status", "canceled"),
            yk_payment_id=payment_info_from_webhook.get("id"),
        )

        if updated_payment:
            logging.info(
                f"Payment {payment_db_id} (YK: {payment_info_from_webhook.get('id')}) status updated to cancelled for user {user_id}."  # noqa: E501
            )
            payload: dict[str, Any] = PaymentCanceledPayload(
                user_id=user_id,
                payment_db_id=payment_db_id,
                provider="yookassa",
                provider_payment_id=payment_info_from_webhook.get("id"),
                status=payment_info_from_webhook.get("status", "canceled"),
            ).to_payload(exclude_unset=True)
            return payload
        else:
            logging.warning(
                f"Could not find payment record {payment_db_id} to update status to cancelled for user {user_id}."  # noqa: E501
            )

    except Exception as e_process_cancel:
        logging.error(
            f"Error processing cancelled payment for user {user_id}, payment_db_id {payment_db_id}: {e_process_cancel}",  # noqa: E501
            exc_info=True,
        )
        raise
    return None
