import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot
from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.utils.request_security import ip_in_allowlist, request_client_ip
from config.settings import Settings
from db.dal import payment_dal

from ..base import (
    normalize_payment_currency_code,
    parse_supported_currency_codes,
    provider_runtime_enabled,
)
from ..shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
    HttpClientMixin,
    PaymentSuccessRequest,
    decimal_amounts_equal,
    finalize_successful_payment,
    first_value,
    format_decimal_amount,
    lookup_payment_by_order_or_provider_id,
    notify_user_payment_failed,
    payment_units_for_activation,
)
from .config import (
    _FAILED_EVENTS,
    _SUCCESS_EVENTS,
    PaykillaConfig,
    _config_min_payment_amount,
    _config_min_payment_currency,
    _debug_invoice_body,
    _decimal_from_api,
    _exchange_rate_url_for,
    _invoice_text,
    _invoice_type_for,
    _payment_currencies,
    _response_invoice_data,
    _sign_query,
    _signature_preview,
    _target_invoice_currency,
    _webhook_signature,
)


class PaykillaService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: PaykillaConfig,
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
        self._exchange_rate_cache: Dict[tuple[str, str], tuple[float, Decimal]] = {}
        self._currency_cache: tuple[float, List[Dict[str, Any]]] = (0, [])

        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)
        if not self.configured:
            logging.warning(
                "PaykillaService initialized but not fully configured. Payments disabled."
            )

    @property
    def configured(self) -> bool:
        return bool(provider_runtime_enabled(self.config) and self.api_key and self.secret_key)

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://account-api.paykilla.com").rstrip("/")

    @property
    def widget_url(self) -> str:
        return (self.config.WIDGET_URL or "https://gopay.paykilla.com").rstrip("/")

    @property
    def api_key(self) -> str:
        return (self.config.API_KEY or "").strip()

    @property
    def secret_key(self) -> str:
        return (self.config.SECRET_KEY or "").strip()

    @property
    def currency(self) -> str:
        return normalize_payment_currency_code(self.config.CURRENCY or "USD")

    @property
    def verify_webhook_signature(self) -> bool:
        return self.config.VERIFY_WEBHOOK_SIGNATURE

    def _signed_invoice_url(self) -> str:
        timestamp_ms = int(time.time() * 1000)
        recv_window_ms = int(self.config.RECV_WINDOW_MS)
        query, signature = _sign_query(timestamp_ms, recv_window_ms, self.secret_key)
        return f"{self.base_url}/api/v2/invoice?{query}&signature={signature}"

    def _signed_invoice_details_url(self, invoice_id: str) -> str:
        timestamp_ms = int(time.time() * 1000)
        recv_window_ms = int(self.config.RECV_WINDOW_MS)
        query, signature = _sign_query(timestamp_ms, recv_window_ms, self.secret_key)
        return f"{self.base_url}/api/v2/invoice/{invoice_id}?{query}&signature={signature}"

    def _signed_currency_url(self) -> str:
        timestamp_ms = int(time.time() * 1000)
        recv_window_ms = int(self.config.RECV_WINDOW_MS)
        query, signature = _sign_query(timestamp_ms, recv_window_ms, self.secret_key)
        return f"{self.base_url}/api/v2/currency?{query}&signature={signature}"

    def _exchange_rate_url(self, source_currency: str, target_currency: str) -> str:
        return _exchange_rate_url_for(self.config, source_currency, target_currency)

    async def _exchange_rate(self, source_currency: str, target_currency: str) -> Decimal:
        source_currency = normalize_payment_currency_code(source_currency)
        target_currency = normalize_payment_currency_code(target_currency)
        if source_currency == target_currency:
            return Decimal("1")

        cache_key = (source_currency, target_currency)
        cache_seconds = int(self.config.EXCHANGE_RATE_CACHE_SECONDS)
        now = time.time()
        cache = self._exchange_rate_cache
        cached = cache.get(cache_key)
        if cached and now - cached[0] < cache_seconds:
            return cached[1]

        session = await self._get_session()
        url = self._exchange_rate_url(source_currency, target_currency)
        async with session.get(url) as response:
            response_text = await response.text()
            try:
                response_data = json.loads(response_text) if response_text else {}
            except json.JSONDecodeError as exc:
                raise ValueError("exchange_rate_invalid_json") from exc
            if response.status != 200 or response_data.get("result") != "success":
                logging.error(
                    "Paykilla exchange rate request failed "
                    "(status=%s, body=%s, source=%s, target=%s)",
                    response.status,
                    response_data,
                    source_currency,
                    target_currency,
                )
                raise ValueError("exchange_rate_unavailable")
            rates = response_data.get("rates") if isinstance(response_data, dict) else None
            target_rate = rates.get(target_currency) if isinstance(rates, dict) else None
            rate = _decimal_from_api(target_rate)
            if rate is None or rate <= 0:
                raise ValueError("exchange_rate_missing")

        cache[cache_key] = (now, rate)
        return rate

    async def _paykilla_currencies(self) -> List[Dict[str, Any]]:
        cache_seconds = int(self.config.EXCHANGE_RATE_CACHE_SECONDS)
        now = time.time()
        cached_at, cached_data = getattr(self, "_currency_cache", (0, []))
        if cached_data and now - cached_at < cache_seconds:
            return cached_data

        headers = {"X-API-KEY": self.api_key}
        session = await self._get_session()
        try:
            async with session.get(self._signed_currency_url(), headers=headers) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else []
                except json.JSONDecodeError:
                    logging.warning(
                        "Paykilla currency metadata request returned invalid JSON: %s",
                        response_text,
                    )
                    return cached_data
                if response.status != 200 or not isinstance(response_data, list):
                    logging.warning(
                        "Paykilla currency metadata request failed (status=%s, body=%s)",
                        response.status,
                        response_data,
                    )
                    return cached_data
        except Exception:
            logging.exception("Paykilla currency metadata request failed.")
            return cached_data

        self._currency_cache = (now, response_data)
        return response_data

    async def _currency_info_for(self, currency: str) -> Optional[Dict[str, Any]]:
        currency = normalize_payment_currency_code(currency)
        for item in await self._paykilla_currencies():
            if not isinstance(item, dict):
                continue
            if normalize_payment_currency_code(item.get("ticker"), default="") == currency:
                return item
        return None

    async def _invoice_amount_bounds_error(
        self, *, amount: Decimal, currency: str
    ) -> Optional[Dict[str, Any]]:
        info = await self._currency_info_for(currency)
        if not info:
            return None
        minimum = _decimal_from_api(info.get("invoiceMin"))
        maximum = _decimal_from_api(info.get("invoiceMax"))
        if minimum is not None and amount < minimum:
            return {
                "message": "invoice_amount_below_minimum",
                "currency": currency,
                "amount": str(amount),
                "minimum": str(format_decimal_amount(minimum)),
            }
        if maximum is not None and amount > maximum:
            return {
                "message": "invoice_amount_above_maximum",
                "currency": currency,
                "amount": str(amount),
                "maximum": str(format_decimal_amount(maximum)),
            }
        return None

    async def _invoice_amount_and_currency(
        self, *, amount: float, payment_currency: str
    ) -> tuple[Decimal, str]:
        payment_currency = normalize_payment_currency_code(payment_currency or self.currency)
        invoice_currency = _target_invoice_currency(self.config, payment_currency)
        invoice_amount = format_decimal_amount(amount)
        if invoice_currency == payment_currency:
            return invoice_amount, invoice_currency

        rate = await self._exchange_rate(payment_currency, invoice_currency)
        converted_amount = format_decimal_amount(invoice_amount * rate)
        logging.info(
            "Paykilla invoice currency conversion: payment=%s %s, invoice=%s %s, rate=%s",
            invoice_amount,
            payment_currency,
            converted_amount,
            invoice_currency,
            rate,
        )
        return converted_amount, invoice_currency

    async def _configured_minimum_error(
        self, *, amount: float, payment_currency: str
    ) -> Optional[Dict[str, Any]]:
        min_amount = _config_min_payment_amount(self.config)
        if min_amount <= 0:
            return None
        min_currency = _config_min_payment_currency(self.config)
        payment_currency = normalize_payment_currency_code(payment_currency)
        payment_amount = format_decimal_amount(amount)
        if payment_currency == min_currency:
            comparable_amount = payment_amount
        else:
            rate = await self._exchange_rate(payment_currency, min_currency)
            comparable_amount = format_decimal_amount(payment_amount * rate)
        if comparable_amount >= min_amount:
            return None
        return {
            "message": "payment_amount_below_minimum",
            "currency": payment_currency,
            "amount": str(payment_amount),
            "minimum": str(format_decimal_amount(min_amount)),
            "minimum_currency": min_currency,
            "converted_amount": str(comparable_amount),
        }

    def _invoice_body(
        self,
        *,
        payment_db_id: int,
        amount: Any,
        currency: Optional[str],
        description: str,
    ) -> Dict[str, Any]:
        currency_code = normalize_payment_currency_code(currency or self.currency)
        invoice_text = _invoice_text(getattr(self.settings, "WEBAPP_TITLE", None), payment_db_id)
        body: Dict[str, Any] = {
            "type": _invoice_type_for(self.config, currency_code),
            "purpose": invoice_text,
            "currency": currency_code,
            "totalPrice": str(format_decimal_amount(amount)),
            "paymentCurrencies": _payment_currencies(self.config),
            "clientOrderId": str(payment_db_id),
            "userPaysServiceFee": bool(self.config.USER_PAYS_SERVICE_FEE),
            "userPaysNetworkFee": bool(self.config.USER_PAYS_NETWORK_FEE),
            "description": invoice_text,
        }
        if self.config.LIFETIME_SECONDS:
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=int(self.config.LIFETIME_SECONDS)
            )
            body["expiredAt"] = expires_at.isoformat().replace("+00:00", "Z")
        return body

    async def create_payment_link(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: Optional[str],
        description: str,
        url_callback: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("PaykillaService is not configured. Cannot create payment link.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(currency or self.currency)
        supported = parse_supported_currency_codes(self.config.SUPPORTED_CURRENCIES)
        if supported and currency_code not in supported:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(supported),
            }

        try:
            minimum_error = await self._configured_minimum_error(
                amount=amount,
                payment_currency=currency_code,
            )
            if minimum_error:
                logging.error(
                    "Paykilla create_payment_link: payment amount below configured minimum "
                    "(details=%s)",
                    minimum_error,
                )
                return False, minimum_error
            invoice_amount, invoice_currency = await self._invoice_amount_and_currency(
                amount=amount,
                payment_currency=currency_code,
            )
        except Exception as exc:
            logging.exception(
                "Paykilla create_payment_link: failed to resolve invoice currency "
                "(amount=%s currency=%s target=%s).",
                amount,
                currency_code,
                _target_invoice_currency(self.config, currency_code),
            )
            return False, {"message": str(exc) or "exchange_rate_unavailable"}

        bounds_error = await self._invoice_amount_bounds_error(
            amount=invoice_amount,
            currency=invoice_currency,
        )
        if bounds_error:
            logging.error(
                "Paykilla create_payment_link: invoice amount violates PayKilla limits "
                "(details=%s, payment_amount=%s, payment_currency=%s)",
                bounds_error,
                format_decimal_amount(amount),
                currency_code,
            )
            return False, bounds_error

        body = self._invoice_body(
            payment_db_id=payment_db_id,
            amount=invoice_amount,
            currency=invoice_currency,
            description=description,
        )
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        try:
            async with session.post(
                self._signed_invoice_url(),
                json=body,
                headers=headers,
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("Paykilla create_payment_link: invalid JSON: %s", response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                invoice = _response_invoice_data(response_data)
                invoice_id = first_value(invoice, "id")
                if response.status not in {200, 201} or not invoice_id:
                    logging.error(
                        "Paykilla create_payment_link: API error "
                        "(status=%s, body=%s, request_body=%s)",
                        response.status,
                        response_data,
                        _debug_invoice_body(body),
                    )
                    return False, {"status": response.status, "message": response_data}
                invoice["payment_url"] = f"{self.widget_url}/{invoice_id}"
                return True, invoice
        except Exception as exc:
            logging.exception("Paykilla create_payment_link: request failed.")
            return False, {"message": str(exc)}

    async def get_invoice_details(self, invoice_id: str) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}

        invoice_id = str(invoice_id or "").strip()
        if not invoice_id:
            return False, {"message": "missing_invoice_id"}

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        try:
            async with session.get(
                self._signed_invoice_details_url(invoice_id),
                headers=headers,
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logging.error("Paykilla get_invoice_details: invalid JSON: %s", response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                invoice = _response_invoice_data(response_data)
                if response.status != 200 or not first_value(invoice, "id"):
                    logging.warning(
                        "Paykilla get_invoice_details failed: id=%s status=%s body=%s",
                        invoice_id,
                        response.status,
                        response_data,
                    )
                    return False, {"status": response.status, "message": response_data}
                return True, invoice
        except Exception as exc:
            logging.exception("Paykilla get_invoice_details request failed: id=%s", invoice_id)
            return False, {"message": str(exc)}

    async def try_reuse_pending_invoice(self, payment: Any) -> Optional[str]:
        invoice_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        if not invoice_id:
            return None

        success, data = await self.get_invoice_details(invoice_id)
        if not success:
            return None
        if str(first_value(data, "id") or "") != invoice_id:
            return None
        if str(data.get("clientOrderId") or "") != str(payment.payment_id):
            return None
        if str(data.get("status") or "").strip().upper() != "PROCESSING":
            return None
        return f"{self.widget_url}/{invoice_id}"

    def _webhook_url_for_request(self, request: web.Request) -> Optional[str]:
        configured = self.config.full_webhook_url(getattr(self.settings, "WEBHOOK_BASE_URL", None))
        if configured:
            return configured
        try:
            return f"{request.scheme}://{request.host}{request.path_qs}"
        except Exception:
            return None

    def _verify_webhook_signature(self, request: web.Request, raw_body: bytes) -> bool:
        timestamp = str(request.headers.get("X-API-TIMESTAMP") or "").strip()
        signature = str(request.headers.get("X-API-SIGN") or "").strip().lower()
        recv_window_raw = str(request.headers.get("X-API-RECV-WINDOW") or "5000").strip()
        api_key = str(request.headers.get("X-API-KEY") or "").strip()
        if not timestamp or not signature:
            return False
        if api_key and not hmac.compare_digest(api_key, self.api_key):
            logging.warning("Paykilla webhook: X-API-KEY does not match configured API key.")
            return False
        try:
            timestamp_ms = int(timestamp)
            recv_window_ms = int(recv_window_raw)
        except ValueError:
            return False
        now_ms = int(time.time() * 1000)
        if abs(now_ms - timestamp_ms) > max(recv_window_ms, 1000):
            logging.warning(
                "Paykilla webhook: timestamp outside recv window "
                "(timestamp=%s now=%s recvWindow=%s).",
                timestamp_ms,
                now_ms,
                recv_window_ms,
            )
            return False
        webhook_url = self._webhook_url_for_request(request)
        if not webhook_url:
            logging.warning("Paykilla webhook: cannot resolve webhook URL for signature.")
            return False
        expected = _webhook_signature(
            timestamp=timestamp,
            method=request.method or "POST",
            url=webhook_url,
            raw_body=raw_body,
            secret_key=self.secret_key,
        )
        if hmac.compare_digest(expected, signature):
            return True
        logging.warning(
            "Paykilla webhook: invalid signature (received=%s expected=%s url=%s).",
            _signature_preview(signature),
            _signature_preview(expected),
            webhook_url,
        )
        return False

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="paykilla_disabled")

        client_ip = request_client_ip(request, trusted_proxies=self.settings.trusted_proxies)
        trusted = self.config.trusted_ips_list
        if trusted and not ip_in_allowlist(client_ip, trusted):
            logging.warning(
                "Paykilla webhook denied from unauthorized IP source "
                "(client_ip=%s remote=%s x_forwarded_for=%s trusted_ip_count=%d).",
                client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
                len(trusted),
            )
            return web.Response(status=403, text="forbidden")

        raw_body = await request.read()
        if self.verify_webhook_signature and not self._verify_webhook_signature(
            request,
            raw_body,
        ):
            return web.Response(status=403, text="invalid_signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            logging.exception("Paykilla webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad_request")

        event_type = str(payload.get("eventType") or "").strip().upper()
        data = payload.get("data")
        if not event_type or not isinstance(data, dict):
            logging.error("Paykilla webhook: missing event envelope fields: %s", payload)
            return web.Response(status=400, text="missing_fields")

        if event_type not in _SUCCESS_EVENTS and event_type not in _FAILED_EVENTS:
            logging.info("Paykilla webhook: intermediate event '%s' ignored.", event_type)
            return web.Response(text="status_ignored")

        data_type = str(data.get("type") or "").strip().upper()
        if data_type and data_type != "INVOICE":
            logging.info(
                "Paykilla webhook: non-invoice event '%s' ignored (type=%s).",
                event_type,
                data_type,
            )
            return web.Response(text="status_ignored")

        invoice_id = str(data.get("id") or "").strip()
        client_order_id = data.get("clientOrderId")
        amount_raw = data.get("amount") or data.get("expectedAmount")
        invoice_currency = normalize_payment_currency_code(data.get("currency") or self.currency)

        if not (invoice_id or client_order_id):
            logging.error("Paykilla webhook: missing invoice ids: %s", payload)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=client_order_id,
                provider_payment_id=invoice_id or None,
            )
            if not payment:
                logging.error(
                    "Paykilla webhook: payment not found (clientOrderId=%s, invoice_id=%s)",
                    client_order_id,
                    invoice_id,
                )
                return web.Response(status=404, text="payment_not_found")

            if payment.status == "succeeded" and event_type in _SUCCESS_EVENTS:
                return web.Response(text="ok")

            resolved_id = invoice_id or str(payment.payment_id)

            if event_type in _SUCCESS_EVENTS:
                payment_currency = normalize_payment_currency_code(payment.currency)
                if amount_raw is not None and invoice_currency == payment_currency:
                    try:
                        if not decimal_amounts_equal(amount_raw, payment.amount):
                            logging.warning(
                                "Paykilla webhook: amount mismatch for payment %s "
                                "(expected %s, got %s)",
                                payment.payment_id,
                                format_decimal_amount(payment.amount),
                                format_decimal_amount(amount_raw),
                            )
                    except Exception as exc:
                        logging.warning(
                            "Paykilla webhook: failed to compare amounts for %s: %s",
                            payment.payment_id,
                            exc,
                        )
                elif amount_raw is not None:
                    logging.info(
                        "Paykilla webhook: invoice amount is in %s while payment record is in %s; "
                        "skipping direct amount comparison for payment %s.",
                        invoice_currency,
                        payment_currency,
                        payment.payment_id,
                    )

                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_id,
                        PAYMENT_STATUS_PENDING_FINALIZATION,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Paykilla webhook: failed to mark payment %s as succeeded.",
                        resolved_id,
                    )
                    return web.Response(status=500, text="processing_error")

                sale_mode = payment.sale_mode or (
                    "traffic" if self.settings.traffic_sale_mode else "subscription"
                )
                payment_units = payment_units_for_activation(payment, sale_mode)

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
                        currency=str(payment.currency),
                        sale_mode=sale_mode,
                        months=payment_units,
                        traffic_amount=float(payment_units),
                        provider_subscription="paykilla",
                        provider_notification="paykilla",
                        db_user=payment.user,
                        log_prefix="Paykilla webhook",
                    )
                )
                if outcome is None:
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if event_type in _FAILED_EVENTS:
                try:
                    await payment_dal.update_provider_payment_and_status(
                        session,
                        payment.payment_id,
                        resolved_id,
                        "failed",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logging.exception(
                        "Paykilla webhook: failed to mark payment %s as failed.",
                        resolved_id,
                    )
                    return web.Response(status=500, text="processing_error")
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.Response(text="ok")
        return web.Response(text="status_ignored")
