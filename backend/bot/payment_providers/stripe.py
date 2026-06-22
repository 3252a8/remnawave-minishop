from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from aiogram import F, Router, types
from aiohttp import ClientError, web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal, user_billing_dal

from .base import (
    PaymentProviderSpec,
    ProviderEnvConfig,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    parse_supported_currency_codes,
    provider_env_file,
    provider_runtime_enabled,
)
from .shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
    HttpClientMixin,
    PaymentSuccessRequest,
    RecurringChargeContext,
    RecurringChargeResult,
    build_payment_record_payload,
    create_webapp_payment_record,
    describe_payment,
    finalize_successful_payment,
    finalize_webapp_link_payment,
    first_value,
    lookup_payment_by_order_or_provider_id,
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    notify_user_payment_failed,
    parse_payment_callback,
    payment_failed,
    payment_record_amounts,
    payment_unavailable,
    payment_units_for_activation,
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
    safe_callback_answer,
    sale_mode_base,
)

logger = logging.getLogger(__name__)
_LOG = "stripe"

_SUCCESS_EVENT_TYPES = {"checkout.session.completed", "payment_intent.succeeded"}
_FAILED_EVENT_TYPES = {
    "checkout.session.expired",
    "payment_intent.canceled",
    "payment_intent.payment_failed",
}
_SUCCESS_PAYMENT_INTENT_STATUSES = {"succeeded", "processing", "requires_capture"}
_FAILED_PAYMENT_INTENT_STATUSES = {
    "canceled",
    "requires_action",
    "requires_payment_method",
}

# Stripe expects these currencies in whole units instead of hundredths.
_ZERO_DECIMAL_CURRENCIES = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}


def _stripe_amount_to_minor_units(amount: Any, currency: Any) -> int:
    """Convert a display amount into the integer amount Stripe expects."""
    currency_code = normalize_payment_currency_code(currency)
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid_amount") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("invalid_amount")
    if currency_code in _ZERO_DECIMAL_CURRENCIES:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _metadata_pairs(
    metadata: Mapping[str, Any],
    *,
    prefix: str = "metadata",
) -> List[tuple[str, str]]:
    pairs: List[tuple[str, str]] = []
    for key, value in metadata.items():
        if value is None:
            continue
        clean_key = "".join(ch for ch in str(key) if ch.isalnum() or ch in {"_", "-"}).strip()
        if not clean_key:
            continue
        pairs.append((f"{prefix}[{clean_key[:40]}]", str(value)[:500]))
    return pairs


def _stripe_json_success(status: int, data: Any) -> bool:
    return 200 <= status < 300 and not (isinstance(data, dict) and data.get("error"))


def _encode_saved_method(customer_id: str, payment_method_id: str) -> str:
    return f"{customer_id}|{payment_method_id}"


def _decode_saved_method(value: Any) -> tuple[Optional[str], Optional[str]]:
    text = str(value or "").strip()
    if not text:
        return None, None
    if "|" in text:
        customer_id, payment_method_id = text.split("|", 1)
        return customer_id.strip() or None, payment_method_id.strip() or None
    return None, text


class StripeConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="STRIPE_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    SECRET_KEY: Optional[str] = None
    WEBHOOK_SECRET: Optional[str] = None
    BASE_URL: str = Field(default="https://api.stripe.com")
    RETURN_URL: Optional[str] = None
    CANCEL_URL: Optional[str] = None
    PAYMENT_METHOD_TYPES: str = Field(default="card")
    SUPPORTED_CURRENCIES: str = Field(default="")
    RECURRING_ENABLED: bool = Field(default=False)
    VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    WEBHOOK_TOLERANCE_SECONDS: int = Field(default=300, ge=0)

    @field_validator(
        "SECRET_KEY",
        "WEBHOOK_SECRET",
        "RETURN_URL",
        "CANCEL_URL",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def payment_method_types_list(self) -> tuple[str, ...]:
        values: List[str] = []
        for item in (self.PAYMENT_METHOD_TYPES or "").replace(";", ",").split(","):
            value = item.strip().lower()
            if value and value not in values:
                values.append(value)
        return tuple(values or ["card"])

    @property
    def webhook_path(self) -> str:
        return "/webhook/stripe"


class StripePresentation(ProviderEnvConfig):
    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_STRIPE_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class StripeService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Any,
        settings: Settings,
        config: StripeConfig,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        default_return_url: str,
    ):
        self.bot = bot
        self.settings = settings
        self.config = config
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self._default_return_url = default_return_url
        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)

        if not self.configured:
            logging.warning(
                "StripeService initialized but not fully configured. Payments disabled."
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.secret_key)

    @property
    def recurring_active(self) -> bool:
        return bool(self.configured and self.config.RECURRING_ENABLED)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://api.stripe.com").rstrip("/")

    @property
    def secret_key(self) -> str:
        return (self.config.SECRET_KEY or "").strip()

    @property
    def webhook_secret(self) -> str:
        return (self.config.WEBHOOK_SECRET or "").strip()

    @property
    def return_url(self) -> str:
        if self.config.RETURN_URL:
            return self.config.RETURN_URL
        if self._default_return_url:
            return f"https://t.me/{self._default_return_url}"
        return "https://example.com/payment-return"

    @property
    def cancel_url(self) -> str:
        return self.config.CANCEL_URL or self.return_url

    def _headers(self, *, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _post_form(
        self,
        endpoint: str,
        data: Iterable[tuple[str, Any]],
        *,
        idempotency_key: Optional[str] = None,
        log_prefix: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}{endpoint}",
                data=[(key, str(value)) for key, value in data if value is not None],
                headers=self._headers(idempotency_key=idempotency_key),
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("%s: invalid JSON response: %s", log_prefix, response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not _stripe_json_success(response.status, response_data):
                    logging.error(
                        "%s: Stripe API returned error (status=%s, body=%s)",
                        log_prefix,
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                return True, response_data
        except (ClientError, TimeoutError, OSError) as exc:
            logging.exception("%s: Stripe request failed.", log_prefix)
            return False, {"message": str(exc)}

    async def _get_json(self, endpoint: str, *, log_prefix: str) -> Tuple[bool, Dict[str, Any]]:
        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}{endpoint}",
                headers={"Authorization": f"Bearer {self.secret_key}"},
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("%s: invalid JSON response: %s", log_prefix, response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not _stripe_json_success(response.status, response_data):
                    logging.error(
                        "%s: Stripe API returned error (status=%s, body=%s)",
                        log_prefix,
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                return True, response_data
        except (ClientError, TimeoutError, OSError) as exc:
            logging.exception("%s: Stripe request failed.", log_prefix)
            return False, {"message": str(exc)}

    async def create_checkout_session(
        self,
        *,
        payment_db_id: int,
        user_id: int,
        amount: float,
        currency: str,
        description: str,
        metadata: Mapping[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(currency)
        try:
            unit_amount = _stripe_amount_to_minor_units(amount, currency_code)
        except ValueError as exc:
            return False, {"message": str(exc)}

        session_metadata = {
            **dict(metadata),
            "user_id": str(user_id),
            "payment_db_id": str(payment_db_id),
            "source": str(metadata.get("source") or "bot"),
        }
        form: List[tuple[str, Any]] = [
            ("mode", "payment"),
            ("success_url", self.return_url),
            ("cancel_url", self.cancel_url),
            ("client_reference_id", str(payment_db_id)),
            ("line_items[0][quantity]", "1"),
            ("line_items[0][price_data][currency]", currency_code.lower()),
            ("line_items[0][price_data][unit_amount]", unit_amount),
            ("line_items[0][price_data][product_data][name]", (description or "Payment")[:250]),
            ("payment_intent_data[description]", (description or "Payment")[:500]),
        ]
        for index, method_type in enumerate(self.config.payment_method_types_list):
            form.append((f"payment_method_types[{index}]", method_type))
        form.extend(_metadata_pairs(session_metadata))
        form.extend(_metadata_pairs(session_metadata, prefix="payment_intent_data[metadata]"))
        if self.recurring_active:
            form.append(("customer_creation", "always"))
            form.append(("payment_intent_data[setup_future_usage]", "off_session"))

        return await self._post_form(
            "/v1/checkout/sessions",
            form,
            idempotency_key=f"checkout:{payment_db_id}",
            log_prefix="Stripe create_checkout_session",
        )

    async def create_off_session_payment_intent(
        self,
        *,
        payment_db_id: int,
        user_id: int,
        customer_id: str,
        payment_method_id: str,
        amount: float,
        currency: str,
        description: str,
        metadata: Mapping[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}
        currency_code = normalize_payment_currency_code(currency)
        try:
            minor_amount = _stripe_amount_to_minor_units(amount, currency_code)
        except ValueError as exc:
            return False, {"message": str(exc)}

        intent_metadata = {
            **dict(metadata),
            "user_id": str(user_id),
            "payment_db_id": str(payment_db_id),
            "source": "auto_renew",
        }
        form: List[tuple[str, Any]] = [
            ("amount", minor_amount),
            ("currency", currency_code.lower()),
            ("customer", customer_id),
            ("payment_method", payment_method_id),
            ("off_session", "true"),
            ("confirm", "true"),
            ("description", (description or "Payment")[:500]),
        ]
        form.extend(_metadata_pairs(intent_metadata))

        return await self._post_form(
            "/v1/payment_intents",
            form,
            idempotency_key=f"renewal:{payment_db_id}",
            log_prefix="Stripe create_off_session_payment_intent",
        )

    async def retrieve_payment_intent(self, payment_intent_id: str) -> Optional[Dict[str, Any]]:
        payment_intent_id = str(payment_intent_id or "").strip()
        if not payment_intent_id or not self.configured:
            return None
        success, data = await self._get_json(
            f"/v1/payment_intents/{payment_intent_id}",
            log_prefix="Stripe retrieve_payment_intent",
        )
        return data if success else None

    async def retrieve_payment_method(self, payment_method_id: str) -> Optional[Dict[str, Any]]:
        payment_method_id = str(payment_method_id or "").strip()
        if not payment_method_id or not self.configured:
            return None
        success, data = await self._get_json(
            f"/v1/payment_methods/{payment_method_id}",
            log_prefix="Stripe retrieve_payment_method",
        )
        return data if success else None

    async def charge_saved_payment_method(
        self, context: RecurringChargeContext
    ) -> RecurringChargeResult:
        if not self.recurring_active:
            return RecurringChargeResult.failed("recurring_inactive")

        saved_value = getattr(context.saved_method, "provider_payment_method_id", "")
        customer_id, payment_method_id = _decode_saved_method(saved_value)
        if not customer_id or not payment_method_id:
            return RecurringChargeResult.failed("missing_saved_method")

        payment_payload = build_payment_record_payload(
            user_id=context.user_id,
            amount=float(context.amount),
            currency=context.currency,
            status="pending_stripe",
            description=context.description,
            months=context.months,
            provider="stripe",
            sale_mode=context.sale_mode,
            hwid_quote=dict(context.hwid_quote or {}) or None,
        )
        try:
            payment = await payment_dal.create_payment_record(context.session, payment_payload)
        except Exception as exc:
            logging.exception("Stripe auto-renew failed to create local payment record")
            return RecurringChargeResult.failed(str(exc))

        success, response_data = await self.create_off_session_payment_intent(
            payment_db_id=payment.payment_id,
            user_id=context.user_id,
            customer_id=customer_id,
            payment_method_id=payment_method_id,
            amount=float(context.amount),
            currency=context.currency,
            description=context.description,
            metadata=dict(context.metadata),
        )
        provider_payment_id = first_value(response_data, "id")
        status = (
            str(response_data.get("status") or "").lower()
            if isinstance(response_data, dict)
            else ""
        )
        if provider_payment_id:
            try:
                await payment_dal.update_provider_payment_and_status(
                    context.session,
                    payment.payment_id,
                    str(provider_payment_id),
                    "pending_stripe",
                )
            except Exception:
                logging.exception(
                    "Stripe auto-renew failed to store provider payment id %s",
                    provider_payment_id,
                )

        if not success or status in _FAILED_PAYMENT_INTENT_STATUSES:
            try:
                await payment_dal.update_payment_status_by_db_id(
                    context.session,
                    payment.payment_id,
                    "failed_creation",
                )
            except Exception:
                logging.exception(
                    "Stripe auto-renew failed to mark payment %s as failed_creation",
                    payment.payment_id,
                )
            return RecurringChargeResult.failed(str(response_data.get("message") or response_data))

        if status and status not in _SUCCESS_PAYMENT_INTENT_STATUSES:
            return RecurringChargeResult.failed(f"unexpected_status:{status}")

        return RecurringChargeResult.ok(provider_payment_id=provider_payment_id, status=status)

    async def try_reuse_pending_payment(self, payment: Any) -> Optional[str]:
        return str(getattr(payment, "provider_payment_url", None) or "").strip() or None

    def verify_signature(self, raw_body: bytes, header_value: str) -> bool:
        secret = self.webhook_secret
        if not secret:
            logging.error("Stripe webhook: no webhook secret configured.")
            return False
        timestamp: Optional[int] = None
        signatures: List[str] = []
        for item in str(header_value or "").split(","):
            key, sep, value = item.partition("=")
            if not sep:
                continue
            if key == "t":
                try:
                    timestamp = int(value)
                except ValueError:
                    return False
            elif key == "v1":
                signatures.append(value)
        if timestamp is None or not signatures:
            return False
        tolerance = int(self.config.WEBHOOK_TOLERANCE_SECONDS or 0)
        if tolerance > 0 and abs(time.time() - timestamp) > tolerance:
            return False
        signed_payload = str(timestamp).encode("utf-8") + b"." + raw_body
        expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, signature) for signature in signatures)

    async def _persist_recurring_payment_method(
        self,
        session: AsyncSession,
        *,
        payment: Any,
        payment_intent: Mapping[str, Any],
        fallback_customer_id: Optional[str] = None,
    ) -> None:
        if not self.recurring_active:
            return
        customer_id = str(payment_intent.get("customer") or fallback_customer_id or "").strip()
        payment_method_id = str(payment_intent.get("payment_method") or "").strip()
        if not customer_id or not payment_method_id:
            return
        payment_method_payload = await self.retrieve_payment_method(payment_method_id)
        card = (
            payment_method_payload.get("card") if isinstance(payment_method_payload, dict) else None
        ) or {}
        card_last4 = card.get("last4")
        card_network = card.get("brand") or (
            payment_method_payload.get("type") if isinstance(payment_method_payload, dict) else None
        )
        await user_billing_dal.upsert_user_payment_method(
            session,
            user_id=int(getattr(payment, "user_id")),
            provider_payment_method_id=_encode_saved_method(customer_id, payment_method_id),
            provider="stripe",
            card_last4=card_last4,
            card_network=card_network,
            set_default=True,
        )

    def _payment_db_id_from_object(self, obj: Mapping[str, Any]) -> Optional[str]:
        metadata_raw = obj.get("metadata")
        metadata: Mapping[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
        payment_db_id = metadata.get("payment_db_id") or obj.get("client_reference_id")
        return str(payment_db_id).strip() if payment_db_id else None

    async def _payment_intent_for_success(
        self,
        event_type: str,
        obj: Mapping[str, Any],
    ) -> tuple[Optional[Mapping[str, Any]], Optional[str], Optional[str]]:
        if event_type == "payment_intent.succeeded":
            return obj, str(obj.get("id") or "").strip() or None, None
        payment_intent_id = str(obj.get("payment_intent") or "").strip()
        if not payment_intent_id:
            return None, None, str(obj.get("id") or "").strip() or None
        payment_intent = await self.retrieve_payment_intent(payment_intent_id)
        return payment_intent, payment_intent_id, str(obj.get("id") or "").strip() or None

    async def _handle_success_event(
        self,
        event_type: str,
        obj: Mapping[str, Any],
    ) -> web.Response:
        if event_type == "checkout.session.completed" and obj.get("payment_status") != "paid":
            logging.info(
                "Stripe webhook: checkout session completed but payment_status is not paid."
            )
            return web.json_response({"received": True})

        (
            payment_intent,
            payment_intent_id,
            checkout_session_id,
        ) = await self._payment_intent_for_success(event_type, obj)
        provider_payment_id = payment_intent_id or checkout_session_id
        payment_db_id = self._payment_db_id_from_object(payment_intent or obj)
        if not payment_db_id:
            payment_db_id = self._payment_db_id_from_object(obj)

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=payment_db_id,
                provider_payment_id=provider_payment_id,
            )
            if not payment:
                logging.error(
                    "Stripe webhook: payment not found (payment_db_id=%s provider_id=%s)",
                    payment_db_id,
                    provider_payment_id,
                )
                return web.json_response({"error": "payment_not_found"}, status=404)
            if payment.status == "succeeded":
                return web.json_response({"received": True})

            amount_minor = None
            currency = None
            if payment_intent:
                amount_minor = payment_intent.get("amount_received") or payment_intent.get("amount")
                currency = payment_intent.get("currency")
            if amount_minor is None:
                amount_minor = obj.get("amount_total")
            if currency is None:
                currency = obj.get("currency")
            if amount_minor is not None:
                expected_minor = _stripe_amount_to_minor_units(payment.amount, payment.currency)
                if int(amount_minor) != expected_minor:
                    logging.error(
                        "Stripe webhook: amount mismatch for payment %s (expected=%s got=%s)",
                        payment.payment_id,
                        expected_minor,
                        amount_minor,
                    )
                    return web.json_response({"error": "amount_mismatch"}, status=400)
            if currency and normalize_payment_currency_code(
                currency
            ) != normalize_payment_currency_code(payment.currency):
                logging.error(
                    "Stripe webhook: currency mismatch for payment %s (expected=%s got=%s)",
                    payment.payment_id,
                    payment.currency,
                    currency,
                )
                return web.json_response({"error": "currency_mismatch"}, status=400)

            try:
                if payment_intent:
                    await self._persist_recurring_payment_method(
                        session,
                        payment=payment,
                        payment_intent=payment_intent,
                        fallback_customer_id=str(obj.get("customer") or "") or None,
                    )
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment.payment_id,
                    provider_payment_id or str(payment.payment_id),
                    PAYMENT_STATUS_PENDING_FINALIZATION,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "Stripe webhook: failed to mark payment %s as succeeded.",
                    payment.payment_id,
                )
                return web.json_response({"error": "payment_update_failed"}, status=500)

            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)
            outcome = await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    subscription_service=self.subscription_service,
                    referral_service=self.referral_service,
                    payment=payment,
                    user_id=payment.user_id,
                    amount=float(payment.amount),
                    currency=payment.currency,
                    sale_mode=sale_mode,
                    months=payment_months,
                    traffic_amount=float(payment_months),
                    provider_subscription="stripe",
                    provider_notification="stripe",
                    db_user=payment.user,
                    log_prefix="Stripe webhook",
                )
            )
            if outcome is None:
                return web.json_response({"error": "activation_failed"}, status=500)
            return web.json_response({"received": True})

    async def _handle_failed_event(
        self,
        event_type: str,
        obj: Mapping[str, Any],
    ) -> web.Response:
        provider_payment_id = str(
            obj.get("payment_intent") if event_type == "checkout.session.expired" else obj.get("id")
        ).strip()
        if not provider_payment_id:
            provider_payment_id = str(obj.get("id") or "").strip()
        payment_db_id = self._payment_db_id_from_object(obj)

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=payment_db_id,
                provider_payment_id=provider_payment_id,
            )
            if not payment:
                logging.warning(
                    "Stripe webhook: failed event for unknown payment "
                    "(payment_db_id=%s provider_id=%s)",
                    payment_db_id,
                    provider_payment_id,
                )
                return web.json_response({"received": True})
            if payment.status == "succeeded":
                return web.json_response({"received": True})
            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment.payment_id,
                    provider_payment_id or str(payment.payment_id),
                    "failed",
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "Stripe webhook: failed to mark payment %s as failed.",
                    payment.payment_id,
                )
                return web.json_response({"error": "payment_update_failed"}, status=500)
            await notify_user_payment_failed(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                payment=payment,
            )
            return web.json_response({"received": True})

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.json_response({"error": "service_not_configured"}, status=503)
        raw_body = await request.read()
        if self.config.VERIFY_WEBHOOK_SIGNATURE:
            signature_header = request.headers.get("Stripe-Signature", "")
            if not self.verify_signature(raw_body, signature_header):
                logging.error("Stripe webhook: invalid signature.")
                return web.json_response({"error": "invalid_signature"}, status=403)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid_json"}, status=400)

        event_type = str(payload.get("type") or "").strip()
        data_raw = payload.get("data")
        data: Mapping[str, Any] = data_raw if isinstance(data_raw, dict) else {}
        obj_raw = data.get("object")
        obj: Mapping[str, Any] = obj_raw if isinstance(obj_raw, dict) else {}
        if event_type in _SUCCESS_EVENT_TYPES:
            return await self._handle_success_event(event_type, obj)
        if event_type in _FAILED_EVENT_TYPES:
            return await self._handle_failed_event(event_type, obj)
        return web.json_response({"received": True})


async def stripe_webhook_route(request: web.Request) -> web.Response:
    service: StripeService = request.app["stripe_service"]
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_stripe_router")


@router.callback_query(F.data.startswith("pay_stripe:"))
async def pay_stripe_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    stripe_service: StripeService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return
    if not SPEC.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
        return
    if not stripe_service or not stripe_service.configured:
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=stripe_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = default_payment_currency_code_for_settings(settings)
    payment_description = describe_payment(translator, parts)
    reuse_amounts = payment_record_amounts(
        months=parts.months,
        sale_mode=parts.sale_mode,
        hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
    )
    reusable_payment = await payment_dal.find_recent_pending_provider_payment(
        session,
        user_id=callback.from_user.id,
        provider="stripe",
        pending_status="pending_stripe",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
    )
    if reusable_payment is not None:
        reusable_url = await stripe_service.try_reuse_pending_payment(reusable_payment)
        if reusable_url:
            await safe_callback_answer(callback)
            await render_payment_link(
                callback,
                translator=translator,
                current_lang=current_lang,
                i18n=i18n,
                parts=parts,
                payment_url=reusable_url,
                log_prefix=_LOG,
            )
            return

    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_stripe",
        description=payment_description,
        months=parts.months,
        provider="stripe",
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
    )
    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "Stripe: failed to create payment record for user %s.",
            callback.from_user.id,
        )
        await notify_payment_record_failure(callback, translator)
        return

    await safe_callback_answer(callback)
    success, response_data = await stripe_service.create_checkout_session(
        payment_db_id=payment_record.payment_id,
        user_id=payment_record.user_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        metadata={
            "subscription_months": str(int(float(parts.months)))
            if parts.sale_base == "subscription"
            else "0",
            "sale_mode": parts.sale_mode,
            "source": "telegram",
        },
    )
    await render_link_or_fail(
        callback,
        translator=translator,
        current_lang=current_lang,
        i18n=i18n,
        parts=parts,
        session=session,
        payment=payment_record,
        api_success=success,
        payment_url=first_value(response_data, "url") if success else None,
        provider_payment_id=first_value(response_data, "id"),
        provider_response=response_data,
        log_prefix=_LOG,
    )


def create_service(ctx: ServiceFactoryContext) -> StripeService:
    bundle = ctx.config_for("stripe_service")
    config = bundle.config if bundle and isinstance(bundle.config, StripeConfig) else StripeConfig()
    return StripeService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = ctx.request.app["settings"]
    service: StripeService = ctx.request.app["stripe_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
    try:
        amounts = payment_record_amounts(
            months=ctx.months,
            sale_mode=ctx.sale_mode,
            traffic_gb=ctx.traffic_gb,
            hwid_device_count=ctx.hwid_device_count,
        )
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_stripe",
            provider="stripe",
        )
        success, response_data = await service.create_checkout_session(
            payment_db_id=payment.payment_id,
            user_id=ctx.user_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
            metadata={
                "subscription_months": str(int(float(ctx.months)))
                if sale_mode_base(ctx.sale_mode) == "subscription"
                else "0",
                "traffic_gb": str(ctx.traffic_gb or ctx.months) if amounts.traffic_sale else None,
                "hwid_devices": str(amounts.purchased_hwid_devices)
                if amounts.purchased_hwid_devices
                else None,
                "sale_mode": ctx.sale_mode,
                "source": "webapp",
            },
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Stripe WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(response_data, "url") if success else None,
        provider_payment_id=first_value(response_data, "id"),
        provider_response=response_data,
        log_prefix="Stripe",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service: StripeService = ctx.request.app.get("stripe_service")
    if not service or not service.configured:
        return None
    return await service.try_reuse_pending_payment(payment)


def _supported_currencies(config: Any) -> Optional[tuple[str, ...]]:
    values = parse_supported_currency_codes(getattr(config, "SUPPORTED_CURRENCIES", None))
    return values or None


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Stripe",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_STRIPE_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_STRIPE_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_STRIPE_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_STRIPE_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_STRIPE_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_STRIPE_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("STRIPE_ENABLED", "bool", "Enabled", subsection="Stripe", attr="ENABLED"),
    ProviderManifestField(
        "STRIPE_SECRET_KEY",
        "string",
        "Secret key",
        description="Stripe secret API key used for Checkout Sessions and PaymentIntents.",
        subsection="Stripe",
        secret=True,
        attr="SECRET_KEY",
    ),
    ProviderManifestField(
        "STRIPE_WEBHOOK_SECRET",
        "string",
        "Webhook secret",
        description="Stripe endpoint signing secret that starts with whsec_.",
        subsection="Stripe",
        secret=True,
        attr="WEBHOOK_SECRET",
    ),
    ProviderManifestField(
        "STRIPE_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.stripe.com",
        subsection="Stripe",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "STRIPE_RETURN_URL",
        "url",
        "Return URL",
        subsection="Stripe",
        attr="RETURN_URL",
    ),
    ProviderManifestField(
        "STRIPE_CANCEL_URL",
        "url",
        "Cancel URL",
        subsection="Stripe",
        attr="CANCEL_URL",
    ),
    ProviderManifestField(
        "STRIPE_PAYMENT_METHOD_TYPES",
        "string",
        "Payment method types",
        description="Comma-separated Checkout payment method types. Default: card.",
        placeholder="card",
        subsection="Stripe",
        attr="PAYMENT_METHOD_TYPES",
    ),
    ProviderManifestField(
        "STRIPE_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Optional comma-separated presentment currencies allowed for this Stripe account. "
            "Empty means no local filter."
        ),
        placeholder="USD,EUR,GBP",
        subsection="Stripe",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "STRIPE_RECURRING_ENABLED",
        "bool",
        "Recurring payments",
        description="Save Checkout payment methods for off-session PaymentIntent auto-renewal.",
        subsection="Stripe",
        attr="RECURRING_ENABLED",
    ),
    ProviderManifestField(
        "STRIPE_VERIFY_WEBHOOK_SIGNATURE",
        "bool",
        "Verify webhook signature",
        description="Verify the Stripe-Signature header using STRIPE_WEBHOOK_SECRET.",
        subsection="Stripe",
        attr="VERIFY_WEBHOOK_SIGNATURE",
    ),
    ProviderManifestField(
        "STRIPE_WEBHOOK_TOLERANCE_SECONDS",
        "int",
        "Webhook tolerance seconds",
        description="Allowed clock skew for Stripe webhook signatures.",
        subsection="Stripe",
        min=0,
        max=86400,
        attr="WEBHOOK_TOLERANCE_SECONDS",
    ),
)


SPEC = PaymentProviderSpec(
    id="stripe",
    provider_key="stripe",
    label="Stripe",
    webapp_label="Stripe",
    webapp_labels={"ru": "Stripe", "en": "Stripe"},
    webapp_icon="CreditCard",
    telegram_labels={"ru": "Stripe", "en": "Stripe"},
    emoji="",
    telegram_emoji="",
    pending_status="pending_stripe",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="stripe_service",
    callback_prefix="pay_stripe",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/stripe",
    webhook_route=stripe_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=StripeConfig,
    presentation_class=StripePresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supports_recurring=True,
    supported_currencies_resolver=_supported_currencies,
    currency_support_note=(
        "Stripe supports many presentment currencies, but availability depends on the account "
        "country and enabled payment methods. Use STRIPE_SUPPORTED_CURRENCIES to restrict UI."
    ),
    currency_support_url="https://docs.stripe.com/currencies",
)
