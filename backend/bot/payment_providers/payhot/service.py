from __future__ import annotations

import hmac
import json
import logging
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlsplit

from aiogram import F, Router, types
from aiohttp import ClientError, web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.models import Payment

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    normalize_payment_currency_code,
    provider_runtime_enabled,
)
from ..shared import (
    CreatePaymentRequest,
    CreateResult,
    HttpClientMixin,
    LinkPaymentDescriptor,
    format_decimal_amount,
    payment_amount_and_currency_match,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required
from ..shared.hosted_settlement import settle_hosted_payment
from .config import PAYHOT_API_URL, PAYMENT_METHOD_CURRENCIES, PayHotConfig

logger = logging.getLogger(__name__)

_PROVIDER = "payhot"
_SERVICE = "payhot_service"
_PENDING = "pending_payhot"
_PAYABLE = {"requires_payment_method", "requires_action", "processing"}
_SIGNATURE = re.compile(r"t=([0-9]{1,12}),v2=([a-f0-9]{64})")
_MINOR = re.compile(r"[1-9][0-9]{0,17}")
_CURRENCIES = {"RUB", "USD", "EUR"}


def _amount_from_minor(value: object) -> Decimal | None:
    if isinstance(value, str) and _MINOR.fullmatch(value):
        return Decimal(value).scaleb(-2)
    return None


def _checkout_url(checkout: dict[str, Any]) -> str | None:
    url = checkout.get("url")
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme == "https" and parsed.hostname and parsed.username is None:
        return url
    return None


class PayHotService(HttpClientMixin):
    def __init__(self, ctx: ServiceFactoryContext, config: PayHotConfig):
        self.config = config
        self.settings = ctx.settings
        self.bot = ctx.bot
        self.i18n = ctx.i18n
        self.async_session_factory = ctx.async_session_factory
        self.subscription_service = ctx.subscription_service
        self.referral_service = ctx.referral_service
        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)

    @property
    def configured(self) -> bool:
        return bool(
            provider_runtime_enabled(self.config)
            and self.can_reconcile_payments
            and self.config.WEBHOOK_SECRET.strip()
            and self.config.supported_currencies
        )

    @property
    def can_reconcile_payments(self) -> bool:
        api_key = self.config.API_KEY.strip()
        return bool(api_key and not api_key.startswith("phk_test_v2_"))

    @property
    def _order_prefix(self) -> str:
        return f"minishop-{self.bot.id}-"

    def _local_order_id(self, value: object) -> str | None:
        if not isinstance(value, str) or not value.startswith(self._order_prefix):
            return None
        order_id = value.removeprefix(self._order_prefix)
        if re.fullmatch(r"[1-9][0-9]{0,18}", order_id) and int(order_id) <= 2**63 - 1:
            return order_id
        return None

    async def _request(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> CreateResult:
        headers = {"Authorization": f"Bearer {self.config.API_KEY.strip()}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            session = await self._get_session()
            async with session.request(
                method, url, json=body, headers=headers, allow_redirects=False
            ) as response:
                if response.status not in {200, 201}:
                    logger.warning("PayHot %s request returned HTTP %s", method, response.status)
                    return False, {"status": response.status, "message": "payhot_api_error"}
                data = await response.json()
        except (ClientError, TimeoutError, OSError):
            logger.warning("PayHot %s request failed", method)
            return False, {"message": "request_failed"}
        except ValueError:
            return False, {"message": "invalid_response"}
        if not isinstance(data, dict):
            return False, {"message": "invalid_response"}
        return True, data

    async def create_payment(
        self, *, payment_db_id: int, amount: float, currency: str
    ) -> CreateResult:
        if not self.configured:
            return False, {"message": "service_not_configured"}
        currency = normalize_payment_currency_code(currency, default="")
        if currency not in self.config.supported_currencies:
            return False, {"message": "unsupported_currency"}
        amount_minor = str(int(format_decimal_amount(amount).scaleb(2)))
        if not _MINOR.fullmatch(amount_minor):
            return False, {"message": "invalid_amount"}

        order_reference = f"{self._order_prefix}{payment_db_id}"
        idempotency_key = f"payhot-create-{order_reference}"
        body = {
            "merchant_order_reference": order_reference,
            "amount_minor": amount_minor,
            "currency": currency,
            "payment_method": self.config.payment_method,
        }
        ok, data = await self._request(
            "POST", PAYHOT_API_URL, body=body, idempotency_key=idempotency_key
        )
        if not ok and data.get("message") == "request_failed":
            ok, data = await self._request(
                "POST", PAYHOT_API_URL, body=body, idempotency_key=idempotency_key
            )
        if not ok:
            return False, data

        remote = data.get("payment")
        if (
            not isinstance(remote, dict)
            or remote.get("merchant_order_reference") != order_reference
            or remote.get("amount_minor") != amount_minor
            or remote.get("currency") != currency
            or not isinstance(provider_id := remote.get("id"), str)
            or not provider_id
        ):
            return False, {"message": "payment_identity_mismatch"}

        checkout = data.get("checkout")
        if isinstance(checkout, dict) and checkout.get("reissue_required") is True:
            ok, data = await self._request(
                "POST", f"{PAYHOT_API_URL}/{quote(provider_id, safe='')}/checkout-sessions"
            )
            if not ok:
                return False, {"id": provider_id, **data}
            checkout = data.get("checkout")
        if not isinstance(checkout, dict) or not (url := _checkout_url(checkout)):
            return False, {"id": provider_id, "message": "missing_checkout_url"}
        return True, {"id": provider_id, "url": url, "expires_at": checkout.get("expires_at")}

    async def get_payment(self, provider_payment_id: str) -> CreateResult:
        if not self.can_reconcile_payments or not provider_payment_id:
            return False, {"message": "service_not_configured"}
        ok, data = await self._request(
            "GET", f"{PAYHOT_API_URL}/{quote(provider_payment_id, safe='')}"
        )
        if not ok:
            return False, data
        remote = data.get("payment")
        if not isinstance(remote, dict) or remote.get("id") != provider_payment_id:
            return False, {"message": "payment_identity_mismatch"}
        order_id = self._local_order_id(remote.get("merchant_order_reference"))
        currency = remote.get("currency")
        amount = _amount_from_minor(remote.get("amount_minor"))
        if order_id is None or not isinstance(currency, str) or currency not in _CURRENCIES:
            return False, {"message": "payment_identity_mismatch"}
        return True, {**remote, "order_id": order_id, "amount": amount}

    async def try_reuse_pending_payment(self, payment: Payment) -> str | None:
        ok, data = await self.get_payment(str(payment.provider_payment_id or ""))
        if (
            not ok
            or data.get("status") not in _PAYABLE
            or data.get("order_id") != str(payment.payment_id)
            or not payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=data.get("amount"),
                received_currency=data.get("currency"),
            )
        ):
            return None
        return payment.provider_payment_url

    async def webhook_route(self, request: web.Request) -> web.Response:
        secret = self.config.WEBHOOK_SECRET.strip()
        if not secret:
            return web.Response(status=503)
        raw = await request.read()
        signature = _SIGNATURE.fullmatch(request.headers.get("PayHot-Signature", ""))
        if signature is None:
            return web.Response(status=403)
        timestamp, supplied = signature.groups()
        if abs(time.time() - int(timestamp)) > 300:
            return web.Response(status=403)
        expected = hmac.digest(secret.encode(), timestamp.encode() + b"." + raw, "sha256").hex()
        if not hmac.compare_digest(expected, supplied):
            return web.Response(status=403)

        try:
            event = json.loads(raw)
        except ValueError:
            return web.Response(status=400)
        if not isinstance(event, dict):
            return web.Response(status=400)
        if event.get("event_type") != "payment.succeeded" or event.get("environment") == "sandbox":
            return web.Response(text="ok")
        data = event.get("data")
        if (
            event.get("api_version") != "v2"
            or not isinstance(data, dict)
            or data.get("object") != "payment"
            or data.get("status") != "succeeded"
        ):
            return web.Response(status=400)
        if data.get("origin") == "recurring":
            return web.Response(text="ok")
        order_id = self._local_order_id(data.get("merchant_order_reference"))
        provider_id = data.get("id")
        currency = data.get("currency")
        amount = _amount_from_minor(data.get("amount_minor"))
        captured = _amount_from_minor(data.get("captured_amount_minor"))
        if (
            order_id is None
            or not isinstance(provider_id, str)
            or not provider_id
            or not isinstance(currency, str)
            or currency not in _CURRENCIES
            or amount is None
            or captured is None
            or captured < amount
        ):
            return web.Response(status=400)
        return await settle_hosted_payment(
            self,
            provider=_PROVIDER,
            provider_id=provider_id,
            order_id=order_id,
            state="succeeded",
            amount=amount,
            currency=currency,
        )


async def payhot_webhook_route(request: web.Request) -> web.Response:
    return await app_required(request, _SERVICE, PayHotService).webhook_route(request)


router = Router(name="user_subscription_payments_payhot_router")


@router.callback_query(F.data.startswith("pay_payhot:"))
async def pay_payhot_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    payhot_service: PayHotService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, payhot_service, session)


def create_service(ctx: ServiceFactoryContext) -> PayHotService:
    bundle = ctx.config_for(_SERVICE)
    config = bundle.config if bundle and isinstance(bundle.config, PayHotConfig) else PayHotConfig()
    return PayHotService(ctx, config)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Payment) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


SPEC = PaymentProviderSpec(
    id=_PROVIDER,
    provider_key=_PROVIDER,
    pending_status=_PENDING,
    label="PayHot",
    webapp_label="PayHot",
    webapp_icon="CreditCard",
    payment_group="mixed",
    enabled=lambda config: bool(config.ENABLED),
    service_key=_SERVICE,
    callback_prefix="pay_payhot",
    router=router,
    create_service=create_service,
    webhook_path=lambda _source: "/webhook/payhot",
    webhook_route=payhot_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=PayHotConfig,
    supported_currencies_resolver=lambda config: getattr(
        config, "supported_currencies", PAYMENT_METHOD_CURRENCIES["card"]
    ),
    info_url="https://pay.hot",
    currency_support_url="https://docs.pay.hot/overview",
    manifest_fields=(
        ProviderManifestField(
            "PAYHOT_ENABLED", "bool", "Enabled", subsection="PayHot", attr="ENABLED"
        ),
        ProviderManifestField(
            "PAYHOT_API_KEY", "string", "API key", subsection="PayHot", attr="API_KEY", secret=True
        ),
        ProviderManifestField(
            "PAYHOT_WEBHOOK_SECRET",
            "string",
            "Webhook signing secret",
            subsection="PayHot",
            attr="WEBHOOK_SECRET",
            secret=True,
        ),
        ProviderManifestField(
            "PAYHOT_PAYMENT_METHOD",
            "string",
            "Payment method",
            subsection="PayHot",
            attr="PAYMENT_METHOD",
            choices=(
                ("card", "Card"),
                ("sbp", "SBP"),
                ("sberpay", "SberPay"),
                ("applepay", "Apple Pay"),
                ("googlepay", "Google Pay"),
                ("crypto", "Crypto"),
            ),
        ),
    ),
)


async def _create_payment(service: PayHotService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
    )


_DESCRIPTOR: LinkPaymentDescriptor[PayHotService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key=_PROVIDER,
    pending_status=_PENDING,
    display_name="PayHot",
    log_prefix=_PROVIDER,
    service_app_key=_SERVICE,
    service_type=PayHotService,
    create=_create_payment,
    reuse=lambda service, payment: service.try_reuse_pending_payment(payment),
    extract_url=lambda data: data.get("url"),
    extract_provider_id=lambda data: data.get("id"),
)
