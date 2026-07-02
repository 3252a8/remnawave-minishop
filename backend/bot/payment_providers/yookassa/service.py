import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

from yookassa import Configuration
from yookassa import Payment as YooKassaPayment
from yookassa.domain.common.confirmation_type import ConfirmationType
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder

from config.settings import Settings

from ..base import (
    normalize_payment_currency_code,
    provider_runtime_enabled,
)
from ..shared import (
    RecurringChargeContext,
    RecurringChargeResult,
)
from .config import YooKassaConfig

if TYPE_CHECKING:
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    SubscriptionService = object

logger = logging.getLogger(__name__)


class YooKassaService:
    def __init__(
        self,
        shop_id: str | None,
        secret_key: str | None,
        configured_return_url: str | None,
        bot_username_for_default_return: str | None = None,
        settings_obj: Settings | None = None,
        config: YooKassaConfig | None = None,
        subscription_service: SubscriptionService | None = None,
    ):

        self.settings = settings_obj
        self.config = config or YooKassaConfig()
        self.subscription_service = subscription_service
        self._bot_username_for_default_return = bot_username_for_default_return
        self._configured_return_url_override = configured_return_url
        # (shop_id, secret_key) currently loaded into the global SDK.
        self._sdk_configured_for: tuple[str, str] | None = None

        if not self.configured:
            if not provider_runtime_enabled(self.config):
                logger.warning(
                    "YooKassa is disabled via YOOKASSA_ENABLED flag. Payment functionality will be DISABLED."  # noqa: E501
                )
            else:
                logger.warning(
                    "YooKassa SHOP_ID or SECRET_KEY not configured in settings. "
                    "Payment functionality will be DISABLED."
                )
        logger.info("YooKassa Service effective return_url for payments: %s", self.return_url)

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
            logger.info("YooKassa SDK (re)configured for shop_id: %s...", shop_id[:5])
        except Exception:
            logger.exception("Failed to configure YooKassa SDK.")
            self._sdk_configured_for = None

    @property
    def return_url(self) -> str:
        url = self._configured_return_url_override or self.config.RETURN_URL
        if url:
            return url
        if self._bot_username_for_default_return:
            return f"https://t.me/{self._bot_username_for_default_return}"
        return "https://example.com/payment_error_no_return_url_configured"

    @property
    def recurring_active(self) -> bool:
        """Auto-renew is available only when YooKassa autopayments are switched on."""
        return bool(self.configured and self.config.autopayments_active)

    async def charge_saved_payment_method(
        self, context: RecurringChargeContext
    ) -> RecurringChargeResult:
        """Charge a saved YooKassa ``payment_method_id`` for auto-renew.

        Initiates a charge with the YooKassa-style metadata bag; the YooKassa
        webhook reconstructs and activates the renewal from that metadata, so
        this method only reports whether the charge was accepted.
        """
        if not self.recurring_active:
            return RecurringChargeResult.failed("recurring_inactive")
        saved_method_id = getattr(context.saved_method, "provider_payment_method_id", None)
        if not saved_method_id:
            return RecurringChargeResult.failed("missing_saved_method")
        resp = await self.create_payment(
            amount=float(context.amount),
            currency=context.currency,
            description=context.description,
            metadata=dict(context.metadata),
            payment_method_id=saved_method_id,
            save_payment_method=False,
            capture=True,
        )
        status = (resp or {}).get("status")
        if not resp or status not in {"pending", "waiting_for_capture", "succeeded"}:
            return RecurringChargeResult.failed(f"unexpected_status:{status}")
        return RecurringChargeResult.ok(provider_payment_id=resp.get("id"), status=status)

    async def create_payment(
        self,
        amount: float,
        currency: str,
        description: str,
        metadata: dict[str, Any],
        receipt_email: str | None = None,
        receipt_phone: str | None = None,
        save_payment_method: bool = False,
        payment_method_id: str | None = None,
        capture: bool = True,
        bind_only: bool = False,
    ) -> dict[str, Any] | None:
        if not self.configured:
            logger.error("YooKassa is not configured. Cannot create payment.")
            return None

        if not self.settings:
            logger.error(
                "YooKassaService: Settings object not available. Cannot create payment with receipt details."  # noqa: E501
            )
            return {
                "error": True,
                "internal_message": "Service settings (Settings object) not initialized.",
            }

        currency = normalize_payment_currency_code(currency)
        if currency != "RUB":
            logger.error("YooKassa currency %s is not supported by this integration", currency)
            return None

        customer_contact_for_receipt = {}
        if receipt_email:
            customer_contact_for_receipt["email"] = receipt_email
        elif receipt_phone:
            customer_contact_for_receipt["phone"] = receipt_phone
        elif self.config.DEFAULT_RECEIPT_EMAIL:
            customer_contact_for_receipt["email"] = self.config.DEFAULT_RECEIPT_EMAIL
        else:
            logger.error(
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

            receipt_items_list: list[dict[str, Any]] = [
                {
                    "description": description[:128],
                    "quantity": "1.00",
                    "amount": {"value": str(round(amount, 2)), "currency": currency.upper()},
                    "vat_code": str(self.config.VAT_CODE),
                    "payment_mode": self.config.yk_receipt_payment_mode,
                    "payment_subject": self.config.yk_receipt_payment_subject,
                }
            ]

            receipt_data_dict: dict[str, Any] = {
                "customer": customer_contact_for_receipt,
                "items": receipt_items_list,
            }

            builder.set_receipt(receipt_data_dict)

            idempotence_key = str(uuid.uuid4())
            payment_request = builder.build()

            logger.info(
                "Creating YooKassa payment (Idempotence-Key: %s). Amount: %s %s. Metadata: %s. "
                "Receipt: %s",
                idempotence_key,
                amount,
                currency,
                metadata,
                receipt_data_dict,
            )

            response = await asyncio.to_thread(
                YooKassaPayment.create,
                payment_request,
                idempotence_key,
            )

            logger.info(
                "YooKassa Payment.create response: ID=%s, Status=%s, Paid=%s",
                response.id,
                response.status,
                response.paid,
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
            logger.exception("YooKassa payment creation failed.")
            return None

    async def get_payment_info(self, payment_id_in_yookassa: str) -> dict[str, Any] | None:
        if not self.configured:
            logger.error("YooKassa is not configured. Cannot get payment info.")
            return None
        try:
            logger.info("Fetching payment info from YooKassa for ID: %s", payment_id_in_yookassa)

            payment_info_yk = await asyncio.to_thread(
                YooKassaPayment.find_one,
                payment_id_in_yookassa,
            )

            if payment_info_yk:
                logger.info(
                    "YooKassa payment info for %s: Status=%s, Paid=%s",
                    payment_id_in_yookassa,
                    payment_info_yk.status,
                    payment_info_yk.paid,
                )
                pm = getattr(payment_info_yk, "payment_method", None)
                pm_payload: dict[str, Any] = {}
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
                        last4_val = card_obj.last4
                    elif isinstance(account_number, str) and len(account_number) >= 4:
                        last4_val = account_number[-4:]
                    pm_payload = {
                        "id": pm_id,
                        "type": pm_type,
                        "title": pm_title,
                        "card_last4": last4_val,
                    }
                confirmation = getattr(payment_info_yk, "confirmation", None)
                confirmation_url = (
                    getattr(confirmation, "confirmation_url", None) if confirmation else None
                )
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
                    "confirmation_url": confirmation_url,
                    "test_mode": getattr(payment_info_yk, "test", None),
                }
            else:
                logger.warning(
                    "No payment info found in YooKassa for ID: %s", payment_id_in_yookassa
                )
                return None
        except Exception:
            logger.exception("YooKassa get payment info for %s failed.", payment_id_in_yookassa)
            return None

    async def cancel_payment(self, payment_id_in_yookassa: str) -> bool:
        if not self.configured:
            logger.error("YooKassa is not configured. Cannot cancel payment.")
            return False
        try:
            await asyncio.to_thread(YooKassaPayment.cancel, payment_id_in_yookassa)
            logger.info("Cancelled YooKassa payment %s", payment_id_in_yookassa)
            return True
        except Exception:
            logger.exception("Failed to cancel YooKassa payment %s.", payment_id_in_yookassa)
            return False
