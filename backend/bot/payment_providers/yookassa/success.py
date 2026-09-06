import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import (
    PaymentCanceledPayload,
    ReferralBonusGrantedPayload,
    SubscriptionCreatedPayload,
    SubscriptionExtendedPayload,
)
from bot.infra.payment_events import build_payment_succeeded_payload
from bot.middlewares.i18n import JsonI18n
from bot.services.lknpd_service import LknpdService
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_gifts import is_gift_sale
from bot.utils.config_link import prepare_config_links
from bot.utils.install_links import ensure_user_install_guide_links
from config.settings import Settings
from db.dal import (
    auto_renew_dal,
    gift_dal,
    payment_dal,
    subscription_dal,
    user_billing_dal,
    user_dal,
)

from ..shared import (
    PaymentSuccessRequest,
    SuccessMessage,
    append_hwid_renewal_note,
    build_success_message,
    finalize_successful_payment,
    format_human_units,
    is_traffic_sale_base,
    make_translator,
    parse_positive_int_units,
    payment_units_for_activation,
    payment_uses_entitlement_context,
    preflight_payment_entitlement,
    resolve_referral_bonus_display,
    send_success_message_to_user,
)
from ..shared import (
    sale_mode_tariff_key as _sale_mode_tariff_key,
)
from . import success_helpers as _success_helpers
from .cancellation import cancellation_can_finalize, handle_auto_renew_cancellation
from .legacy_auto_renew import ensure_legacy_auto_renew_payment

DEFERRED_EVENTS_KEY = _success_helpers.DEFERRED_EVENTS_KEY
DEFERRED_SUCCESS_MESSAGE_KEY = _success_helpers.DEFERRED_SUCCESS_MESSAGE_KEY
HWID_DEVICE_SALE_BASES = _success_helpers.HWID_DEVICE_SALE_BASES
_emit_yookassa_success_events = _success_helpers.emit_yookassa_success_events
_is_hwid_device_sale_base = _success_helpers.is_hwid_device_sale_base
_metadata_datetime = _success_helpers.metadata_datetime
_metadata_float = _success_helpers.metadata_float
_metadata_int = _success_helpers.metadata_int
_metadata_value_present = _success_helpers.metadata_value_present
_payment_amount_and_currency_match = _success_helpers.payment_amount_and_currency_are_valid
_resolve_yookassa_activation_amounts = _success_helpers.resolve_yookassa_activation_amounts

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

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


async def emit_yookassa_success_events(event_payload: dict) -> None:
    await _emit_yookassa_success_events(
        event_payload,
        send_success_message=send_success_message_to_user,
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
    lknpd_service: LknpdService | None = None,
) -> dict[str, Any] | None:
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

    # Every successful payment must identify an immutable local order.  The
    # recurring charge flow creates it before calling YooKassa.
    if (
        not user_id_str
        or not (
            _metadata_value_present(subscription_months_str)
            or _metadata_value_present(traffic_gb_str)
            or _metadata_value_present(hwid_devices_str)
        )
        or (not payment_db_id_str and not auto_renew_subscription_id_str)
    ):
        logger.error(
            "Missing crucial metadata for payment: %s, metadata: %s",
            payment_info_from_webhook.get("id"),
            metadata,
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
        promo_code_id = (
            int(promo_code_id_str) if promo_code_id_str and promo_code_id_str.isdigit() else None
        )

        amount_raw = payment_info_from_webhook.get("amount")
        amount_data = amount_raw if isinstance(amount_raw, dict) else {}
        payment_value = float(amount_data.get("value", 0.0))
        payment_currency = str(amount_data.get("currency") or "")
        yk_payment_id_from_hook = payment_info_from_webhook.get("id")
        hwid_valid_from = _metadata_datetime(metadata.get("hwid_valid_from"))
        hwid_valid_until = _metadata_datetime(metadata.get("hwid_valid_until"))
        hwid_pricing_period_months = _metadata_int(metadata.get("hwid_pricing_period_months"))
        hwid_proration_ratio = _metadata_float(metadata.get("hwid_proration_ratio"))
        hwid_full_price = _metadata_float(metadata.get("hwid_full_price"))
        if payment_db_id is None:
            if auto_renew_subscription_id_str:
                legacy_subscription_id = parse_positive_int_units(auto_renew_subscription_id_str)
                if legacy_subscription_id is None:
                    raise ValueError("Invalid legacy auto-renew subscription id")
                legacy_payment = await ensure_legacy_auto_renew_payment(
                    session,
                    provider_payment_id=str(yk_payment_id_from_hook or ""),
                    user_id=user_id,
                    subscription_id=legacy_subscription_id,
                    metadata=metadata,
                    description=str(
                        payment_info_from_webhook.get("description")
                        or "YooKassa subscription renewal"
                    ),
                    subscription_service=subscription_service,
                )
                payment_db_id = int(legacy_payment.payment_id)
                logger.info(
                    "Recovered legacy YooKassa auto-renew payment %s as local order %s.",
                    yk_payment_id_from_hook,
                    payment_db_id,
                )
            else:
                logger.error(
                    "YooKassa payment %s has no local payment record after validation.",
                    yk_payment_id_from_hook,
                )
                return None

        payment_record = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if not payment_record:
            logger.error(
                "Payment record %s not found for YK ID %s.",
                payment_db_id,
                yk_payment_id_from_hook,
            )
            return None
        if getattr(payment_record, "user_id", None) != user_id:
            logger.error(
                "YooKassa payment %s metadata user %s does not own local payment %s.",
                yk_payment_id_from_hook,
                user_id,
                payment_db_id,
            )
            return None

        stored_sale_mode = str(getattr(payment_record, "sale_mode", "") or "").strip()
        if stored_sale_mode:
            # The provider echoes metadata but it must not be allowed to
            # select a different entitlement from the one persisted locally.
            sale_mode = stored_sale_mode
            sale_mode_base = sale_mode.split("@", 1)[0].split("|", 1)[0]
            user_id = int(payment_record.user_id)
            payment_units = payment_units_for_activation(payment_record, sale_mode)
            hwid_devices_count = (
                parse_positive_int_units(getattr(payment_record, "purchased_hwid_devices", None))
                or 0
            )
            hwid_valid_from = _metadata_datetime(getattr(payment_record, "hwid_valid_from", None))
            hwid_valid_until = _metadata_datetime(getattr(payment_record, "hwid_valid_until", None))
            hwid_pricing_period_months = _metadata_int(
                getattr(payment_record, "hwid_pricing_period_months", None)
            )
            hwid_proration_ratio = _metadata_float(
                getattr(payment_record, "hwid_proration_ratio", None)
            )
            hwid_full_price = _metadata_float(getattr(payment_record, "hwid_full_price", None))
            promo_code_id = _metadata_int(getattr(payment_record, "promo_code_id", None))

            if sale_mode_base == "subscription":
                subscription_months = float(payment_units)
                traffic_amount_gb = 0.0
                months_for_activation = int(subscription_months)
                traffic_gb_for_activation = None
            elif _is_hwid_device_sale_base(sale_mode_base):
                subscription_months = 0.0
                traffic_amount_gb = 0.0
                months_for_activation = hwid_devices_count
                traffic_gb_for_activation = None
            else:
                subscription_months = 0.0
                traffic_amount_gb = float(payment_units)
                months_for_activation = int(traffic_amount_gb)
                traffic_gb_for_activation = (
                    traffic_amount_gb if is_traffic_sale_base(sale_mode_base) else None
                )
        else:
            # Pre-schema/in-flight legacy records can lack sale_mode. Keep the
            # old metadata fallback only for those rows, and make it visible.
            logger.warning(
                "YooKassa payment %s has no stored sale_mode; using legacy metadata fallback.",
                payment_db_id,
            )
            if sale_mode_base == "subscription":
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
            if promo_code_id is None:
                promo_code_id = _metadata_int(getattr(payment_record, "promo_code_id", None))

        is_auto_renew = bool(auto_renew_subscription_id_str and sale_mode_base == "subscription")

        if _is_hwid_device_sale_base(sale_mode_base) and hwid_devices_count <= 0:
            logger.error(
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
        if (
            sale_mode_base == "subscription"
            and hwid_devices_count > 0
            and (
                not hwid_valid_from
                or not hwid_valid_until
                or hwid_valid_from >= hwid_valid_until
                or hwid_full_price is None
            )
        ):
            logger.error(
                "YooKassa subscription+HWID payment %s has invalid HWID metadata: %s",
                yk_payment_id_from_hook,
                metadata,
            )
            return None

        amount_matches, mismatch_kind = _payment_amount_and_currency_match(
            payment_record,
            actual_amount=payment_value,
            actual_currency=payment_currency,
        )
        if not amount_matches:
            logger.error(
                "YooKassa payment %s does not match local payment %s "
                "(expected=%s %s, received=%s %s); skipping fulfillment.",
                yk_payment_id_from_hook,
                payment_db_id,
                getattr(payment_record, "amount", None),
                getattr(payment_record, "currency", None),
                payment_value,
                payment_currency or None,
            )
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id,
                f"failed_{mismatch_kind}_mismatch",
                yk_payment_id_from_hook,
            )
            return None
        if sale_mode_base in {"balance_topup", "trial"} or is_gift_sale(sale_mode):
            await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=bot,
                    settings=settings,
                    i18n=i18n,
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=referral_service,
                    payment=payment_record,
                    user_id=user_id,
                    amount=payment_value,
                    currency=payment_currency,
                    sale_mode=sale_mode,
                    months=payment_units,
                    traffic_amount=None,
                    provider_subscription="yookassa",
                    provider_notification="yookassa",
                    log_prefix="YooKassa webhook",
                )
            )
            return None
        payment_record = await payment_dal.claim_payment_finalization(session, payment_db_id)
        if payment_record is None:
            logger.info(
                "Skipping duplicate YooKassa webhook for payment %s (YK: %s).",
                payment_db_id,
                yk_payment_id_from_hook,
            )
            return None

        await user_dal.lock_user_by_id(session, user_id)
        if await gift_dal.activating_for_user(session, user_id) is not None:
            await payment_dal.update_payment_status_by_db_id(
                session, payment_db_id, "activation_failed"
            )
            return None
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logger.error(
                "User %s not found in DB during successful payment processing for YK ID %s. "
                "Payment record %s.",
                user_id,
                payment_info_from_webhook.get("id"),
                payment_db_id,
            )

            await payment_dal.update_payment_status_by_db_id(
                session, payment_db_id, "failed_user_not_found", payment_info_from_webhook.get("id")
            )

            return None

        active_subscription = None
        if payment_uses_entitlement_context(payment_record) or sale_mode_base in {
            "subscription",
            "tariff_upgrade",
        }:
            active_subscription = (
                await subscription_dal.get_active_subscription_by_user_id_for_update(
                    session,
                    user_id,
                )
            )
            if (
                active_subscription is None
                and payment_uses_entitlement_context(payment_record)
                and bool(getattr(payment_record, "is_auto_renew", False))
                and getattr(payment_record, "renewal_subscription_id", None) is not None
            ):
                renewal_subscription = await subscription_dal.get_subscription_by_id_for_update(
                    session,
                    int(payment_record.renewal_subscription_id),
                )
                if (
                    renewal_subscription is not None
                    and int(getattr(renewal_subscription, "user_id", 0) or 0) == user_id
                ):
                    active_subscription = renewal_subscription

        payment_provider = (
            str(getattr(payment_record, "provider", "") or "yookassa").strip().lower()
        )
        # The only payment allowed to land on a live Tribute recurrence is that
        # recurrence's own subscription webhook. A Tribute tariff_upgrade is not
        # it: an upgrade replaces the plan the recurrence was created for and
        # Tribute cannot reprice an existing recurrence, so it is blocked like
        # any other provider's.
        tribute_subscription_event = (
            sale_mode_base == "subscription" and payment_provider == "tribute"
        )
        if (
            sale_mode_base in {"subscription", "tariff_upgrade"}
            and not tribute_subscription_event
            and active_subscription is not None
            and str(getattr(active_subscription, "provider", "") or "").strip().lower() == "tribute"
            and bool(getattr(active_subscription, "auto_renew_enabled", False))
        ):
            logger.error(
                "Rejecting YooKassa payment %s because Tribute recurrence became active "
                "before entitlement mutation.",
                payment_db_id,
            )
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id,
                "activation_failed",
                yk_payment_id_from_hook,
            )
            return None

        if payment_uses_entitlement_context(payment_record):
            entitlement_preflight = preflight_payment_entitlement(
                payment_record,
                active_subscription,
            )
            if not entitlement_preflight.allowed:
                logger.error(
                    "Rejecting YooKassa payment %s before entitlement mutation: %s (%s).",
                    payment_db_id,
                    entitlement_preflight.status,
                    entitlement_preflight.reason,
                )
                await payment_dal.update_payment_status_by_db_id(
                    session,
                    payment_db_id,
                    "activation_failed",
                    yk_payment_id_from_hook,
                )
                return None

    except (TypeError, ValueError) as e:
        logger.error("Invalid metadata format for payment processing: %s - %s", metadata, e)

        if payment_db_id_str and payment_db_id_str.isdigit():
            try:
                await payment_dal.update_payment_status_by_db_id(
                    session,
                    int(payment_db_id_str),
                    "failed_metadata_error",
                    payment_info_from_webhook.get("id"),
                )
            except Exception as e_upd:
                logger.error("Failed to update payment status after metadata error: %s", e_upd)
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
                    logger.exception("Failed to persist multi-card YooKassa method from webhook")
        except Exception:
            logger.exception("Failed to persist YooKassa payment method from webhook")
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
            logger.error(
                "Failed to activate subscription for user %s after payment %s",
                user_id,
                yk_payment_id_from_hook,
            )
            raise Exception(f"Subscription Error: Failed to activate for user {user_id}")

        updated_payment_record = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status=payment_info_from_webhook.get("status", "succeeded"),
            yk_payment_id=yk_payment_id_from_hook,
        )
        if not updated_payment_record:
            logger.error(
                "Failed to update payment record %s for yk_id %s",
                payment_db_id,
                yk_payment_id_from_hook,
            )
            raise Exception(f"DB Error: Could not update payment record {payment_db_id}")
        await auto_renew_dal.mark_cycle_succeeded_for_record(session, updated_payment_record)

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
            currency=payment_currency,
            sale_mode=sale_mode,
            tariff_key=tariff_key_for_event,
            months=months_for_activation if sale_mode_base == "subscription" else None,
            traffic_gb=traffic_gb_for_activation,
            purchased_hwid_devices=hwid_devices_count if hwid_devices_count > 0 else None,
            payment=updated_payment_record,
            activation=activation_details,
            end_date=events.iso(activation_details.get("end_date")),
            is_auto_renew=is_auto_renew,
            renewal_subscription_id=(
                activation_details.get("subscription_id")
                or getattr(updated_payment_record, "renewal_subscription_id", None)
            ),
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
                        duration_days=activation_details.get("duration_days"),
                        payment_db_id=payment_db_id,
                    ).to_payload(),
                }
            )

        base_subscription_end_date = activation_details.get("end_date")
        final_end_date_for_user = base_subscription_end_date
        applied_promo_bonus_days = activation_details.get("applied_promo_bonus_days", 0)

        referral_bonus_info = None
        if sale_mode_base == "subscription":
            try:
                referral_savepoint = await session.begin_nested()
                try:
                    referral_bonus_info = await referral_service.apply_referral_bonuses_for_payment(
                        session,
                        user_id,
                        months_for_activation,
                        current_payment_db_id=payment_db_id,
                        skip_if_active_before_payment=False,
                        tariff_key=effective_tariff_key,
                        duration_days=activation_details.get("duration_days"),
                    )
                except Exception:
                    await referral_savepoint.rollback()
                    raise
                else:
                    await referral_savepoint.commit()
            except Exception:
                referral_bonus_info = None
                logger.exception(
                    "YooKassa: referral bonus failed for payment %s; keeping the paid entitlement.",
                    payment_db_id,
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
        applied_referee_bonus_days_from_referral: int | None = None
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

        granted_traffic_gb = (
            activation_details.get("traffic_gb")
            if activation_details and activation_details.get("traffic_gb") is not None
            else traffic_amount_gb
        )
        traffic_label = format_human_units(granted_traffic_gb)
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
                elif activation_details.get("duration_days"):
                    receipt_item_name = _(
                        "payment_description_subscription_days",
                        days=activation_details["duration_days"],
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
                    operation_time=datetime.now(UTC),
                )
            except Exception:
                logger.exception(
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
                "yookassa_auto_renewal_days"
                if activation_details.get("duration_days")
                else "yookassa_auto_renewal",
                days=activation_details.get("duration_days"),
                months=int(subscription_months),
                end_date=final_end_date_for_user.strftime("%Y-%m-%d"),
            )
            include_keyboard = False
        elif (
            sale_mode_base == "subscription"
            and not final_end_date_for_user
            and not is_traffic_sale_base(sale_mode_base)
        ):
            logger.error(
                "Critical error: final_end_date_for_user is None for user %s after successful "
                "payment logic.",
                user_id,
            )
            details_message = _("payment_successful_error_details")
            include_keyboard = True
        else:
            inviter_name, referee_bonus_source = await resolve_referral_bonus_display(
                session, translator, db_user, referral_bonus_info
            )
            details_message = build_success_message(
                SuccessMessage(
                    translator=translator,
                    duration_days=activation_details.get("duration_days"),
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
                    referee_bonus_source=referee_bonus_source,
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
            "user": db_user,
            "sale_mode": sale_mode,
        }

        return payment_succeeded_payload

    except Exception as e_process:
        logger.exception(
            "Error during process_successful_payment main try block for user %s: %s",
            user_id,
            e_process,
        )

        raise


async def process_cancelled_payment(
    session: AsyncSession,
    bot: Bot,
    payment_info_from_webhook: dict[str, Any],
    i18n: JsonI18n,
    settings: Settings,
) -> dict[str, Any] | None:
    metadata_raw = payment_info_from_webhook.get("metadata")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    user_id_str = metadata.get("user_id")
    payment_db_id_str = metadata.get("payment_db_id")

    if not user_id_str or not payment_db_id_str:
        logger.warning(
            "Missing metadata in cancelled payment webhook: %s", payment_info_from_webhook.get("id")
        )
        return None
    try:
        user_id = int(user_id_str)
        payment_db_id = int(payment_db_id_str)
    except ValueError:
        logger.error("Invalid metadata in cancelled payment webhook: %s", metadata)
        return None

    try:
        cancellation_raw = payment_info_from_webhook.get("cancellation_details")
        cancellation = cancellation_raw if isinstance(cancellation_raw, dict) else {}
        cancellation_party = str(cancellation.get("party") or "").strip().lower() or None
        cancellation_reason = str(cancellation.get("reason") or "").strip().lower() or None
        updated_payment = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status=payment_info_from_webhook.get("status", "canceled"),
            yk_payment_id=payment_info_from_webhook.get("id"),
        )

        if updated_payment:
            if not cancellation_can_finalize(updated_payment, payment_db_id, logger):
                return None
            await auto_renew_dal.record_provider_cancellation(
                session,
                payment_id=payment_db_id,
                party=cancellation_party,
                reason=cancellation_reason,
            )
            decision = await handle_auto_renew_cancellation(
                session,
                payment=updated_payment,
                user_id=user_id,
                cancellation_party=cancellation_party,
                cancellation_reason=cancellation_reason,
                settings=settings,
            )
            cycle_id = decision.cycle_id
            retry_at = decision.retry_at
            logger.info(
                "Payment %s (YK: %s) status updated to cancelled for user %s.",
                payment_db_id,
                payment_info_from_webhook.get("id"),
                user_id,
            )
            payload: dict[str, Any] = PaymentCanceledPayload(
                user_id=user_id,
                payment_db_id=payment_db_id,
                provider="yookassa",
                provider_payment_id=payment_info_from_webhook.get("id"),
                status=payment_info_from_webhook.get("status", "canceled"),
                cancellation_party=cancellation_party,
                cancellation_reason=cancellation_reason,
                auto_renew_cycle_id=cycle_id,
                auto_renew_retry_scheduled=retry_at is not None,
                retry_at=retry_at,
                message_key=("autorenew_retry_scheduled" if retry_at is not None else None),
            ).to_payload(exclude_unset=True)
            return payload
        logger.warning(
            "Could not find payment record %s to update status to cancelled for user %s.",
            payment_db_id,
            user_id,
        )

    except Exception as e_process_cancel:
        logger.exception(
            "Error processing cancelled payment for user %s, payment_db_id %s: %s",
            user_id,
            payment_db_id,
            e_process_cancel,
        )
        raise
    return None
