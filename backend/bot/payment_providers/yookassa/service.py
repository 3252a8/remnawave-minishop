import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, TypeVar

from yookassa import Configuration
from yookassa import Payment as YooKassaPayment
from yookassa.domain.common.confirmation_type import ConfirmationType
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder

from config.settings import Settings
from db.dal import payment_dal

from ..base import (
    normalize_payment_currency_code,
    provider_runtime_enabled,
)
from ..shared import (
    RecurringChargeContext,
    RecurringChargeResult,
    build_payment_record_payload,
    format_decimal_amount,
)
from .config import YooKassaConfig

if TYPE_CHECKING:
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    SubscriptionService = object

logger = logging.getLogger(__name__)
SdkResultT = TypeVar("SdkResultT")
_YOOKASSA_IDEMPOTENCE_WINDOW = timedelta(hours=24)


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

    def _sdk_timeout_seconds(self) -> float:
        raw_timeout = getattr(self.settings, "PAYMENT_REQUEST_TIMEOUT_SECONDS", 20.0)
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            return 20.0
        return max(1.0, timeout)

    async def _run_sdk_call(
        self,
        operation: str,
        func: Callable[..., SdkResultT],
        *args: object,
    ) -> SdkResultT:
        timeout = self._sdk_timeout_seconds()
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning(
                "YooKassa SDK call timed out operation=%s timeout_seconds=%.1f",
                operation,
                timeout,
            )
            raise

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

        Creates the immutable local order before charging and puts its id in
        the YooKassa-style metadata bag.  The webhook validates the settled
        amount and currency against that order before activation.
        """
        if not self.recurring_active:
            return RecurringChargeResult.failed("recurring_inactive")
        saved_method_id = getattr(context.saved_method, "provider_payment_method_id", None)
        if not saved_method_id:
            return RecurringChargeResult.failed("missing_saved_method")

        currency = normalize_payment_currency_code(context.currency)
        idempotence_key = str(context.idempotence_key or uuid.uuid4()).strip()
        if not idempotence_key:
            idempotence_key = str(uuid.uuid4())
        payment_payload = build_payment_record_payload(
            user_id=context.user_id,
            amount=float(context.amount),
            currency=currency,
            status="pending_yookassa",
            description=context.description,
            months=context.months,
            provider="yookassa",
            sale_mode=context.sale_mode,
            hwid_quote=dict(context.hwid_quote or {}) or None,
        )
        payment_payload["idempotence_key"] = idempotence_key
        try:
            payment, created = await payment_dal.create_or_get_payment_record_by_idempotence_key(
                context.session,
                payment_payload,
            )
            if created:
                # Commit before starting the external charge: YooKassa can
                # deliver a successful webhook immediately, and it must be
                # able to resolve the expected local order from metadata.
                await context.session.commit()
        except Exception as exc:
            await context.session.rollback()
            logger.exception("YooKassa auto-renew failed to create local payment record")
            return RecurringChargeResult.failed(str(exc))

        if not created:
            existing_result = self._existing_auto_renew_result(payment)
            if existing_result is not None:
                return existing_result

        metadata = dict(context.metadata)
        metadata["payment_db_id"] = str(payment.payment_id)
        try:
            resp = await self.create_payment(
                amount=float(context.amount),
                currency=currency,
                description=context.description,
                metadata=metadata,
                payment_method_id=saved_method_id,
                save_payment_method=False,
                capture=True,
                idempotence_key=idempotence_key,
            )
        except Exception as exc:
            logger.exception("YooKassa auto-renew charge failed before API response")
            await self._mark_auto_renew_payment_failed(context.session, payment.payment_id)
            return RecurringChargeResult.failed(str(exc))

        status = (resp or {}).get("status")
        if not resp or status not in {"pending", "waiting_for_capture", "succeeded"}:
            provider_payment_id = str((resp or {}).get("id") or "").strip() or None
            await self._mark_auto_renew_payment_failed(
                context.session,
                payment.payment_id,
                yookassa_payment_id=provider_payment_id,
            )
            return RecurringChargeResult.failed(f"unexpected_status:{status}")

        provider_payment_id = str(resp.get("id") or "").strip() or None
        if provider_payment_id:
            try:
                await payment_dal.update_payment_status_by_db_id(
                    context.session,
                    payment.payment_id,
                    "pending_yookassa",
                    provider_payment_id,
                )
                await context.session.commit()
            except Exception:
                # The pre-charge commit plus payment_db_id metadata keeps the
                # successful webhook processable even when persisting the
                # provider id fails here.
                await context.session.rollback()
                logger.exception(
                    "YooKassa auto-renew failed to store provider payment id %s",
                    provider_payment_id,
                )
        return RecurringChargeResult.ok(provider_payment_id=provider_payment_id, status=status)

    @staticmethod
    def _existing_auto_renew_result(payment: Any) -> RecurringChargeResult | None:
        """Return a safe outcome for an already-claimed renewal order.

        A row with a known provider payment id must never create a second
        charge.  A failed row without that id is intentionally retried with
        the same YooKassa key: it covers the crash/timeout window where the
        remote payment may have been accepted but its response was lost.  The
        provider guarantees that replay for 24 hours only, so older uncertain
        rows fail closed instead of becoming a new charge.
        """
        status = str(getattr(payment, "status", "") or "").strip().lower()
        provider_payment_id = (
            str(
                getattr(payment, "yookassa_payment_id", None)
                or getattr(payment, "provider_payment_id", None)
                or ""
            ).strip()
            or None
        )
        if provider_payment_id:
            if status in {
                "pending",
                "pending_yookassa",
                "waiting_for_capture",
                "succeeded_pending_finalization",
                "succeeded",
            }:
                logger.info(
                    "YooKassa auto-renew reusing payment %s (provider id %s, status %s)",
                    getattr(payment, "payment_id", None),
                    provider_payment_id,
                    status,
                )
                return RecurringChargeResult.ok(
                    provider_payment_id=provider_payment_id,
                    status=status,
                )
            return RecurringChargeResult.failed(f"existing_payment:{status or 'unknown'}")
        if status in {"succeeded_pending_finalization", "succeeded"}:
            return RecurringChargeResult.ok(status=status)
        # Any existing record without a provider id is an uncertain previous
        # request, regardless of the local failure label.  Replay it only
        # inside YooKassa's documented 24-hour idempotence window; otherwise
        # the same key could become a brand-new merchant-initiated charge.
        created_at = getattr(payment, "created_at", None)
        if not isinstance(created_at, datetime):
            logger.error(
                "YooKassa auto-renew will not replay payment %s without a creation timestamp",
                getattr(payment, "payment_id", None),
            )
            return RecurringChargeResult.failed("idempotence_window_unknown")
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        else:
            created_at = created_at.astimezone(UTC)
        if datetime.now(UTC) - created_at >= _YOOKASSA_IDEMPOTENCE_WINDOW:
            logger.warning(
                "YooKassa auto-renew will not replay payment %s after the 24h idempotence window",
                getattr(payment, "payment_id", None),
            )
            return RecurringChargeResult.failed("idempotence_window_expired")
        return None

    async def _mark_auto_renew_payment_failed(
        self,
        session: Any,
        payment_db_id: int,
        *,
        yookassa_payment_id: str | None = None,
    ) -> None:
        try:
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id,
                "failed_creation",
                yookassa_payment_id,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "YooKassa auto-renew failed to mark payment %s as failed_creation",
                payment_db_id,
            )

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
        idempotence_key: str | None = None,
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
            # For binding cards only, do not capture and set the documented
            # minimum amount before rendering both the payment and receipt.
            if bind_only:
                capture = False
                amount = max(amount, 1.00)
            invoice_amount = str(format_decimal_amount(amount))
            builder = PaymentRequestBuilder()
            builder.set_amount({"value": invoice_amount, "currency": currency.upper()})
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
                    "amount": {"value": invoice_amount, "currency": currency.upper()},
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

            idempotence_key = str(idempotence_key or uuid.uuid4()).strip()
            if not idempotence_key:
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

            response = await self._run_sdk_call(
                "payment.create",
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

            payment_info_yk = await self._run_sdk_call(
                "payment.find_one",
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
            await self._run_sdk_call(
                "payment.cancel",
                YooKassaPayment.cancel,
                payment_id_in_yookassa,
            )
            logger.info("Cancelled YooKassa payment %s", payment_id_in_yookassa)
            return True
        except Exception:
            logger.exception("Failed to cancel YooKassa payment %s.", payment_id_in_yookassa)
            return False
