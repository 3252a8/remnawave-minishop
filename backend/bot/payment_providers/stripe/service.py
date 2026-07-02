from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object
from config.settings import Settings
from db.dal import payment_dal, user_billing_dal

from ..base import (
    normalize_payment_currency_code,
    provider_runtime_enabled,
)
from ..shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
    HttpClientMixin,
    PaymentSuccessRequest,
    RecurringChargeContext,
    RecurringChargeResult,
    build_payment_record_payload,
    finalize_successful_payment,
    first_value,
    lookup_payment_by_order_or_provider_id,
    notify_user_payment_failed,
    payment_units_for_activation,
)
from .config import (
    _FAILED_EVENT_TYPES,
    _FAILED_PAYMENT_INTENT_STATUSES,
    _SUCCESS_EVENT_TYPES,
    _SUCCESS_PAYMENT_INTENT_STATUSES,
    StripeConfig,
    _decode_saved_method,
    _encode_saved_method,
    _metadata_pairs,
    _stripe_amount_to_minor_units,
    _stripe_json_success,
)


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

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
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
        idempotency_key: str | None = None,
        log_prefix: str,
    ) -> tuple[bool, dict[str, Any]]:
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

    async def _get_json(self, endpoint: str, *, log_prefix: str) -> tuple[bool, dict[str, Any]]:
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
    ) -> tuple[bool, dict[str, Any]]:
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
        form: list[tuple[str, Any]] = [
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
    ) -> tuple[bool, dict[str, Any]]:
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
        form: list[tuple[str, Any]] = [
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

    async def retrieve_payment_intent(self, payment_intent_id: str) -> dict[str, Any] | None:
        payment_intent_id = str(payment_intent_id or "").strip()
        if not payment_intent_id or not self.configured:
            return None
        success, data = await self._get_json(
            f"/v1/payment_intents/{payment_intent_id}",
            log_prefix="Stripe retrieve_payment_intent",
        )
        return data if success else None

    async def retrieve_payment_method(self, payment_method_id: str) -> dict[str, Any] | None:
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

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        return str(getattr(payment, "provider_payment_url", None) or "").strip() or None

    def verify_signature(self, raw_body: bytes, header_value: str) -> bool:
        secret = self.webhook_secret
        if not secret:
            logging.error("Stripe webhook: no webhook secret configured.")
            return False
        timestamp: int | None = None
        signatures: list[str] = []
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
        fallback_customer_id: str | None = None,
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
            user_id=int(payment.user_id),
            provider_payment_method_id=_encode_saved_method(customer_id, payment_method_id),
            provider="stripe",
            card_last4=card_last4,
            card_network=card_network,
            set_default=True,
        )

    def _payment_db_id_from_object(self, obj: Mapping[str, Any]) -> str | None:
        metadata_raw = obj.get("metadata")
        metadata: Mapping[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
        payment_db_id = metadata.get("payment_db_id") or obj.get("client_reference_id")
        return str(payment_db_id).strip() if payment_db_id else None

    async def _payment_intent_for_success(
        self,
        event_type: str,
        obj: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any] | None, str | None, str | None]:
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
