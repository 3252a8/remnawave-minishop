import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from yookassa import Configuration
from yookassa import Payment as YooKassaPayment
from yookassa.domain.common.confirmation_type import ConfirmationType
from yookassa.domain.notification import WebhookNotification
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder

from bot.infra.webhook_queue import enqueue_webhook_event
from bot.keyboards.inline.user_keyboards import (
    get_back_to_main_menu_markup,
    get_bind_url_keyboard,
    get_payment_method_delete_confirm_keyboard,
    get_payment_method_details_keyboard,
    get_payment_methods_list_keyboard,
    get_payment_url_keyboard,
    get_yk_autopay_choice_keyboard,
    get_yk_saved_cards_keyboard,
    payment_methods_back_callback,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.lknpd_service import LknpdService
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.utils.config_link import prepare_config_links
from bot.utils.install_links import ensure_user_install_guide_links
from bot.utils.request_security import ip_in_allowlist, request_client_ip
from config.settings import Settings
from db.dal import payment_dal, user_billing_dal, user_dal
from db.models import Payment

from .base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    provider_env_file,
    provider_runtime_enabled,
)
from .shared import (
    PaymentCallbackParts,
    SuccessMessage,
    append_hwid_renewal_note,
    build_success_message,
    create_webapp_payment_record,
    format_human_units,
    format_number_for_payload,
    is_traffic_sale_base,
    make_translator,
    mark_payment_failed_creation,
    notify_admins_payment_received,
    payment_failed,
    payment_link_response,
    payment_record_amounts,
    payment_unavailable,
    quote_hwid_callback_parts,
    resolve_inviter_name,
    send_success_message_to_user,
)
from .shared import (
    sale_mode_base as _sale_mode_base,
)


class YooKassaConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="YOOKASSA_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=True)
    SHOP_ID: Optional[str] = None
    SECRET_KEY: Optional[str] = None
    RETURN_URL: Optional[str] = None
    DEFAULT_RECEIPT_EMAIL: Optional[str] = None
    VAT_CODE: int = Field(default=1)
    PAYMENT_MODE: str = Field(default="full_prepayment")
    PAYMENT_SUBJECT: str = Field(default="service")
    AUTOPAYMENTS_ENABLED: bool = Field(default=False)
    AUTOPAYMENTS_REQUIRE_CARD_BINDING: bool = Field(default=True)

    @field_validator("SHOP_ID", "SECRET_KEY", "RETURN_URL", "DEFAULT_RECEIPT_EMAIL", mode="before")
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def autopayments_active(self) -> bool:
        return bool(self.ENABLED and self.AUTOPAYMENTS_ENABLED)

    @property
    def yk_receipt_payment_mode(self) -> str:
        return "service" if self.AUTOPAYMENTS_ENABLED else "full_prepayment"

    @property
    def yk_receipt_payment_subject(self) -> str:
        return "full_payment" if self.AUTOPAYMENTS_ENABLED else "payment"

    @property
    def webhook_path(self) -> str:
        return "/webhook/yookassa"


class YooKassaPresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_YOOKASSA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class YooKassaService:
    def __init__(
        self,
        shop_id: Optional[str],
        secret_key: Optional[str],
        configured_return_url: Optional[str],
        bot_username_for_default_return: Optional[str] = None,
        settings_obj: Optional[Settings] = None,
        config: Optional[YooKassaConfig] = None,
        subscription_service: Optional[SubscriptionService] = None,
    ):

        self.settings = settings_obj
        self.config = config or YooKassaConfig()
        self.subscription_service = subscription_service
        self._bot_username_for_default_return = bot_username_for_default_return
        self._configured_return_url_override = configured_return_url
        self._sdk_configured_for = (
            None  # (shop_id, secret_key) currently loaded into the global SDK
        )

        if not self.configured:
            if not provider_runtime_enabled(self.config):
                logging.warning(
                    "YooKassa is disabled via YOOKASSA_ENABLED flag. Payment functionality will be DISABLED."  # noqa: E501
                )
            else:
                logging.warning(
                    "YooKassa SHOP_ID or SECRET_KEY not configured in settings. "
                    "Payment functionality will be DISABLED."
                )
        logging.info("YooKassa Service effective return_url for payments: %s", self.return_url)

    @property
    def configured(self) -> bool:
        if not (
            provider_runtime_enabled(self.config) and self.config.SHOP_ID and self.config.SECRET_KEY
        ):
            return False
        self._ensure_sdk_configured()
        return self._sdk_configured_for is not None

    def _ensure_sdk_configured(self) -> None:
        """Reconfigure the global YooKassa SDK if shop_id/secret_key changed at runtime."""
        shop_id = self.config.SHOP_ID
        secret_key = self.config.SECRET_KEY
        if not shop_id or not secret_key:
            self._sdk_configured_for = None
            return
        if self._sdk_configured_for == (shop_id, secret_key):
            return
        try:
            Configuration.configure(shop_id, secret_key)
            self._sdk_configured_for = (shop_id, secret_key)
            logging.info("YooKassa SDK (re)configured for shop_id: %s...", shop_id[:5])
        except Exception:
            logging.exception("Failed to configure YooKassa SDK.")
            self._sdk_configured_for = None

    @property
    def return_url(self) -> str:
        url = self._configured_return_url_override or self.config.RETURN_URL
        if url:
            return url
        if self._bot_username_for_default_return:
            return f"https://t.me/{self._bot_username_for_default_return}"
        return "https://example.com/payment_error_no_return_url_configured"

    async def create_payment(
        self,
        amount: float,
        currency: str,
        description: str,
        metadata: Dict[str, Any],
        receipt_email: Optional[str] = None,
        receipt_phone: Optional[str] = None,
        save_payment_method: bool = False,
        payment_method_id: Optional[str] = None,
        capture: bool = True,
        bind_only: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not self.configured:
            logging.error("YooKassa is not configured. Cannot create payment.")
            return None

        if not self.settings:
            logging.error(
                "YooKassaService: Settings object not available. Cannot create payment with receipt details."  # noqa: E501
            )
            return {
                "error": True,
                "internal_message": "Service settings (Settings object) not initialized.",
            }

        customer_contact_for_receipt = {}
        if receipt_email:
            customer_contact_for_receipt["email"] = receipt_email
        elif receipt_phone:
            customer_contact_for_receipt["phone"] = receipt_phone
        elif self.config.DEFAULT_RECEIPT_EMAIL:
            customer_contact_for_receipt["email"] = self.config.DEFAULT_RECEIPT_EMAIL
        else:
            logging.error(
                "CRITICAL: No email/phone for YooKassa receipt provided and YOOKASSA_DEFAULT_RECEIPT_EMAIL is not set."  # noqa: E501
            )
            return {
                "error": True,
                "internal_message": "YooKassa receipt customer contact (email/phone) missing and no default email configured.",  # noqa: E501
            }

        try:
            builder = PaymentRequestBuilder()
            builder.set_amount({"value": str(round(amount, 2)), "currency": currency.upper()})
            # For binding cards only, do not capture and set minimal amount
            if bind_only:
                capture = False
                amount = max(amount, 1.00)
            builder.set_capture(capture)
            if not payment_method_id:
                # Saved payment_method_id charges must omit confirmation per YooKassa API
                builder.set_confirmation(
                    {"type": ConfirmationType.REDIRECT, "return_url": self.return_url}
                )
            builder.set_description(description)
            builder.set_metadata(metadata)
            if save_payment_method:
                # Ask YooKassa to save method for off-session charges
                builder.set_save_payment_method(True)
            elif not payment_method_id:
                # Keep the Smart Payment form unrestricted for one-off payments.
                builder.set_save_payment_method(False)
            if payment_method_id:
                # Use a previously saved payment method for merchant-initiated payments
                builder.set_payment_method_id(payment_method_id)

            receipt_items_list: List[Dict[str, Any]] = [
                {
                    "description": description[:128],
                    "quantity": "1.00",
                    "amount": {"value": str(round(amount, 2)), "currency": currency.upper()},
                    "vat_code": str(self.config.VAT_CODE),
                    "payment_mode": self.config.yk_receipt_payment_mode,
                    "payment_subject": self.config.yk_receipt_payment_subject,
                }
            ]

            receipt_data_dict: Dict[str, Any] = {
                "customer": customer_contact_for_receipt,
                "items": receipt_items_list,
            }

            builder.set_receipt(receipt_data_dict)

            idempotence_key = str(uuid.uuid4())
            payment_request = builder.build()

            logging.info(
                f"Creating YooKassa payment (Idempotence-Key: {idempotence_key}). "
                f"Amount: {amount} {currency}. Metadata: {metadata}. Receipt: {receipt_data_dict}"
            )

            response = await asyncio.to_thread(
                YooKassaPayment.create,
                payment_request,
                idempotence_key,
            )

            logging.info(
                f"YooKassa Payment.create response: ID={response.id}, Status={response.status}, Paid={response.paid}"  # noqa: E501
            )

            return {
                "id": response.id,
                "confirmation_url": response.confirmation.confirmation_url
                if response.confirmation
                else None,
                "status": response.status,
                "metadata": response.metadata,
                "amount_value": float(response.amount.value),
                "amount_currency": response.amount.currency,
                "idempotence_key_used": idempotence_key,
                "paid": response.paid,
                "refundable": response.refundable,
                "created_at": response.created_at.isoformat()
                if hasattr(response.created_at, "isoformat")
                else str(response.created_at),
                "description_from_yk": response.description,
                "test_mode": response.test if hasattr(response, "test") else None,
                "payment_method": getattr(response, "payment_method", None),
            }
        except Exception:
            logging.exception("YooKassa payment creation failed.")
            return None

    async def get_payment_info(self, payment_id_in_yookassa: str) -> Optional[Dict[str, Any]]:
        if not self.configured:
            logging.error("YooKassa is not configured. Cannot get payment info.")
            return None
        try:
            logging.info(f"Fetching payment info from YooKassa for ID: {payment_id_in_yookassa}")

            payment_info_yk = await asyncio.to_thread(
                YooKassaPayment.find_one,
                payment_id_in_yookassa,
            )

            if payment_info_yk:
                logging.info(
                    f"YooKassa payment info for {payment_id_in_yookassa}: Status={payment_info_yk.status}, Paid={payment_info_yk.paid}"  # noqa: E501
                )
                pm = getattr(payment_info_yk, "payment_method", None)
                pm_payload: Dict[str, Any] = {}
                if pm:
                    # Collect common fields, including id and hints for last4
                    pm_id = getattr(pm, "id", None)
                    pm_type = getattr(pm, "type", None)
                    pm_title = getattr(pm, "title", None)
                    account_number = getattr(pm, "account_number", None) or getattr(
                        pm, "account", None
                    )
                    card_obj = getattr(pm, "card", None)
                    last4_val = None
                    if card_obj and hasattr(card_obj, "last4"):
                        last4_val = getattr(card_obj, "last4")
                    elif isinstance(account_number, str) and len(account_number) >= 4:
                        last4_val = account_number[-4:]
                    pm_payload = {
                        "id": pm_id,
                        "type": pm_type,
                        "title": pm_title,
                        "card_last4": last4_val,
                    }
                return {
                    "id": payment_info_yk.id,
                    "status": payment_info_yk.status,
                    "paid": payment_info_yk.paid,
                    "amount_value": float(payment_info_yk.amount.value),
                    "amount_currency": payment_info_yk.amount.currency,
                    "metadata": payment_info_yk.metadata,
                    "description": payment_info_yk.description,
                    "refundable": payment_info_yk.refundable,
                    "created_at": payment_info_yk.created_at.isoformat()
                    if hasattr(payment_info_yk.created_at, "isoformat")
                    else str(payment_info_yk.created_at),
                    "captured_at": payment_info_yk.captured_at.isoformat()
                    if getattr(payment_info_yk, "captured_at", None)
                    and hasattr(payment_info_yk.captured_at, "isoformat")
                    else None,
                    "payment_method": pm_payload,
                    "test_mode": getattr(payment_info_yk, "test", None),
                }
            else:
                logging.warning(
                    f"No payment info found in YooKassa for ID: {payment_id_in_yookassa}"
                )
                return None
        except Exception:
            logging.exception("YooKassa get payment info for %s failed.", payment_id_in_yookassa)
            return None

    async def cancel_payment(self, payment_id_in_yookassa: str) -> bool:
        if not self.configured:
            logging.error("YooKassa is not configured. Cannot cancel payment.")
            return False
        try:
            await asyncio.to_thread(YooKassaPayment.cancel, payment_id_in_yookassa)
            logging.info(f"Cancelled YooKassa payment {payment_id_in_yookassa}")
            return True
        except Exception:
            logging.exception("Failed to cancel YooKassa payment %s.", payment_id_in_yookassa)
            return False


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


def _is_hwid_device_sale_base(sale_mode_base: str) -> bool:
    return sale_mode_base in HWID_DEVICE_SALE_BASES


def _metadata_value_present(value: Optional[Any]) -> bool:
    return value is not None and str(value).strip() != ""


def _resolve_yookassa_activation_amounts(
    *,
    sale_mode_base: str,
    subscription_months_raw: Optional[Any],
    traffic_gb_raw: Optional[Any],
    hwid_devices_raw: Optional[Any],
) -> tuple[float, float, int, int, Optional[float]]:
    subscription_months = float(subscription_months_raw or 0)
    traffic_amount_gb = (
        float(traffic_gb_raw) if _metadata_value_present(traffic_gb_raw) else subscription_months
    )
    hwid_devices_count = (
        int(float(hwid_devices_raw))
        if _metadata_value_present(hwid_devices_raw)
        else (int(subscription_months) if _is_hwid_device_sale_base(sale_mode_base) else 0)
    )

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
    payment_info_from_webhook: dict,
    i18n: JsonI18n,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    referral_service: ReferralService,
    lknpd_service: Optional[LknpdService] = None,
):
    metadata = payment_info_from_webhook.get("metadata", {})
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
        return

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
            return

        payment_record = None
        # If this is an auto-renewal (no payment_db_id in metadata), ensure a payment record exists
        if payment_db_id is None and auto_renew_subscription_id_str:
            try:
                if not yk_payment_id_from_hook:
                    logging.error(
                        "Auto-renew webhook missing YooKassa payment id; cannot ensure payment record."  # noqa: E501
                    )
                    return
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
                    )
                payment_db_id = payment_record.payment_id
            except Exception as e_ensure:
                logging.error(
                    f"Failed to ensure payment record for auto-renew webhook (YK {payment_info_from_webhook.get('id')}): {e_ensure}",  # noqa: E501
                    exc_info=True,
                )
                return
        elif payment_db_id is not None:
            payment_record = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if not payment_record:
                logging.error(
                    f"Payment record {payment_db_id} not found for YK ID {yk_payment_id_from_hook}."
                )
                return

        if payment_record and payment_record.status == "succeeded":
            logging.info(
                f"Skipping duplicate YooKassa webhook for payment {payment_db_id} (YK: {yk_payment_id_from_hook})."  # noqa: E501
            )
            return

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(
                f"User {user_id} not found in DB during successful payment processing for YK ID {payment_info_from_webhook.get('id')}. Payment record {payment_db_id}."  # noqa: E501
            )

            await payment_dal.update_payment_status_by_db_id(
                session, payment_db_id, "failed_user_not_found", payment_info_from_webhook.get("id")
            )

            return

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
        return

    try:
        yk_payment_id_from_hook = payment_info_from_webhook.get("id")
        payment_before_update = None
        if payment_db_id is not None:
            payment_before_update = await payment_dal.get_payment_by_db_id(
                session,
                payment_db_id,
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
            )
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
        if should_send_lknpd_receipt:
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
        await send_success_message_to_user(
            bot=bot,
            user_id=user_id,
            text=details_message,
            language=user_lang,
            i18n=i18n,
            settings=settings,
            config_link_display=config_link_display,
            connect_button_url=connect_button_url,
            install_share_url=install_share_url,
            include_keyboard=include_keyboard,
            log_prefix="YooKassa webhook",
        )

        tariff_for_log = None
        for source in (payment_before_update, updated_payment_record, payment_record):
            if source is not None and getattr(source, "tariff_key", None):
                tariff_for_log = source.tariff_key
                break
        user_for_notify = db_user or await user_dal.get_user_by_id(session, user_id)
        await notify_admins_payment_received(
            bot=bot,
            settings=settings,
            i18n=i18n,
            user_id=user_id,
            amount=payment_value,
            currency=settings.DEFAULT_CURRENCY_SYMBOL,
            months_for_admin=int(subscription_months) if sale_mode_base == "subscription" else 0,
            traffic_gb_for_admin=(
                traffic_amount_gb if is_traffic_sale_base(sale_mode_base) else None
            ),
            payment_provider="yookassa",
            username=user_for_notify.username if user_for_notify else None,
            email=getattr(user_for_notify, "email", None) if user_for_notify else None,
            traffic_is_premium=sale_mode_base == "premium_topup",
            tariff_key=tariff_for_log,
            log_prefix="YooKassa webhook",
        )

    except Exception as e_process:
        logging.error(
            f"Error during process_successful_payment main try block for user {user_id}: {e_process}",  # noqa: E501
            exc_info=True,
        )

        raise


async def process_cancelled_payment(
    session: AsyncSession,
    bot: Bot,
    payment_info_from_webhook: dict,
    i18n: JsonI18n,
    settings: Settings,
):

    metadata = payment_info_from_webhook.get("metadata", {})
    user_id_str = metadata.get("user_id")
    payment_db_id_str = metadata.get("payment_db_id")

    if not user_id_str or not payment_db_id_str:
        logging.warning(
            f"Missing metadata in cancelled payment webhook: {payment_info_from_webhook.get('id')}"
        )
        return
    try:
        user_id = int(user_id_str)
        payment_db_id = int(payment_db_id_str)
    except ValueError:
        logging.error(f"Invalid metadata in cancelled payment webhook: {metadata}")
        return

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
        else:
            logging.warning(
                f"Could not find payment record {payment_db_id} to update status to cancelled for user {user_id}."  # noqa: E501
            )

        db_user = await user_dal.get_user_by_id(session, user_id)
        user_lang = settings.DEFAULT_LANGUAGE
        if db_user and db_user.language_code:
            user_lang = db_user.language_code

        _ = lambda key, **kwargs: i18n.gettext(user_lang, key, **kwargs)
        await bot.send_message(user_id, _("payment_failed"))

    except Exception as e_process_cancel:
        logging.error(
            f"Error processing cancelled payment for user {user_id}, payment_db_id {payment_db_id}: {e_process_cancel}",  # noqa: E501
            exc_info=True,
        )
        raise


async def yookassa_webhook_route(request: web.Request):

    try:
        bot: Bot = request.app["bot"]
        i18n_instance: JsonI18n = request.app["i18n"]
        settings: Settings = request.app["settings"]
        panel_service: PanelApiService = request.app["panel_service"]
        subscription_service: SubscriptionService = request.app["subscription_service"]
        referral_service: ReferralService = request.app["referral_service"]
        lknpd_service: Optional[LknpdService] = request.app.get("lknpd_service")
        async_session_factory: sessionmaker = request.app["async_session_factory"]
    except KeyError:
        logging.exception("KeyError accessing app context in yookassa_webhook_route.")
        return web.Response(status=500, text="Internal Server Error: Missing app context component")

    client_ip = request_client_ip(request, trusted_proxies=settings.trusted_proxies)
    if not ip_in_allowlist(client_ip, YOOKASSA_WEBHOOK_ALLOWED_IPS):
        logging.warning(
            "YooKassa webhook denied from unauthorized IP source "
            "(client_ip=%s remote=%s x_forwarded_for=%s trusted_ips=%s trusted_proxies=%s).",
            client_ip,
            request.remote,
            request.headers.get("X-Forwarded-For"),
            YOOKASSA_WEBHOOK_ALLOWED_IPS,
            settings.trusted_proxies,
        )
        return web.Response(status=403)

    try:
        event_json = await request.json()

        notification_object = WebhookNotification(event_json)
        payment_data_from_notification = notification_object.object

        logging.info(
            f"YooKassa Webhook Parsed: Event='{notification_object.event}', "
            f"PaymentId='{payment_data_from_notification.id}', Status='{payment_data_from_notification.status}'"  # noqa: E501
        )

        if (
            not payment_data_from_notification
            or not hasattr(payment_data_from_notification, "metadata")
            or payment_data_from_notification.metadata is None
        ):
            logging.error(
                f"YooKassa webhook payment {payment_data_from_notification.id} lacks metadata. Cannot process."  # noqa: E501
            )
            return web.Response(status=200, text="ok_error_no_metadata")

        # Safely extract payment_method details (SDK objects may not have to_dict)
        pm_obj = getattr(payment_data_from_notification, "payment_method", None)
        pm_dict = None
        if pm_obj is not None:
            try:
                card_obj = getattr(pm_obj, "card", None)
                pm_dict = {
                    "id": getattr(pm_obj, "id", None),
                    "type": getattr(pm_obj, "type", None),
                    "saved": bool(getattr(pm_obj, "saved", False)),
                    "title": getattr(pm_obj, "title", None),
                    "account_number": (
                        getattr(pm_obj, "account_number", None)
                        if hasattr(pm_obj, "account_number")
                        else (
                            getattr(pm_obj, "account", None) if hasattr(pm_obj, "account") else None
                        )
                    ),
                    "card": (
                        {
                            "first6": getattr(card_obj, "first6", None),
                            "last4": getattr(card_obj, "last4", None),
                            "expiry_month": getattr(card_obj, "expiry_month", None),
                            "expiry_year": getattr(card_obj, "expiry_year", None),
                            "card_type": getattr(card_obj, "card_type", None),
                        }
                        if card_obj is not None
                        else None
                    ),
                }
            except Exception:
                logging.exception("Failed to serialize YooKassa payment_method from webhook")
                pm_dict = None

        payment_dict_for_processing = {
            "id": str(payment_data_from_notification.id),
            "status": str(payment_data_from_notification.status),
            "paid": bool(payment_data_from_notification.paid),
            "amount": {
                "value": str(payment_data_from_notification.amount.value),
                "currency": str(payment_data_from_notification.amount.currency),
            }
            if payment_data_from_notification.amount
            else {},
            "metadata": dict(payment_data_from_notification.metadata),
            "description": str(payment_data_from_notification.description)
            if payment_data_from_notification.description
            else None,
            "payment_method": pm_dict,
        }

        if notification_object.event in {
            YOOKASSA_EVENT_PAYMENT_SUCCEEDED,
            YOOKASSA_EVENT_PAYMENT_CANCELED,
        }:
            queued = await enqueue_webhook_event(
                settings,
                "yookassa",
                {
                    "event": notification_object.event,
                    "payment": payment_dict_for_processing,
                },
                event_id=f"{notification_object.event}:{payment_dict_for_processing.get('id')}",
            )
            if queued:
                return web.Response(status=200, text="queued")

        async with payment_processing_lock:
            async with async_session_factory() as session:
                try:
                    if notification_object.event == YOOKASSA_EVENT_PAYMENT_SUCCEEDED:
                        if (
                            payment_dict_for_processing.get("paid")
                            and payment_dict_for_processing.get("status") == "succeeded"
                        ):
                            await process_successful_payment(
                                session,
                                bot,
                                payment_dict_for_processing,
                                i18n_instance,
                                settings,
                                panel_service,
                                subscription_service,
                                referral_service,
                                lknpd_service,
                            )
                            await session.commit()
                        else:
                            logging.warning(
                                f"Payment Succeeded event for {payment_dict_for_processing.get('id')} "  # noqa: E501
                                f"but data not as expected: status='{payment_dict_for_processing.get('status')}', "  # noqa: E501
                                f"paid='{payment_dict_for_processing.get('paid')}'"
                            )
                    elif notification_object.event == YOOKASSA_EVENT_PAYMENT_CANCELED:
                        await process_cancelled_payment(
                            session, bot, payment_dict_for_processing, i18n_instance, settings
                        )
                        await session.commit()
                    elif notification_object.event == YOOKASSA_EVENT_PAYMENT_WAITING_FOR_CAPTURE:
                        # Bind-only flow: save method and cancel auth if metadata has bind_only
                        metadata = payment_dict_for_processing.get("metadata", {}) or {}
                        if (
                            settings.yookassa_autopayments_active
                            and metadata.get("bind_only") == "1"
                        ):
                            try:
                                user_id_str = metadata.get("user_id")
                                if user_id_str and user_id_str.isdigit():
                                    user_id = int(user_id_str)
                                    payment_method = payment_dict_for_processing.get(
                                        "payment_method"
                                    )
                                    if isinstance(payment_method, dict) and payment_method.get(
                                        "id"
                                    ):
                                        pm_type = payment_method.get("type")
                                        title = payment_method.get("title")
                                        card = payment_method.get("card") or {}
                                        account_number = payment_method.get(
                                            "account_number"
                                        ) or payment_method.get("account")
                                        display_network = None
                                        display_last4 = None
                                        if (pm_type or "").lower() in {
                                            "bank_card",
                                            "bank-card",
                                            "card",
                                        }:
                                            display_network = (
                                                card.get("card_type") or title or "Card"
                                            )
                                            display_last4 = card.get("last4")
                                        elif (pm_type or "").lower() in {
                                            "yoo_money",
                                            "yoomoney",
                                            "yoo-money",
                                            "wallet",
                                        }:
                                            # Normalize wallet display name to avoid leaking full account from title  # noqa: E501
                                            display_network = "YooMoney"
                                            if (
                                                isinstance(account_number, str)
                                                and len(account_number) >= 4
                                            ):
                                                display_last4 = account_number[-4:]
                                            else:
                                                display_last4 = None
                                        else:
                                            display_network = title or (
                                                pm_type.upper() if pm_type else "Payment method"
                                            )
                                            display_last4 = None
                                        await user_billing_dal.upsert_yk_payment_method(
                                            session,
                                            user_id=user_id,
                                            payment_method_id=payment_method.get("id"),
                                            card_last4=display_last4,
                                            card_network=display_network,
                                        )
                                        await session.commit()
                                        # Save multi-card entry and mark default if first
                                        try:
                                            from db.dal import user_billing_dal as ub

                                            await ub.upsert_user_payment_method(
                                                session,
                                                user_id=user_id,
                                                provider_payment_method_id=payment_method.get("id"),
                                                provider="yookassa",
                                                card_last4=display_last4,
                                                card_network=display_network,
                                                set_default=True,
                                            )
                                            await session.commit()
                                        except Exception:
                                            await session.rollback()
                                        # Notify user about successful binding with Back button
                                        try:
                                            # Use user's DB language for bind success notification
                                            i18n_lang = settings.DEFAULT_LANGUAGE
                                            from db.dal import user_dal

                                            db_user = await user_dal.get_user_by_id(
                                                session, user_id
                                            )
                                            if db_user and db_user.language_code:
                                                i18n_lang = db_user.language_code
                                            _ = lambda key, **kwargs: i18n_instance.gettext(
                                                i18n_lang, key, **kwargs
                                            )
                                            from bot.keyboards.inline.user_keyboards import (
                                                get_back_to_payment_methods_keyboard,
                                            )

                                            await bot.send_message(
                                                chat_id=user_id,
                                                text=_("payment_method_bound_success"),
                                                reply_markup=get_back_to_payment_methods_keyboard(
                                                    i18n_lang, i18n_instance
                                                ),
                                            )
                                        except Exception:
                                            pass
                                        # Attempt to cancel the authorization to avoid charge hold
                                        try:
                                            yk: YooKassaService = request.app.get(
                                                "yookassa_service"
                                            )
                                            if yk:
                                                await yk.cancel_payment(
                                                    payment_dict_for_processing.get("id")
                                                )
                                        except Exception:
                                            logging.exception(
                                                "Failed to cancel bind-only payment auth"
                                            )
                            except Exception:
                                logging.exception(
                                    "Failed to handle bind-only waiting_for_capture webhook"
                                )
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Error processing YooKassa webhook event '%s' for YK Payment ID %s in DB transaction.",  # noqa: E501
                        notification_object.event,
                        payment_dict_for_processing.get("id"),
                    )
                    return web.Response(status=500, text="internal_processing_error")

        return web.Response(status=200, text="ok")

    except json.JSONDecodeError:
        logging.error("YooKassa Webhook: Invalid JSON received.")
        return web.Response(status=400, text="bad_request_invalid_json")
    except Exception:
        logging.exception("YooKassa Webhook general processing error.")
        return web.Response(status=500, text="internal_error")


router = Router(name="user_subscription_payments_yookassa_router")


def _format_value(val: float) -> str:
    return str(int(val)) if float(val).is_integer() else f"{val:g}"


def _parse_offer_payload(payload: str) -> Optional[Tuple[float, float, str]]:
    try:
        parts = payload.split(":")
        value = float(parts[0])
        price = float(parts[1])
        sale_mode = parts[2] if len(parts) > 2 else "subscription"
        return value, price, sale_mode
    except (ValueError, IndexError):
        return None


def _format_saved_payment_method_title(
    get_text, network: Optional[str], last4: Optional[str], is_default: bool
) -> str:
    def _is_yoomoney_network(name: Optional[str]) -> bool:
        s = (name or "").lower()
        return "yoomoney" in s or "yoo money" in s or "yoo-money" in s

    def _extract_last4(text: str) -> Optional[str]:
        digits = "".join(ch for ch in text if ch.isdigit())
        return digits[-4:] if len(digits) >= 4 else None

    if _is_yoomoney_network(network):
        inferred_last4 = last4 or (_extract_last4(network or "") or "****")
        title = get_text("payment_method_wallet_title", last4=inferred_last4)
    elif last4:
        network_name = network or get_text("payment_network_card")
        title = get_text("payment_method_card_title", network=network_name, last4=last4)
    else:
        network_name = network or get_text("payment_network_generic")
        title = get_text("payment_method_generic_title", network=network_name)
    return f"⭐ {title}" if is_default else title


async def _initiate_yk_payment(
    callback: types.CallbackQuery,
    *,
    settings: Settings,
    session: AsyncSession,
    yookassa_service: YooKassaService,
    i18n: Optional[JsonI18n],
    current_lang: str,
    get_text,
    user_id: int,
    months: int,
    price_rub: float,
    currency_code_for_yk: str,
    save_payment_method: bool,
    back_callback: str,
    payment_method_id: Optional[str] = None,
    selected_method_internal_id: Optional[int] = None,
    sale_mode: str = "subscription",
    hwid_quote: Optional[dict] = None,
) -> bool:
    """Create payment record and initiate YooKassa payment (new card or saved card)."""
    if not callback.message:
        return False

    sale_base = _sale_mode_base(sale_mode)
    payment_description = (
        get_text("payment_description_traffic", traffic_gb=_format_value(months))
        if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
        else (
            get_text("payment_description_hwid_devices", count=int(months))
            if sale_base in HWID_DEVICE_SALE_BASES
            else get_text("payment_description_subscription", months=int(months))
        )
    )
    payment_record_data = {
        "user_id": user_id,
        "amount": price_rub,
        "currency": currency_code_for_yk,
        "status": "pending_yookassa",
        "description": payment_description,
        "subscription_duration_months": int(months) if sale_base == "subscription" else None,
        "sale_mode": sale_base,
        "tariff_key": sale_mode.split("@", 1)[1].split("|", 1)[0] if "@" in sale_mode else None,
        "purchased_gb": float(months)
        if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
        else None,
        "purchased_hwid_devices": int(months) if sale_base in HWID_DEVICE_SALE_BASES else None,
        "hwid_valid_from": hwid_quote.get("valid_from") if hwid_quote else None,
        "hwid_valid_until": hwid_quote.get("valid_until") if hwid_quote else None,
        "hwid_pricing_period_months": hwid_quote.get("pricing_period_months")
        if hwid_quote
        else None,
        "hwid_proration_ratio": hwid_quote.get("proration_ratio") if hwid_quote else None,
        "hwid_full_price": hwid_quote.get("full_price") if hwid_quote else None,
    }

    db_payment_record = None
    try:
        db_payment_record = await payment_dal.create_payment_record(session, payment_record_data)
        await session.commit()
        logging.info(
            f"Payment record {db_payment_record.payment_id} created for user {user_id} with status 'pending_yookassa'."  # noqa: E501
        )
    except Exception as e_db_payment:
        await session.rollback()
        logging.error(
            f"Failed to create payment record in DB for user {user_id}: {e_db_payment}",
            exc_info=True,
        )
        try:
            await callback.message.edit_text(get_text("error_creating_payment_record"))
        except Exception:
            pass
        return False

    if not db_payment_record:
        try:
            await callback.message.edit_text(get_text("error_creating_payment_record"))
        except Exception:
            pass
        return False

    yookassa_metadata = {
        "user_id": str(user_id),
        "subscription_months": str(months),
        "payment_db_id": str(db_payment_record.payment_id),
        "sale_mode": sale_mode,
    }
    if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}:
        yookassa_metadata["traffic_gb"] = str(months)
    if sale_base in HWID_DEVICE_SALE_BASES:
        yookassa_metadata["hwid_devices"] = str(months)
    if payment_method_id:
        yookassa_metadata["used_saved_payment_method_id"] = payment_method_id

    receipt_email_for_yk = yookassa_service.config.DEFAULT_RECEIPT_EMAIL

    payment_response_yk = await yookassa_service.create_payment(
        amount=price_rub,
        currency=currency_code_for_yk,
        description=payment_description,
        metadata=yookassa_metadata,
        receipt_email=receipt_email_for_yk,
        save_payment_method=save_payment_method,
        payment_method_id=payment_method_id,
    )

    if payment_response_yk and payment_response_yk.get("confirmation_url"):
        pm = payment_response_yk.get("payment_method")
        try:
            if pm and pm.get("id"):
                pm_type = pm.get("type")
                title = pm.get("title")
                card = pm.get("card") or {}
                account_number = pm.get("account_number") or pm.get("account")
                if isinstance(card, dict) and (pm_type or "").lower() in {
                    "bank_card",
                    "bank-card",
                    "card",
                }:
                    display_network = card.get("card_type") or title or "Card"
                    display_last4 = card.get("last4")
                elif (pm_type or "").lower() in {"yoo_money", "yoomoney", "yoo-money", "wallet"}:
                    display_network = "YooMoney"
                    display_last4 = (
                        account_number[-4:]
                        if isinstance(account_number, str) and len(account_number) >= 4
                        else None
                    )
                else:
                    display_network = title or (pm_type.upper() if pm_type else "Payment method")
                    display_last4 = None
                await user_billing_dal.upsert_yk_payment_method(
                    session,
                    user_id=user_id,
                    payment_method_id=pm["id"],
                    card_last4=display_last4,
                    card_network=display_network,
                )
                try:
                    await user_billing_dal.upsert_user_payment_method(
                        session,
                        user_id=user_id,
                        provider_payment_method_id=pm["id"],
                        provider="yookassa",
                        card_last4=display_last4,
                        card_network=display_network,
                        set_default=save_payment_method,
                    )
                except Exception:
                    pass
                await session.commit()
        except Exception:
            await session.rollback()
            logging.exception("Failed to save YooKassa payment method preliminarily")
        try:
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id=db_payment_record.payment_id,
                new_status=payment_response_yk.get("status", "pending"),
                yk_payment_id=payment_response_yk.get("id"),
            )
            if selected_method_internal_id is not None:
                try:
                    await user_billing_dal.set_user_default_payment_method(
                        session, user_id, selected_method_internal_id
                    )
                except Exception:
                    logging.exception(
                        "Failed to set default payment method after initiating payment"
                    )
            await session.commit()
        except Exception as e_db_update_ykid:
            await session.rollback()
            logging.error(
                f"Failed to update payment record {db_payment_record.payment_id} with YK ID: {e_db_update_ykid}",  # noqa: E501
                exc_info=True,
            )
            try:
                await callback.message.edit_text(get_text("error_payment_gateway_link_failed"))
            except Exception:
                pass
            return False

        try:
            await callback.message.edit_text(
                get_text(
                    key="payment_link_message_traffic"
                    if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
                    else "payment_link_message",
                    months=int(months),
                    traffic_gb=_format_value(months),
                ),
                reply_markup=get_payment_url_keyboard(
                    payment_response_yk["confirmation_url"],
                    current_lang,
                    i18n,
                    back_callback=back_callback,
                    back_text_key="back_to_payment_methods_button",
                ),
                disable_web_page_preview=False,
            )
        except Exception as e_edit:
            logging.warning(f"Edit message for payment link failed: {e_edit}. Sending new one.")
            try:
                await callback.message.answer(
                    get_text(
                        key="payment_link_message_traffic"
                        if sale_base in {"traffic", "traffic_package", "topup", "premium_topup"}
                        else "payment_link_message",
                        months=int(months),
                        traffic_gb=_format_value(months),
                    ),
                    reply_markup=get_payment_url_keyboard(
                        payment_response_yk["confirmation_url"],
                        current_lang,
                        i18n,
                        back_callback=back_callback,
                        back_text_key="back_to_payment_methods_button",
                    ),
                    disable_web_page_preview=False,
                )
            except Exception:
                pass
        return True

    if payment_response_yk and payment_method_id:
        status_to_store = payment_response_yk.get("status", "pending")
        try:
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id=db_payment_record.payment_id,
                new_status=status_to_store,
                yk_payment_id=payment_response_yk.get("id"),
            )
            if selected_method_internal_id is not None:
                try:
                    await user_billing_dal.set_user_default_payment_method(
                        session, user_id, selected_method_internal_id
                    )
                except Exception:
                    logging.exception(
                        "Failed to set default payment method after saved-card payment start"
                    )
            await session.commit()
        except Exception as e_db_update_saved:
            await session.rollback()
            logging.error(
                f"Failed to update saved-card payment record {db_payment_record.payment_id}: {e_db_update_saved}",  # noqa: E501
                exc_info=True,
            )
            try:
                await callback.message.edit_text(get_text("error_payment_gateway"))
            except Exception:
                pass
            return False

        message_text = get_text("yookassa_autopay_charge_initiated")
        try:
            await callback.message.edit_text(
                message_text,
                reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
            )
        except Exception as e_edit:
            logging.warning(f"Failed to notify about saved-card charge start: {e_edit}")
            try:
                await callback.message.answer(
                    message_text,
                    reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
                )
            except Exception:
                pass
        return True

    try:
        await payment_dal.update_payment_status_by_db_id(
            session, db_payment_record.payment_id, "failed_creation"
        )
        await session.commit()
    except Exception as e_db_fail_create:
        await session.rollback()
        logging.error(
            f"Additionally failed to update payment record to 'failed_creation': {e_db_fail_create}",  # noqa: E501
            exc_info=True,
        )
    logging.error(
        f"Failed to create payment in YooKassa for user {user_id}, payment_db_id {db_payment_record.payment_id}. Response: {payment_response_yk}"  # noqa: E501
    )
    try:
        await callback.message.edit_text(get_text("error_payment_gateway"))
    except Exception:
        pass
    return False


async def _yookassa_available_to_callback_user(
    callback: types.CallbackQuery,
    settings: Settings,
    get_text,
) -> bool:
    if SPEC.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        return True
    try:
        await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
    except Exception:
        pass
    if callback.message:
        try:
            await callback.message.edit_text(get_text("payment_service_unavailable"))
        except Exception:
            pass
    return False


@router.callback_query(F.data.startswith("pay_yk:"))
async def pay_yk_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    yookassa_service: YooKassaService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n or not callback.message:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logging.error("YooKassa service is not configured or unavailable.")
        target_msg_edit = callback.message
        await target_msg_edit.edit_text(get_text("payment_service_unavailable"))
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        return

    try:
        _, data_payload = callback.data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk data in callback: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parsed = _parse_offer_payload(data_payload)
    if not parsed:
        logging.error(f"Invalid pay_yk payload structure: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    months, price_rub, sale_mode = parsed
    hwid_quote = None
    if _sale_mode_base(sale_mode) in HWID_DEVICE_SALE_BASES:
        quoted_parts, hwid_quote = await quote_hwid_callback_parts(
            session=session,
            user_id=callback.from_user.id,
            parts=PaymentCallbackParts(months=months, price=price_rub, sale_mode=sale_mode),
            subscription_service=yookassa_service.subscription_service,
            currency="rub",
        )
        if not quoted_parts:
            try:
                await callback.answer(get_text("error_try_again"), show_alert=True)
            except Exception:
                pass
            return
        months = quoted_parts.months
        price_rub = quoted_parts.price
    user_id = callback.from_user.id
    currency_code_for_yk = "RUB"
    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    autopay_require_binding = bool(
        getattr(settings, "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING", True)
    )
    saved_methods: List = []
    if autopay_enabled:
        try:
            saved_methods = await user_billing_dal.list_user_payment_methods(
                session, user_id, provider="yookassa"
            )
        except Exception as e_list:
            logging.exception(f"Failed to load saved payment methods for user {user_id}: {e_list}")
            saved_methods = []

    if autopay_enabled and saved_methods:
        try:
            await callback.message.edit_text(
                get_text("yookassa_autopay_flow_prompt"),
                reply_markup=get_yk_autopay_choice_keyboard(
                    months,
                    price_rub,
                    current_lang,
                    i18n,
                    has_saved_cards=True,
                    sale_mode=sale_mode,
                    back_callback=payment_methods_back_callback(
                        _format_value(months), sale_mode, price_rub
                    ),
                ),
            )
        except Exception as e_edit:
            logging.warning(f"Failed to show autopay choice: {e_edit}. Sending new message.")
            try:
                await callback.message.answer(
                    get_text("yookassa_autopay_flow_prompt"),
                    reply_markup=get_yk_autopay_choice_keyboard(
                        months,
                        price_rub,
                        current_lang,
                        i18n,
                        has_saved_cards=True,
                        sale_mode=sale_mode,
                        back_callback=payment_methods_back_callback(
                            _format_value(months), sale_mode, price_rub
                        ),
                    ),
                )
            except Exception:
                pass
        try:
            await callback.answer()
        except Exception:
            pass
        return

    await _initiate_yk_payment(
        callback,
        settings=settings,
        session=session,
        yookassa_service=yookassa_service,
        i18n=i18n,
        current_lang=current_lang,
        get_text=get_text,
        user_id=user_id,
        months=months,
        price_rub=price_rub,
        currency_code_for_yk=currency_code_for_yk,
        save_payment_method=autopay_enabled and autopay_require_binding,
        back_callback=payment_methods_back_callback(_format_value(months), sale_mode, price_rub),
        sale_mode=sale_mode,
        hwid_quote=hwid_quote,
    )
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_yk_new:"))
async def pay_yk_new_card_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    yookassa_service: YooKassaService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n or not callback.message:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logging.error("YooKassa service unavailable for pay_yk_new.")
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        try:
            await callback.message.edit_text(get_text("payment_service_unavailable"))
        except Exception:
            pass
        return

    try:
        _, data_payload = callback.data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk_new data in callback: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parsed = _parse_offer_payload(data_payload)
    if not parsed:
        logging.error(f"Invalid pay_yk_new payload structure: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    months, price_rub, sale_mode = parsed
    user_id = callback.from_user.id
    currency_code_for_yk = "RUB"
    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    autopay_require_binding = bool(
        getattr(settings, "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING", True)
    )

    await _initiate_yk_payment(
        callback,
        settings=settings,
        session=session,
        yookassa_service=yookassa_service,
        i18n=i18n,
        current_lang=current_lang,
        get_text=get_text,
        user_id=user_id,
        months=months,
        price_rub=price_rub,
        currency_code_for_yk=currency_code_for_yk,
        save_payment_method=autopay_enabled and autopay_require_binding,
        back_callback=payment_methods_back_callback(_format_value(months), sale_mode, price_rub),
        sale_mode=sale_mode,
    )
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_yk_saved_list:"))
async def pay_yk_saved_list_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    yookassa_service: YooKassaService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n or not callback.message:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    try:
        _, data_payload = callback.data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk_saved_list data: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parts = data_payload.split(":")
    if len(parts) < 2:
        logging.error(f"pay_yk_saved_list payload missing components: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    try:
        months = float(parts[0])
        price_rub = float(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
        sale_mode = parts[3] if len(parts) > 3 else "subscription"
    except (ValueError, IndexError):
        logging.error(f"pay_yk_saved_list payload parsing error: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    if not autopay_enabled:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    user_id = callback.from_user.id
    try:
        saved_methods = await user_billing_dal.list_user_payment_methods(
            session, user_id, provider="yookassa"
        )
    except Exception as e_list:
        logging.exception(f"Failed to list saved payment methods for user {user_id}: {e_list}")
        saved_methods = []

    if not saved_methods:
        try:
            await callback.message.edit_text(
                get_text("yookassa_autopay_no_saved_cards"),
                reply_markup=get_yk_autopay_choice_keyboard(
                    months,
                    price_rub,
                    current_lang,
                    i18n,
                    has_saved_cards=False,
                    sale_mode=sale_mode,
                    back_callback=payment_methods_back_callback(
                        _format_value(months), sale_mode, price_rub
                    ),
                ),
            )
        except Exception as e_edit:
            logging.warning(f"Failed to display no-saved-card notice: {e_edit}")
            try:
                await callback.message.answer(
                    get_text("yookassa_autopay_no_saved_cards"),
                    reply_markup=get_yk_autopay_choice_keyboard(
                        months,
                        price_rub,
                        current_lang,
                        i18n,
                        has_saved_cards=False,
                        sale_mode=sale_mode,
                        back_callback=payment_methods_back_callback(
                            _format_value(months), sale_mode, price_rub
                        ),
                    ),
                )
            except Exception:
                pass
        try:
            await callback.answer()
        except Exception:
            pass
        return

    cards: List[Tuple[str, str]] = []
    for method in saved_methods:
        title = _format_saved_payment_method_title(
            get_text, method.card_network, method.card_last4, method.is_default
        )
        cards.append((str(method.method_id), title))

    per_page = 5
    max_page = max(0, (len(cards) - 1) // per_page)
    page = max(0, min(page, max_page))

    try:
        await callback.message.edit_text(
            get_text("yookassa_autopay_choose_saved_card"),
            reply_markup=get_yk_saved_cards_keyboard(
                cards,
                months,
                price_rub,
                current_lang,
                i18n,
                page=page,
                sale_mode=sale_mode,
            ),
        )
    except Exception as e_edit:
        logging.warning(f"Failed to display saved card list: {e_edit}")
        try:
            await callback.message.answer(
                get_text("yookassa_autopay_choose_saved_card"),
                reply_markup=get_yk_saved_cards_keyboard(
                    cards,
                    months,
                    price_rub,
                    current_lang,
                    i18n,
                    page=page,
                    sale_mode=sale_mode,
                ),
            )
        except Exception:
            pass
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_yk_use_saved:"))
async def pay_yk_use_saved_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    yookassa_service: YooKassaService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n or not callback.message:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not await _yookassa_available_to_callback_user(callback, settings, get_text):
        return

    if not yookassa_service or not yookassa_service.configured:
        logging.error("YooKassa service unavailable for pay_yk_use_saved.")
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        try:
            await callback.message.edit_text(get_text("payment_service_unavailable"))
        except Exception:
            pass
        return

    try:
        _, data_payload = callback.data.split(":", 1)
    except ValueError:
        logging.error(f"Invalid pay_yk_use_saved data: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    parts = data_payload.split(":")
    if len(parts) < 3:
        logging.error(f"pay_yk_use_saved payload missing components: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    try:
        months = float(parts[0])
        price_rub = float(parts[1])
        sale_mode = parts[3] if len(parts) > 3 else "subscription"
    except (ValueError, IndexError):
        logging.error(f"pay_yk_use_saved months/price parsing error: {callback.data}")
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    autopay_enabled = bool(
        settings.yookassa_autopayments_active
        and _sale_mode_base(sale_mode) == "subscription"
        and not settings.traffic_sale_mode
    )
    if not autopay_enabled:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    method_identifier = parts[2]
    user_id = callback.from_user.id

    try:
        saved_methods = await user_billing_dal.list_user_payment_methods(
            session, user_id, provider="yookassa"
        )
    except Exception as e_list:
        logging.exception(f"Failed to list saved payment methods for user {user_id}: {e_list}")
        saved_methods = []

    selected_method = None
    for method in saved_methods:
        if method_identifier.isdigit():
            if method.method_id == int(method_identifier):
                selected_method = method
                break
        if method.provider_payment_method_id == method_identifier:
            selected_method = method
            break

    if not selected_method:
        logging.warning(
            f"Selected payment method not found for user {user_id}: {method_identifier}"
        )
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    currency_code_for_yk = "RUB"

    await _initiate_yk_payment(
        callback,
        settings=settings,
        session=session,
        yookassa_service=yookassa_service,
        i18n=i18n,
        current_lang=current_lang,
        get_text=get_text,
        user_id=user_id,
        months=months,
        price_rub=price_rub,
        currency_code_for_yk=currency_code_for_yk,
        save_payment_method=False,
        back_callback=f"pay_yk_saved_list:{_format_value(months)}:{price_rub}:{sale_mode}",
        payment_method_id=selected_method.provider_payment_method_id,
        selected_method_internal_id=selected_method.method_id,
        sale_mode=sale_mode,
    )
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data == "pm:manage")
async def payment_methods_manage(
    callback: types.CallbackQuery, settings: Settings, i18n_data: dict, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not settings.yookassa_autopayments_active:
        try:
            _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
            await callback.answer(_("error_service_unavailable"), show_alert=True)
        except Exception:
            pass
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    from db.dal.user_billing_dal import list_user_payment_methods

    get_text = _
    methods = await list_user_payment_methods(session, callback.from_user.id)
    cards: List[tuple] = []

    def _is_yoomoney_network(network: Optional[str]) -> bool:
        s = (network or "").lower()
        return "yoomoney" in s or "yoo money" in s or "yoo-money" in s

    def _extract_last4(text: str) -> Optional[str]:
        digits = "".join(ch for ch in text if ch.isdigit())
        return digits[-4:] if len(digits) >= 4 else None

    def _format_pm_title(network: Optional[str], last4: Optional[str]) -> str:
        if _is_yoomoney_network(network):
            l4 = last4 or _extract_last4(network or "")
            if l4:
                return get_text("payment_method_wallet_title", last4=l4)
            return get_text("payment_method_wallet_title", last4="****")
        if last4:
            network_name = network or get_text("payment_network_card")
            return get_text("payment_method_card_title", network=network_name, last4=last4)
        network_name = network or get_text("payment_network_generic")
        return get_text("payment_method_generic_title", network=network_name)

    for m in methods:
        title = _format_pm_title(m.card_network, m.card_last4)
        cards.append((str(m.method_id), title if not m.is_default else f"⭐ {title}"))

    text = get_text("payment_methods_title")
    if not cards:
        text += "\n\n" + get_text("payment_method_none")

    await callback.message.edit_text(
        text, reply_markup=get_payment_methods_list_keyboard(cards, 0, current_lang, i18n)
    )
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data == "pm:bind")
async def payment_method_bind(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    yookassa_service: YooKassaService,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not settings.yookassa_autopayments_active:
        try:
            _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
            await callback.answer(_("error_service_unavailable"), show_alert=True)
        except Exception:
            pass
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    metadata = {"user_id": str(callback.from_user.id), "bind_only": "1"}
    resp = await yookassa_service.create_payment(
        amount=1.00,
        currency="RUB",
        description="Bind card",
        metadata=metadata,
        receipt_email=yookassa_service.config.DEFAULT_RECEIPT_EMAIL,
        save_payment_method=True,
        capture=False,
        bind_only=True,
    )
    if not resp or not resp.get("confirmation_url"):
        await callback.answer(_("error_payment_gateway"), show_alert=True)
        return
    await callback.message.edit_text(
        _("payment_methods_title"),
        reply_markup=get_bind_url_keyboard(resp["confirmation_url"], current_lang, i18n),
    )
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pm:delete_confirm"))
async def payment_method_delete_confirm(
    callback: types.CallbackQuery, settings: Settings, i18n_data: dict
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not settings.yookassa_autopayments_active:
        try:
            _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
            await callback.answer(_("error_service_unavailable"), show_alert=True)
        except Exception:
            pass
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
    parts = callback.data.split(":", 2)
    pm_id = parts[2] if len(parts) >= 3 else ""
    await callback.message.edit_text(
        _("payment_method_delete_confirm"),
        reply_markup=get_payment_method_delete_confirm_keyboard(pm_id, current_lang, i18n),
    )
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pm:delete"))
async def payment_method_delete(
    callback: types.CallbackQuery, settings: Settings, i18n_data: dict, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not settings.yookassa_autopayments_active:
        try:
            _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
            await callback.answer(_("error_service_unavailable"), show_alert=True)
        except Exception:
            pass
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
    parts = callback.data.split(":", 2)
    pm_id_raw = parts[2] if len(parts) >= 3 else ""
    deleted = False

    try:
        from db.dal.user_billing_dal import (
            delete_user_payment_method,
            delete_user_payment_method_by_provider_id,
            list_user_payment_methods,
        )

        if pm_id_raw:
            if pm_id_raw.isdigit():
                deleted = await delete_user_payment_method(
                    session, callback.from_user.id, int(pm_id_raw)
                )
            else:
                deleted = await delete_user_payment_method_by_provider_id(
                    session, callback.from_user.id, pm_id_raw
                )
        try:
            legacy_deleted = await user_billing_dal.delete_yk_payment_method(
                session, callback.from_user.id
            )
            deleted = deleted or legacy_deleted
        except Exception:
            pass
        await session.commit()

        methods = await list_user_payment_methods(session, callback.from_user.id)
        text = _("payment_methods_title")
        cards = []
        for m in methods:

            def _is_yoomoney_network(network: Optional[str]) -> bool:
                s = (network or "").lower()
                return "yoomoney" in s or "yoo money" in s or "yoo-money" in s

            def _extract_last4(text: str) -> Optional[str]:
                digits = "".join(ch for ch in text if ch.isdigit())
                return digits[-4:] if len(digits) >= 4 else None

            def _format_pm_title(network: Optional[str], last4: Optional[str]) -> str:
                if _is_yoomoney_network(network):
                    l4 = last4 or _extract_last4(network or "")
                    if l4:
                        return _("payment_method_wallet_title", last4=l4)
                    return _("payment_method_wallet_title", last4="****")
                if last4:
                    network_name = network or _("payment_network_card")
                    return _("payment_method_card_title", network=network_name, last4=last4)
                network_name = network or _("payment_network_generic")
                return _("payment_method_generic_title", network=network_name)

            title = _format_pm_title(m.card_network, m.card_last4)
            cards.append((str(m.method_id), title if not m.is_default else f"⭐ {title}"))
        if not cards:
            text += "\n\n" + _("payment_method_none")
        msg = _("payment_method_deleted_success") if deleted else _("error_try_again")
        await callback.message.edit_text(
            f"{msg}\n\n{text}",
            reply_markup=get_payment_methods_list_keyboard(cards, 0, current_lang, i18n),
        )
        try:
            await callback.answer()
        except Exception:
            pass
        return
    except Exception:
        await session.rollback()
        try:
            await callback.answer(_("error_try_again"), show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("pm:view"))
async def payment_method_view(
    callback: types.CallbackQuery, settings: Settings, i18n_data: dict, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not settings.yookassa_autopayments_active:
        try:
            _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
            await callback.answer(_("error_service_unavailable"), show_alert=True)
        except Exception:
            pass
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    billing = await user_billing_dal.get_user_billing(session, callback.from_user.id)
    if not billing or not billing.yookassa_payment_method_id:
        from db.dal.user_billing_dal import list_user_payment_methods

        methods = await list_user_payment_methods(session, callback.from_user.id)
        if not methods:
            await callback.answer(_("payment_method_none"), show_alert=True)
            return
        parts = callback.data.split(":", 2)
        pm_id = parts[2] if len(parts) >= 3 else str(methods[0].method_id)
        sel = next(
            (
                m
                for m in methods
                if str(m.method_id) == pm_id or m.provider_payment_method_id == pm_id
            ),
            methods[0],
        )

        def _is_yoomoney_network(network: Optional[str]) -> bool:
            s = (network or "").lower()
            return "yoomoney" in s or "yoo money" in s or "yoo-money" in s

        def _extract_last4(text: str) -> Optional[str]:
            digits = "".join(ch for ch in text if ch.isdigit())
            return digits[-4:] if len(digits) >= 4 else None

        def _format_pm_title(network: Optional[str], last4: Optional[str]) -> str:
            if _is_yoomoney_network(network):
                l4 = last4 or _extract_last4(network or "")
                if l4:
                    return _("payment_method_wallet_title", last4=l4)
                return _("payment_method_wallet_title", last4="****")
            if last4:
                network_name = network or _("payment_network_card")
                return _("payment_method_card_title", network=network_name, last4=last4)
            network_name = network or _("payment_network_generic")
            return _("payment_method_generic_title", network=network_name)

        title = _format_pm_title(sel.card_network, sel.card_last4)
        added_at = sel.created_at.strftime("%Y-%m-%d") if getattr(sel, "created_at", None) else "—"
        last_tx = "—"
        try:
            stmt = (
                select(Payment)
                .where(
                    Payment.user_id == callback.from_user.id,
                    Payment.status == "succeeded",
                    Payment.provider == "yookassa",
                )
                .order_by(Payment.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            lp = result.scalar_one_or_none()
            if lp and lp.created_at:
                last_tx = lp.created_at.strftime("%Y-%m-%d")
        except Exception:
            pass
        details = f"{title}\n{_('payment_method_added_at', date=added_at)}\n{_('payment_method_last_tx', date=last_tx)}"  # noqa: E501
        await callback.message.edit_text(
            details,
            reply_markup=get_payment_method_details_keyboard(
                str(sel.method_id), current_lang, i18n
            ),
        )
        try:
            await callback.answer()
        except Exception:
            pass
        return

    added_at = (
        billing.created_at.strftime("%Y-%m-%d") if getattr(billing, "created_at", None) else "—"
    )
    last_tx = "—"
    try:
        stmt = (
            select(Payment)
            .where(
                Payment.user_id == callback.from_user.id,
                Payment.status == "succeeded",
                Payment.provider == "yookassa",
            )
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        last_payment = result.scalar_one_or_none()
        if last_payment and last_payment.created_at:
            last_tx = last_payment.created_at.strftime("%Y-%m-%d")
    except Exception:
        pass

    def _is_yoomoney_network(network: Optional[str]) -> bool:
        s = (network or "").lower()
        return "yoomoney" in s or "yoo money" in s or "yoo-money" in s

    def _extract_last4(text: str) -> Optional[str]:
        digits = "".join(ch for ch in text if ch.isdigit())
        return digits[-4:] if len(digits) >= 4 else None

    def _format_pm_title(network: Optional[str], last4: Optional[str]) -> str:
        if _is_yoomoney_network(network):
            l4 = last4 or _extract_last4(network or "")
            if l4:
                return _("payment_method_wallet_title", last4=l4)
            return _("payment_method_wallet_title", last4="****")
        if last4:
            network_name = network or _("payment_network_card")
            return _("payment_method_card_title", network=network_name, last4=last4)
        network_name = network or _("payment_network_generic")
        return _("payment_method_generic_title", network=network_name)

    title = _format_pm_title(billing.card_network, billing.card_last4)
    details = f"{title}\n{_('payment_method_added_at', date=added_at)}\n{_('payment_method_last_tx', date=last_tx)}"  # noqa: E501
    await callback.message.edit_text(
        details,
        reply_markup=get_payment_method_details_keyboard(
            billing.yookassa_payment_method_id, current_lang, i18n
        ),
    )
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pm:history"))
async def payment_method_history(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    yookassa_service: YooKassaService,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not settings.yookassa_autopayments_active:
        try:
            _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key
            await callback.answer(_("error_service_unavailable"), show_alert=True)
        except Exception:
            pass
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    from db.dal import payment_dal

    payments = await payment_dal.get_recent_payment_logs_with_user(session, limit=30, offset=0)
    user_payments = [p for p in payments if p.user_id == callback.from_user.id]

    selected_pm_provider_id: Optional[str] = None
    pm_filter_requested: bool = False
    try:
        split_a, split_b, split_pm_id = callback.data.split(":", 2)
        if split_pm_id:
            pm_filter_requested = True
            if split_pm_id.isdigit():
                from db.dal.user_billing_dal import list_user_payment_methods

                methods = await list_user_payment_methods(session, callback.from_user.id)
                sel = next((m for m in methods if str(m.method_id) == split_pm_id), None)
                if sel and sel.provider_payment_method_id:
                    selected_pm_provider_id = sel.provider_payment_method_id
            else:
                selected_pm_provider_id = split_pm_id
    except Exception:
        selected_pm_provider_id = None
        pm_filter_requested = False

    if pm_filter_requested and not selected_pm_provider_id:
        user_payments = []

    if selected_pm_provider_id:
        filtered: List[Payment] = []
        for p in user_payments:
            if p.provider != "yookassa":
                continue
            if p.yookassa_payment_id and yookassa_service:
                try:
                    info = await yookassa_service.get_payment_info(p.yookassa_payment_id)
                    pm = (info or {}).get("payment_method") or {}
                    if pm.get("id") == selected_pm_provider_id:
                        filtered.append(p)
                        continue
                except Exception:
                    pass
        user_payments = filtered

    if not user_payments:
        from bot.keyboards.inline.user_keyboards import (
            get_back_to_payment_method_details_keyboard,
            get_payment_methods_manage_keyboard,
        )

        back_pm_id = ""
        try:
            split_a, split_b, back_pm_id = callback.data.split(":", 2)
        except Exception:
            back_pm_id = ""
        back_markup = (
            get_back_to_payment_method_details_keyboard(back_pm_id, current_lang, i18n)
            if back_pm_id
            else get_payment_methods_manage_keyboard(current_lang, i18n, has_card=True)
        )
        await callback.message.edit_text(_("payment_method_no_history"), reply_markup=back_markup)
        return

    traffic_mode = getattr(settings, "traffic_sale_mode", False)

    def _format_item(p: Payment) -> str:
        if traffic_mode:
            units_val = p.subscription_duration_months or 0
            units_display = (
                str(int(units_val)) if float(units_val).is_integer() else f"{units_val:g}"
            )
            title = p.description or _("traffic_purchase_title", traffic_gb=units_display)
        else:
            title = p.description or _(
                "subscription_purchase_title", months=p.subscription_duration_months or 1
            )
        date_str = p.created_at.strftime("%Y-%m-%d") if p.created_at else "N/A"
        return f"{date_str} — {title} — {p.amount:.2f} {p.currency}"

    lines = [_format_item(p) for p in user_payments]
    text = _("payment_method_tx_history_title") + "\n\n" + "\n".join(lines)
    try:
        split_a, split_b, split_pm_id_for_back = callback.data.split(":", 2)
    except Exception:
        split_pm_id_for_back = ""
    from bot.keyboards.inline.user_keyboards import (
        get_back_to_payment_method_details_keyboard,
        get_payment_methods_manage_keyboard,
    )

    back_markup = (
        get_back_to_payment_method_details_keyboard(split_pm_id_for_back, current_lang, i18n)
        if split_pm_id_for_back
        else get_payment_methods_manage_keyboard(current_lang, i18n, has_card=True)
    )
    await callback.message.edit_text(text, reply_markup=back_markup)


@router.callback_query(F.data.startswith("pm:list:"))
async def payment_methods_list(
    callback: types.CallbackQuery, settings: Settings, i18n_data: dict, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    from db.dal.user_billing_dal import list_user_payment_methods

    cards: List[tuple] = []
    methods = await list_user_payment_methods(session, callback.from_user.id)
    for m in methods:

        def _is_yoomoney_network(network: Optional[str]) -> bool:
            s = (network or "").lower()
            return "yoomoney" in s or "yoo money" in s or "yoo-money" in s

        def _extract_last4(text: str) -> Optional[str]:
            digits = "".join(ch for ch in text if ch.isdigit())
            return digits[-4:] if len(digits) >= 4 else None

        def _format_pm_title(network: Optional[str], last4: Optional[str]) -> str:
            if _is_yoomoney_network(network):
                l4 = last4 or _extract_last4(network or "")
                if l4:
                    return get_text("payment_method_wallet_title", last4=l4)
                return get_text("payment_method_wallet_title", last4="****")
            if last4:
                network_name = network or get_text("payment_network_card")
                return get_text("payment_method_card_title", network=network_name, last4=last4)
            network_name = network or get_text("payment_network_generic")
            return get_text("payment_method_generic_title", network=network_name)

        title = _format_pm_title(m.card_network, m.card_last4)
        cards.append((str(m.method_id), title if not m.is_default else f"⭐ {title}"))

    try:
        _, _, page_str = callback.data.split(":", 2)
        page = int(page_str)
    except Exception:
        page = 0

    text = get_text("payment_methods_title")
    if not cards:
        text += "\n\n" + get_text("payment_method_none")
    await callback.message.edit_text(
        text, reply_markup=get_payment_methods_list_keyboard(cards, page, current_lang, i18n)
    )
    try:
        await callback.answer()
    except Exception:
        pass


logger = logging.getLogger(__name__)


def create_service(ctx: ServiceFactoryContext) -> YooKassaService:
    bundle = ctx.config_for("yookassa_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, YooKassaConfig) else YooKassaConfig()
    )
    return YooKassaService(
        shop_id=config.SHOP_ID,
        secret_key=config.SECRET_KEY,
        configured_return_url=config.RETURN_URL,
        bot_username_for_default_return=ctx.bot_username_for_default_return,
        settings_obj=ctx.settings,
        config=config,
        subscription_service=ctx.subscription_service,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    service: YooKassaService = ctx.request.app["yookassa_service"]
    if not service or not service.configured:
        return payment_unavailable()

    try:
        amounts = payment_record_amounts(
            months=ctx.months,
            sale_mode=ctx.sale_mode,
            traffic_gb=ctx.traffic_gb,
        )
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency="RUB",
            status="pending_yookassa",
            provider="yookassa",
        )
        metadata = {
            "user_id": str(ctx.user_id),
            "subscription_months": str(
                int(float(ctx.months))
                if not amounts.traffic_sale and not amounts.hwid_devices_sale
                else 0
            ),
            "payment_db_id": str(payment.payment_id),
            "sale_mode": ctx.sale_mode,
            "source": "webapp",
        }
        if amounts.traffic_sale:
            metadata["traffic_gb"] = format_number_for_payload(ctx.traffic_gb or ctx.months)
        if amounts.hwid_devices_sale:
            metadata["hwid_devices"] = str(int(float(ctx.months)))
        if amounts.tariff_key:
            metadata["tariff_key"] = amounts.tariff_key
        response = await service.create_payment(
            amount=ctx.price,
            currency="RUB",
            description=ctx.description,
            metadata=metadata,
            receipt_email=service.config.DEFAULT_RECEIPT_EMAIL,
            save_payment_method=False,
        )
        payment_url = response.get("confirmation_url") if response else None
        if not payment_url:
            await mark_payment_failed_creation(ctx.session, payment.payment_id)
            return payment_failed()

        await payment_dal.update_payment_status_by_db_id(
            ctx.session,
            payment.payment_id,
            response.get("status", "pending"),
            yk_payment_id=response.get("id"),
        )
        await ctx.session.commit()
        return payment_link_response(payment_url=payment_url, payment_id=payment.payment_id)
    except Exception:
        await ctx.session.rollback()
        logger.exception("YooKassa WebApp payment failed")
        return payment_failed()


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="YooKassa",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_YOOKASSA_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_YOOKASSA_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_YOOKASSA_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_YOOKASSA_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_YOOKASSA_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_YOOKASSA_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💳",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "YOOKASSA_ENABLED", "bool", "Включена", subsection="YooKassa", attr="ENABLED"
    ),
    ProviderManifestField(
        "YOOKASSA_SHOP_ID", "string", "Shop ID", subsection="YooKassa", attr="SHOP_ID"
    ),
    ProviderManifestField(
        "YOOKASSA_SECRET_KEY",
        "string",
        "Secret key",
        subsection="YooKassa",
        secret=True,
        attr="SECRET_KEY",
    ),
    ProviderManifestField(
        "YOOKASSA_RETURN_URL", "url", "Return URL", subsection="YooKassa", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "YOOKASSA_DEFAULT_RECEIPT_EMAIL",
        "string",
        "Email для чека по умолчанию",
        subsection="YooKassa",
        attr="DEFAULT_RECEIPT_EMAIL",
    ),
    ProviderManifestField(
        "YOOKASSA_VAT_CODE",
        "int",
        "VAT code",
        description="1..6 в зависимости от системы налогообложения",
        subsection="YooKassa",
        min=1,
        max=6,
        attr="VAT_CODE",
    ),
    ProviderManifestField(
        "YOOKASSA_AUTOPAYMENTS_ENABLED",
        "bool",
        "Автоплатежи (recurring)",
        subsection="YooKassa",
        attr="AUTOPAYMENTS_ENABLED",
    ),
    ProviderManifestField(
        "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING",
        "bool",
        "Принудительная привязка карты",
        subsection="YooKassa",
        attr="AUTOPAYMENTS_REQUIRE_CARD_BINDING",
    ),
)


SPEC = PaymentProviderSpec(
    id="yookassa",
    provider_key="yookassa",
    label="YooKassa",
    webapp_label="ЮKassa",
    webapp_labels={"ru": "ЮKassa", "en": "YooKassa"},
    webapp_icon="CreditCard",
    telegram_labels={"ru": "ЮKassa", "en": "YooKassa"},
    telegram_emoji="💳",
    pending_status="pending_yookassa",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="yookassa_service",
    callback_prefix="pay_yk",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/yookassa",
    webhook_route=yookassa_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    config_class=YooKassaConfig,
    presentation_class=YooKassaPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
)
