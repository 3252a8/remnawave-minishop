import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.utils.request_security import ip_in_allowlist, request_client_ip
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal

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
    HttpClientMixin,
    PaymentSuccessRequest,
    build_payment_record_payload,
    create_webapp_payment_record,
    decimal_amounts_equal,
    describe_payment,
    finalize_successful_payment,
    finalize_webapp_link_payment,
    first_value,
    format_decimal_amount,
    lookup_payment_by_order_or_provider_id,
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    notify_user_payment_failed,
    parse_payment_callback,
    payment_failed,
    payment_unavailable,
    payment_units_for_activation,
    quote_hwid_callback_parts,
    render_link_or_fail,
)

router = Router(name="user_subscription_payments_paykilla_router")
_LOG = "paykilla"

PAYKILLA_DEFAULT_PAYMENT_CURRENCIES = "USDTTRC"
PAYKILLA_DEFAULT_INVOICE_CURRENCIES = "USD,EUR"
PAYKILLA_DEFAULT_EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/{source}"
PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES = (
    "RUB,USD,EUR,AED,GBP,BTC,ETH,TRX,TON,USDTTRC,USDTETH,USDTBSC,"
    "USDCETH,USDCBSC,DAIETH,DAIBSC,BNBBSC,ETHBSC,LINKETH,LINKBSC,"
    "USDTTON,AAVEETH,MANAETH,SHIBETH"
)
_FIAT_CURRENCIES = {"RUB", "USD", "EUR", "AED", "GBP"}
_SUCCESS_EVENTS = {"INVOICE_PAID", "PAYMENT_COMPLETED", "PAYMENT_OVERPAID"}
_FAILED_EVENTS = {
    "PAYMENT_FAILED",
    "PAYMENT_UNDERPAID",
    "INVOICE_EXPIRED",
    "INVOICE_CANCELLED",
    "PAYMENT_CANCELLED",
    "COMPLIANCE_FAILED",
}
_CYRILLIC_TO_LATIN = str.maketrans(
    {
        "А": "A",
        "Б": "B",
        "В": "V",
        "Г": "G",
        "Д": "D",
        "Е": "E",
        "Ё": "E",
        "Ж": "Zh",
        "З": "Z",
        "И": "I",
        "Й": "Y",
        "К": "K",
        "Л": "L",
        "М": "M",
        "Н": "N",
        "О": "O",
        "П": "P",
        "Р": "R",
        "С": "S",
        "Т": "T",
        "У": "U",
        "Ф": "F",
        "Х": "H",
        "Ц": "Ts",
        "Ч": "Ch",
        "Ш": "Sh",
        "Щ": "Sch",
        "Ъ": "",
        "Ы": "Y",
        "Ь": "",
        "Э": "E",
        "Ю": "Yu",
        "Я": "Ya",
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


class PaykillaConfig(ProviderEnvConfig):
    """PayKilla V2 env vars."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYKILLA_",
        extra="ignore",
        populate_by_name=True,
    )

    ENABLED: bool = Field(default=False)
    API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("PAYKILLA_API_KEY", "PAYKILLA_V2_API_KEY"),
    )
    SECRET_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("PAYKILLA_SECRET_KEY", "PAYKILLA_V2_SECRET_KEY"),
    )
    BASE_URL: str = Field(
        default="https://account-api.paykilla.com",
        validation_alias=AliasChoices("PAYKILLA_BASE_URL", "PAYKILLA_V2_BASE_URL"),
    )
    WIDGET_URL: str = Field(default="https://gopay.paykilla.com")
    CURRENCY: str = Field(default="USD")
    INVOICE_CURRENCIES: str = Field(default=PAYKILLA_DEFAULT_INVOICE_CURRENCIES)
    INVOICE_TYPE: Optional[str] = None
    PAYMENT_CURRENCIES: str = Field(default=PAYKILLA_DEFAULT_PAYMENT_CURRENCIES)
    SUPPORTED_CURRENCIES: str = Field(default=PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES)
    LIFETIME_SECONDS: int = Field(default=3600)
    RECV_WINDOW_MS: int = Field(default=5000)
    USER_PAYS_SERVICE_FEE: bool = Field(default=True)
    USER_PAYS_NETWORK_FEE: bool = Field(default=True)
    EXCHANGE_RATE_URL: str = Field(default=PAYKILLA_DEFAULT_EXCHANGE_RATE_URL)
    EXCHANGE_RATE_CACHE_SECONDS: int = Field(default=3600)
    VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    WEBHOOK_URL: Optional[str] = None
    TRUSTED_IPS: str = Field(default="")

    @field_validator("LIFETIME_SECONDS", mode="before")
    @classmethod
    def _clamp_lifetime(cls, v):
        if isinstance(v, str):
            v = v.strip()
        try:
            value = int(v)
        except (TypeError, ValueError):
            return 3600
        return min(2_592_000, max(300, value))

    @field_validator("RECV_WINDOW_MS", mode="before")
    @classmethod
    def _clamp_recv_window(cls, v):
        if isinstance(v, str):
            v = v.strip()
        try:
            value = int(v)
        except (TypeError, ValueError):
            return 5000
        return min(60_000, max(1000, value))

    @field_validator("EXCHANGE_RATE_CACHE_SECONDS", mode="before")
    @classmethod
    def _clamp_exchange_rate_cache(cls, v):
        if isinstance(v, str):
            v = v.strip()
        try:
            value = int(v)
        except (TypeError, ValueError):
            return 3600
        return min(86_400, max(60, value))

    @field_validator(
        "API_KEY",
        "SECRET_KEY",
        "INVOICE_TYPE",
        "WEBHOOK_URL",
        mode="before",
    )
    @classmethod
    def _strip_optional(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("INVOICE_TYPE", mode="before")
    @classmethod
    def _normalize_invoice_type(cls, v):
        if isinstance(v, str):
            value = v.strip().upper()
            return value or None
        return v

    @property
    def webhook_path(self) -> str:
        return "/webhook/paykilla"

    def full_webhook_url(self, base: Optional[str]) -> Optional[str]:
        if self.WEBHOOK_URL:
            return self.WEBHOOK_URL.rstrip("/")
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"

    @property
    def trusted_ips_list(self) -> List[str]:
        return [item.strip() for item in (self.TRUSTED_IPS or "").split(",") if item.strip()]


class PaykillaPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for PayKilla."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_PAYKILLA_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


def _normalize_paykilla_text(value: Any) -> str:
    text = str(value or "")
    text = text.translate(_CYRILLIC_TO_LATIN)
    text = re.sub(r"[-\u2010-\u2015]", " ", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9_\s.,]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_paykilla_text(value: Any, *, fallback: str, max_length: int = 255) -> str:
    text = _normalize_paykilla_text(value)
    fallback_text = _normalize_paykilla_text(fallback) or "Payment"
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = fallback_text
    return text[:max_length].strip() or fallback_text[:max_length].strip() or "Payment"


def _invoice_text(title: Any, payment_db_id: int) -> str:
    project_title = _clean_paykilla_text(title, fallback="Minishop")
    return _clean_paykilla_text(
        f"{project_title} payment {payment_db_id}",
        fallback=f"Payment {payment_db_id}",
    )


def _payment_currencies(config: PaykillaConfig) -> List[str]:
    currencies = list(parse_supported_currency_codes(config.PAYMENT_CURRENCIES))
    return currencies or ["USDTTRC"]


def _invoice_currencies(config: PaykillaConfig) -> tuple[str, ...]:
    currencies = parse_supported_currency_codes(config.INVOICE_CURRENCIES)
    return currencies or parse_supported_currency_codes(PAYKILLA_DEFAULT_INVOICE_CURRENCIES)


def _target_invoice_currency(config: PaykillaConfig, payment_currency: str) -> str:
    payment_currency = normalize_payment_currency_code(payment_currency)
    invoice_currencies = _invoice_currencies(config)
    if payment_currency in invoice_currencies:
        return payment_currency
    fallback = normalize_payment_currency_code(config.CURRENCY, default="")
    if fallback and fallback in invoice_currencies:
        return fallback
    return invoice_currencies[0] if invoice_currencies else payment_currency


def _invoice_type_for(config: PaykillaConfig, currency: str) -> str:
    explicit = (config.INVOICE_TYPE or "").strip().upper()
    if explicit in {"FIAT_BASED", "FIXED_AMOUNT", "OPEN_AMOUNT"}:
        return explicit
    return "FIAT_BASED" if currency in _FIAT_CURRENCIES else "FIXED_AMOUNT"


def _sign_query(timestamp_ms: int, recv_window_ms: int, secret_key: str) -> Tuple[str, str]:
    query = urlencode(
        [
            ("timestamp", str(timestamp_ms)),
            ("recvWindow", str(recv_window_ms)),
        ]
    )
    signature = hmac.new(secret_key.encode("utf-8"), query.encode("utf-8"), hashlib.sha256)
    return query, signature.hexdigest()


def _webhook_signature(
    *,
    timestamp: str,
    method: str,
    url: str,
    raw_body: bytes,
    secret_key: str,
) -> str:
    message = f"{timestamp}{method.upper()}{url}".encode("utf-8") + raw_body
    return hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _signature_preview(signature: str) -> str:
    signature = str(signature or "")
    if len(signature) <= 12:
        return signature
    return f"{signature[:6]}...{signature[-6:]}"


def _response_invoice_data(response_data: Dict[str, Any]) -> Dict[str, Any]:
    data = response_data.get("data") if isinstance(response_data, dict) else None
    if isinstance(data, dict) and data.get("id"):
        return data
    return response_data if isinstance(response_data, dict) else {}


def _debug_invoice_body(body: Dict[str, Any]) -> str:
    return json.dumps(body, ensure_ascii=True, sort_keys=True)


def _decimal_from_api(value: Any) -> Optional[Decimal]:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


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

        self._init_http_client(total_timeout=20)
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

    def _signed_currency_url(self) -> str:
        timestamp_ms = int(time.time() * 1000)
        recv_window_ms = int(self.config.RECV_WINDOW_MS)
        query, signature = _sign_query(timestamp_ms, recv_window_ms, self.secret_key)
        return f"{self.base_url}/api/v2/currency?{query}&signature={signature}"

    def _exchange_rate_url(self, source_currency: str, target_currency: str) -> str:
        template = self.config.EXCHANGE_RATE_URL or PAYKILLA_DEFAULT_EXCHANGE_RATE_URL
        return template.format(source=source_currency, target=target_currency)

    async def _exchange_rate(self, source_currency: str, target_currency: str) -> Decimal:
        source_currency = normalize_payment_currency_code(source_currency)
        target_currency = normalize_payment_currency_code(target_currency)
        if source_currency == target_currency:
            return Decimal("1")

        cache_key = (source_currency, target_currency)
        cache_seconds = int(self.config.EXCHANGE_RATE_CACHE_SECONDS)
        now = time.time()
        cache = getattr(self, "_exchange_rate_cache", None)
        if cache is None:
            cache = {}
            self._exchange_rate_cache = cache
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
                        "Paykilla currency metadata request failed "
                        "(status=%s, body=%s)",
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
                "(client_ip=%s remote=%s x_forwarded_for=%s trusted_ips=%s trusted_proxies=%s).",
                client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
                trusted,
                self.settings.trusted_proxies,
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
                        "succeeded",
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


@router.callback_query(F.data.startswith("pay_paykilla:"))
async def pay_paykilla_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    paykilla_service: PaykillaService,
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

    if not paykilla_service or not paykilla_service.configured:
        logging.error("Paykilla service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_paykilla data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=paykilla_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = default_payment_currency_code_for_settings(settings)
    payment_description = describe_payment(translator, parts)
    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_paykilla",
        description=payment_description,
        months=parts.months,
        provider="paykilla",
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "Paykilla: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    success, response_data = await paykilla_service.create_payment_link(
        payment_db_id=payment_record.payment_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        url_callback=paykilla_service.config.full_webhook_url(settings.WEBHOOK_BASE_URL),
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
        payment_url=first_value(response_data, "payment_url"),
        provider_payment_id=first_value(response_data, "id"),
        log_prefix=_LOG,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = ctx.request.app["settings"]
    service: PaykillaService = ctx.request.app["paykilla_service"]
    if not service or not service.configured:
        return payment_unavailable()

    currency = ctx.currency or default_payment_currency_code_for_settings(settings)
    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_paykilla",
            provider="paykilla",
        )
        success, response_data = await service.create_payment_link(
            payment_db_id=payment.payment_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
            url_callback=service.config.full_webhook_url(settings.WEBHOOK_BASE_URL),
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Paykilla WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(response_data, "payment_url") if success else None,
        provider_payment_id=first_value(response_data, "id"),
        log_prefix="Paykilla",
    )


async def paykilla_webhook_route(request: web.Request) -> web.Response:
    service: PaykillaService = request.app["paykilla_service"]
    return await service.webhook_route(request)


def create_service(ctx: ServiceFactoryContext) -> PaykillaService:
    bundle = ctx.config_for("paykilla_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, PaykillaConfig) else PaykillaConfig()
    )
    return PaykillaService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="PayKilla",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_PAYKILLA_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_PAYKILLA_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_PAYKILLA_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Bitcoin",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_PAYKILLA_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_PAYKILLA_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_PAYKILLA_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "",
            "TELEGRAM_EMOJI",
        ),
    )
)


_CONFIG_MANIFEST = (
    ProviderManifestField(
        "PAYKILLA_ENABLED", "bool", "Enabled", subsection="PayKilla", attr="ENABLED"
    ),
    ProviderManifestField(
        "PAYKILLA_API_KEY",
        "string",
        "API key",
        description="PayKilla public HMAC key with INVOICE permission.",
        subsection="PayKilla",
        secret=True,
        attr="API_KEY",
    ),
    ProviderManifestField(
        "PAYKILLA_SECRET_KEY",
        "string",
        "Secret key",
        description="PayKilla HMAC secret key. Never expose it client-side.",
        subsection="PayKilla",
        secret=True,
        attr="SECRET_KEY",
    ),
    ProviderManifestField(
        "PAYKILLA_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://account-api.paykilla.com",
        subsection="PayKilla",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "PAYKILLA_WIDGET_URL",
        "url",
        "Widget URL",
        placeholder="https://gopay.paykilla.com",
        subsection="PayKilla",
        attr="WIDGET_URL",
    ),
    ProviderManifestField(
        "PAYKILLA_CURRENCY",
        "string",
        "Fallback invoice currency",
        description=(
            "Currency used for PayKilla invoice creation when the tariff currency is not "
            "accepted by PayKilla as an invoice currency. Default: USD."
        ),
        placeholder="USD",
        subsection="PayKilla",
        attr="CURRENCY",
    ),
    ProviderManifestField(
        "PAYKILLA_INVOICE_CURRENCIES",
        "string",
        "PayKilla invoice currencies",
        description=(
            "Comma-separated currencies accepted by PayKilla as invoice currency. "
            "Payments in other tariff currencies are converted to PAYKILLA_CURRENCY."
        ),
        placeholder=PAYKILLA_DEFAULT_INVOICE_CURRENCIES,
        subsection="PayKilla",
        attr="INVOICE_CURRENCIES",
    ),
    ProviderManifestField(
        "PAYKILLA_SUPPORTED_CURRENCIES",
        "string",
        "Supported tariff currencies",
        description=(
            "Comma-separated tariff/payment currencies that may use PayKilla. "
            "Unsupported PayKilla invoice currencies are converted before invoice creation."
        ),
        placeholder=PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES,
        subsection="PayKilla",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "PAYKILLA_PAYMENT_CURRENCIES",
        "string",
        "Accepted crypto tickers",
        description=(
            "Comma-separated PayKilla tickers sent as paymentCurrencies, e.g. USDTTRC. "
            "Add BTC/ETH only when enabled for the merchant account."
        ),
        placeholder=PAYKILLA_DEFAULT_PAYMENT_CURRENCIES,
        subsection="PayKilla",
        attr="PAYMENT_CURRENCIES",
    ),
    ProviderManifestField(
        "PAYKILLA_INVOICE_TYPE",
        "string",
        "Invoice type",
        description="Optional override: FIAT_BASED, FIXED_AMOUNT, or OPEN_AMOUNT.",
        subsection="PayKilla",
        attr="INVOICE_TYPE",
        choices=(
            ("", "Auto"),
            ("FIAT_BASED", "FIAT_BASED"),
            ("FIXED_AMOUNT", "FIXED_AMOUNT"),
            ("OPEN_AMOUNT", "OPEN_AMOUNT"),
        ),
    ),
    ProviderManifestField(
        "PAYKILLA_LIFETIME_SECONDS",
        "int",
        "Invoice lifetime (seconds)",
        description="Used to send expiredAt to PayKilla.",
        subsection="PayKilla",
        min=300,
        max=2_592_000,
        attr="LIFETIME_SECONDS",
    ),
    ProviderManifestField(
        "PAYKILLA_RECV_WINDOW_MS",
        "int",
        "Request recvWindow (ms)",
        description="Validity window for signed PayKilla API requests.",
        subsection="PayKilla",
        min=1000,
        max=60_000,
        attr="RECV_WINDOW_MS",
    ),
    ProviderManifestField(
        "PAYKILLA_USER_PAYS_SERVICE_FEE",
        "bool",
        "User pays service fee",
        subsection="PayKilla",
        attr="USER_PAYS_SERVICE_FEE",
    ),
    ProviderManifestField(
        "PAYKILLA_USER_PAYS_NETWORK_FEE",
        "bool",
        "User pays network fee",
        subsection="PayKilla",
        attr="USER_PAYS_NETWORK_FEE",
    ),
    ProviderManifestField(
        "PAYKILLA_EXCHANGE_RATE_URL",
        "url",
        "Exchange rate URL",
        description=(
            "No-key exchange rate endpoint used when tariff currency must be converted. "
            "Supports {source} and {target} placeholders."
        ),
        placeholder=PAYKILLA_DEFAULT_EXCHANGE_RATE_URL,
        subsection="PayKilla",
        attr="EXCHANGE_RATE_URL",
    ),
    ProviderManifestField(
        "PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS",
        "int",
        "Exchange rate cache (seconds)",
        description="How long PayKilla currency conversion rates and PayKilla limits are cached.",
        subsection="PayKilla",
        min=60,
        max=86_400,
        attr="EXCHANGE_RATE_CACHE_SECONDS",
    ),
    ProviderManifestField(
        "PAYKILLA_VERIFY_WEBHOOK_SIGNATURE",
        "bool",
        "Verify webhook signature",
        subsection="PayKilla",
        attr="VERIFY_WEBHOOK_SIGNATURE",
    ),
    ProviderManifestField(
        "PAYKILLA_WEBHOOK_URL",
        "url",
        "Exact webhook URL",
        description=(
            "Optional override for signature verification. Leave empty to use "
            "WEBHOOK_BASE_URL + /webhook/paykilla."
        ),
        subsection="PayKilla",
        attr="WEBHOOK_URL",
    ),
    ProviderManifestField(
        "PAYKILLA_TRUSTED_IPS",
        "string",
        "Trusted IPs",
        description="Optional comma-separated IP addresses accepted for PayKilla webhooks.",
        subsection="PayKilla",
        attr="TRUSTED_IPS",
    ),
)


SPEC = PaymentProviderSpec(
    id="paykilla",
    provider_key="paykilla",
    label="PayKilla",
    webapp_label="PayKilla",
    webapp_labels={"ru": "PayKilla", "en": "PayKilla"},
    webapp_icon="Bitcoin",
    telegram_labels={"ru": "PayKilla", "en": "PayKilla"},
    telegram_emoji="",
    pending_status="pending_paykilla",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="paykilla_service",
    callback_prefix="pay_paykilla",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/paykilla",
    webhook_route=paykilla_webhook_route,
    create_webapp_payment=create_webapp_payment,
    emoji="",
    config_class=PaykillaConfig,
    presentation_class=PaykillaPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies_resolver=lambda config: getattr(
        config, "SUPPORTED_CURRENCIES", PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES
    ),
    currency_support_note=(
        "PayKilla invoice currency and paymentCurrencies availability can depend on "
        "merchant account settings."
    ),
    currency_support_url="https://paykilla.gitbook.io/paykilla-docs/api-integration/supported-currencies",
)
