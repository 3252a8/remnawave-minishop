"""Create and settle RivaraPay hosted payment intents."""

import hmac
import json
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from aiohttp import ClientError, web
from yarl import URL

from db.models import Payment

from ..base import ServiceFactoryContext, normalize_payment_currency_code
from ..shared import CreatePaymentRequest, HttpClientMixin, post_json_request
from ..shared.common import payment_amount_and_currency_match
from ..shared.hosted_settlement import settle_hosted_payment
from .config import INTENTS_URL, RivaraPayConfig

logger = logging.getLogger(__name__)

PENDING_STATUS = "pending_rivarapay"
PROVIDER_KEYS = ("rivarapay_sbp", "rivarapay_crypto")
WEBHOOK_PATH = "/webhook/rivarapay"
_WEBHOOK_TOLERANCE_SECONDS = 300
_OPEN_STATUSES = frozenset({"CREATED", "PENDING", "PROCESSING"})


def checkout_url(data: dict[str, Any]) -> str | None:
    value = data.get("checkoutUrl")
    if not isinstance(value, str):
        return None
    try:
        url = URL(value)
        return value if url.scheme == "https" and url.host and url.user is None else None
    except ValueError:
        return None


def intent_id(data: dict[str, Any]) -> str | None:
    value = data.get("id")
    return value if isinstance(value, str) and value.startswith("pi_") else None


def _intent_matches(data: dict[str, Any], *, order_id: str, amount: Any, currency: str) -> bool:
    money = data.get("amount")
    if not isinstance(money, dict):
        return False
    minor = money.get("amount")
    if not isinstance(minor, str) or not minor.isascii() or not minor.isdecimal():
        return False
    return (
        data.get("livemode") is True
        and data.get("merchantOrderId") == order_id
        and payment_amount_and_currency_match(
            expected_amount=amount,
            expected_currency=currency,
            received_amount=Decimal(minor).scaleb(-2),
            received_currency=money.get("currency"),
        )
    )


def _valid_signature(secret: str, timestamp: str, signature: str, raw: bytes) -> bool:
    if not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp) > 12:
        return False
    if abs(int(time.time()) - int(timestamp)) > _WEBHOOK_TOLERANCE_SECONDS:
        return False
    expected = hmac.digest(secret.encode(), timestamp.encode() + b"." + raw, "sha256")
    return len(signature) == 64 and hmac.compare_digest(expected.hex().encode(), signature.encode())


class RivaraPayService(HttpClientMixin):
    def __init__(self, ctx: ServiceFactoryContext, config: RivaraPayConfig) -> None:
        self.bot = ctx.bot
        self.settings = ctx.settings
        self.config = config
        self.i18n = ctx.i18n
        self.async_session_factory = ctx.async_session_factory
        self.subscription_service = ctx.subscription_service
        self.referral_service = ctx.referral_service
        self._default_return_url = (
            f"https://t.me/{ctx.bot_username_for_default_return}"
            if ctx.bot_username_for_default_return
            else ""
        )
        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)

    @property
    def configured(self) -> bool:
        return (
            self.config.credentials_configured
            and bool(self.settings.WEBHOOK_BASE_URL)
            and (
                self.config.SBP_ENABLED
                or self.config.SBP_ADMIN_ONLY_ENABLED
                or self.config.CRYPTO_ENABLED
                or self.config.CRYPTO_ADMIN_ONLY_ENABLED
            )
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.config.API_KEY}

    async def create_payment(
        self, request: CreatePaymentRequest, method: str
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}
        if normalize_payment_currency_code(request.currency, default="") != "RUB":
            return False, {"message": "unsupported_currency"}
        try:
            amount = Decimal(str(request.amount))
            minor = amount.scaleb(2)
            if not minor.is_finite() or minor <= 0 or minor != minor.to_integral_value():
                return False, {"message": "invalid_amount"}
        except InvalidOperation:
            return False, {"message": "invalid_amount"}

        order_id = str(request.payment.payment_id)
        body: dict[str, Any] = {
            "amount": format(minor, ".0f"),
            "currency": "RUB",
            "merchantOrderId": order_id,
            "customerEmail": f"{request.user_id}@telegram.org",
            "description": request.description[:500],
            "allowedMethods": [method],
        }
        if return_url := self.config.RETURN_URL or self._default_return_url:
            body["returnUrl"] = return_url
        return await post_json_request(
            await self._get_session(),
            INTENTS_URL,
            body=body,
            headers={**self._headers, "Idempotency-Key": str(uuid4())},
            log_prefix="RivaraPay create payment",
            is_success=lambda status, data: (
                status in {200, 201}
                and isinstance(data, dict)
                and bool(intent_id(data) and checkout_url(data))
                and _intent_matches(data, order_id=order_id, amount=amount, currency="RUB")
            ),
        )

    async def try_reuse_pending_payment(self, payment: Payment) -> str | None:
        provider_id = payment.provider_payment_id
        if not provider_id or not payment.provider_payment_url:
            return None
        try:
            session = await self._get_session()
            async with session.get(
                f"{INTENTS_URL}/{quote(provider_id, safe='')}", headers=self._headers
            ) as response:
                if response.status != 200:
                    return None
                data = await response.json()
        except (ClientError, TimeoutError, ValueError):
            logger.warning("RivaraPay: could not refresh payment intent")
            return None
        if (
            isinstance(data, dict)
            and intent_id(data) == provider_id
            and isinstance(status := data.get("status"), str)
            and status in _OPEN_STATUSES
            and _intent_matches(
                data,
                order_id=str(payment.payment_id),
                amount=payment.amount,
                currency=payment.currency,
            )
        ):
            return payment.provider_payment_url
        return None

    async def webhook_route(self, request: web.Request) -> web.Response:
        # Keep accepting already-issued intents if the checkout buttons are disabled.
        if not self.config.credentials_configured:
            return web.Response(status=503)
        raw = await request.read()
        if not _valid_signature(
            self.config.WEBHOOK_SECRET,
            request.headers.get("X-Timestamp", ""),
            request.headers.get("X-Signature", ""),
            raw,
        ):
            return web.Response(status=400)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return web.Response(status=400)
        if not isinstance(data, dict):
            return web.Response(status=400)
        # An expired intent can still be paid. The finalization claim deduplicates
        # paid deliveries atomically with fulfillment, including concurrent retries.
        if data.get("event_type") != "payment.paid" or data.get("test") is True:
            return web.Response(text="ok")
        provider_id = data.get("payment_id")
        order_id = data.get("order_id")
        if (
            data.get("status") != "paid"
            or data.get("test") is not False
            or not isinstance(provider_id, str)
            or not provider_id.startswith("pi_")
            or not isinstance(order_id, str)
            or not order_id.isascii()
            or not order_id.isdecimal()
            or len(order_id) > 19
            or not 0 < int(order_id) < 2**63
            or not isinstance(data.get("amount"), str)
            or data.get("currency") != "RUB"
        ):
            return web.Response(status=400)
        return await settle_hosted_payment(
            self,
            provider=PROVIDER_KEYS,
            provider_id=provider_id,
            order_id=order_id,
            state="succeeded",
            amount=data["amount"],
            currency=data["currency"],
        )
