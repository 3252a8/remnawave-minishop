import hashlib
import hmac
import json
import logging
import re
import time
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import SettingsConfigDict

from .base import (
    ProviderEnvConfig,
    normalize_payment_currency_code,
    parse_supported_currency_codes,
    provider_env_file,
)
from .shared import (
    format_decimal_amount,
)

PAYKILLA_DEFAULT_PAYMENT_CURRENCIES = "USDTTRC,BTC,ETH,USDTBSC,USDTTON"
PAYKILLA_DEFAULT_INVOICE_CURRENCIES = "USD,EUR"
PAYKILLA_DEFAULT_EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/{source}"
PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT = 10.0
PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY = "USD"
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
_SYNC_EXCHANGE_RATE_CACHE: Dict[tuple[str, str, str], tuple[float, Decimal]] = {}


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
    MIN_PAYMENT_AMOUNT: float = Field(default=PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT)
    MIN_PAYMENT_CURRENCY: str = Field(default=PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY)
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

    @field_validator("MIN_PAYMENT_AMOUNT", mode="before")
    @classmethod
    def _normalize_min_payment_amount(cls, v):
        if isinstance(v, str):
            v = v.strip()
        try:
            value = Decimal(str(v))
        except (InvalidOperation, TypeError, ValueError):
            return PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT
        if not value.is_finite() or value < 0:
            return PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT
        return float(value)

    @field_validator("MIN_PAYMENT_CURRENCY", mode="before")
    @classmethod
    def _normalize_min_payment_currency(cls, v):
        return normalize_payment_currency_code(v, default=PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY)

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
    return currencies or list(parse_supported_currency_codes(PAYKILLA_DEFAULT_PAYMENT_CURRENCIES))


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


def _config_min_payment_amount(config: PaykillaConfig) -> Decimal:
    amount = _decimal_from_api(getattr(config, "MIN_PAYMENT_AMOUNT", None))
    if amount is None or amount < 0:
        return Decimal(str(PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT))
    return amount


def _config_min_payment_currency(config: PaykillaConfig) -> str:
    return normalize_payment_currency_code(
        getattr(config, "MIN_PAYMENT_CURRENCY", None),
        default=PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY,
    )


def _exchange_rate_url_for(
    config: PaykillaConfig,
    source_currency: str,
    target_currency: str,
) -> str:
    template = getattr(config, "EXCHANGE_RATE_URL", None) or PAYKILLA_DEFAULT_EXCHANGE_RATE_URL
    return template.format(source=source_currency, target=target_currency)


def _exchange_rate_sync(
    config: PaykillaConfig, source_currency: str, target_currency: str
) -> Optional[Decimal]:
    source_currency = normalize_payment_currency_code(source_currency)
    target_currency = normalize_payment_currency_code(target_currency)
    if source_currency == target_currency:
        return Decimal("1")

    url = _exchange_rate_url_for(config, source_currency, target_currency)
    cache_key = (url, source_currency, target_currency)
    cache_seconds = int(getattr(config, "EXCHANGE_RATE_CACHE_SECONDS", 3600) or 3600)
    now = time.time()
    cached = _SYNC_EXCHANGE_RATE_CACHE.get(cache_key)
    if cached and now - cached[0] < cache_seconds:
        return cached[1]

    try:
        with urlopen(url, timeout=5) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except Exception:
        logging.exception(
            "Paykilla exchange rate sync lookup failed (source=%s target=%s).",
            source_currency,
            target_currency,
        )
        return None

    if not isinstance(response_data, dict) or response_data.get("result") != "success":
        logging.warning(
            "Paykilla exchange rate sync lookup returned unexpected body: %s",
            response_data,
        )
        return None
    rates = response_data.get("rates")
    rate = _decimal_from_api(rates.get(target_currency) if isinstance(rates, dict) else None)
    if rate is None or rate <= 0:
        return None
    _SYNC_EXCHANGE_RATE_CACHE[cache_key] = (now, rate)
    return rate


def _min_payment_threshold_for_currency(
    config: PaykillaConfig, payment_currency: Any
) -> Optional[Decimal]:
    min_amount = _config_min_payment_amount(config)
    if min_amount <= 0:
        return None
    min_currency = _config_min_payment_currency(config)
    payment_currency = normalize_payment_currency_code(payment_currency)
    if payment_currency == min_currency:
        return format_decimal_amount(min_amount)
    rate = _exchange_rate_sync(config, payment_currency, min_currency)
    if rate is None or rate <= 0:
        return None
    return (min_amount / rate).quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def _paykilla_payment_minimum_metadata(
    config: PaykillaConfig, payment_currency: Any
) -> Optional[Dict[str, Any]]:
    payment_currency = normalize_payment_currency_code(payment_currency)
    threshold = _min_payment_threshold_for_currency(config, payment_currency)
    if threshold is None:
        return None
    return {
        "min_amount": str(threshold),
        "min_currency": payment_currency,
        "configured_min_amount": str(format_decimal_amount(_config_min_payment_amount(config))),
        "configured_min_currency": _config_min_payment_currency(config),
    }


def _paykilla_payment_amount_supported(
    config: PaykillaConfig,
    payment_currency: Any,
    amount: Any,
) -> bool:
    threshold = _min_payment_threshold_for_currency(config, payment_currency)
    if threshold is None:
        return True
    value = _decimal_from_api(amount)
    if value is None:
        return True
    return format_decimal_amount(value) >= threshold
