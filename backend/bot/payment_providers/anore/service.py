from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib.parse import quote

from aiogram import F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
    provider_runtime_enabled,
)
from ..shared import (
    CreatePaymentRequest,
    CreateResult,
    HttpClientMixin,
    LinkPaymentDescriptor,
    first_value,
    format_decimal_amount,
    payment_amount_and_currency_match,
    post_json_request,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required
from ..shared.hosted_settlement import settle_hosted_payment
from .config import AnoreConfig, AnorePresentation


class AnoreService(HttpClientMixin):
    def __init__(self, ctx: ServiceFactoryContext, config: AnoreConfig):
        self.config = config
        self.settings = ctx.settings
        self.bot = ctx.bot
        self.i18n = ctx.i18n
        self.async_session_factory = ctx.async_session_factory
        self.subscription_service = ctx.subscription_service
        self.referral_service = ctx.referral_service
        self._default_return_url = ctx.bot_username_for_default_return
        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)

    @property
    def configured(self) -> bool:
        return provider_runtime_enabled(self.config) and self.can_reconcile_payments

    @property
    def can_reconcile_payments(self) -> bool:
        return bool(self.config.API_KEY.strip() and self.config.WEBHOOK_SECRET.strip())

    @property
    def base_url(self) -> str:
        return self.config.BASE_URL.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.API_KEY.strip()}"}

    async def create_payment(
        self, *, payment_db_id: int, amount: float, currency: str, description: str
    ) -> CreateResult:
        if not self.configured:
            return False, {"message": "service_not_configured"}
        currency = currency.upper()
        if currency not in {"RUB", "USD"}:
            return False, {"message": "unsupported_currency"}
        body: dict[str, Any] = {
            "amount": float(format_decimal_amount(amount)),
            "currency": currency,
            "orderId": str(payment_db_id),
            "description": description,
            "getbackurl": self.config.RETURN_URL or f"https://t.me/{self._default_return_url}",
            "callbackUrl": f"{self.settings.WEBHOOK_BASE_URL.rstrip('/')}/webhook/anore",
        }
        if self.config.SHOP_ID:
            body["shopId"] = self.config.SHOP_ID
        if self.config.METHODS:
            methods = [
                method.strip() for method in self.config.METHODS.split(",") if method.strip()
            ]
            if any(method not in {"sbp", "yoomoney", "crypto"} for method in methods):
                return False, {"message": "unsupported_payment_method"}
            body["methods"] = ",".join(methods)
        return await post_json_request(
            await self._get_session(),
            f"{self.base_url}/payments",
            body=body,
            headers=self.headers,
            log_prefix="Anore create payment",
            is_success=lambda status, data: (
                status == 200 and isinstance(data, dict) and data.get("success") is True
            ),
        )

    async def get_payment(self, provider_payment_id: str) -> CreateResult:
        if not self.can_reconcile_payments or not provider_payment_id:
            return False, {"message": "service_not_configured"}
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/payments/{quote(provider_payment_id, safe='')}",
                headers=self.headers,
            ) as response:
                data = await response.json()
                if (
                    response.status != 200
                    or not isinstance(data, dict)
                    or data.get("success") is not True
                ):
                    return False, {"message": "payment_lookup_failed"}
                if "orderId" in data:
                    data["order_id"] = data["orderId"]
                return True, data
        except Exception:
            return False, {"message": "payment_lookup_failed"}

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        provider_id = str(payment.provider_payment_id or "")
        success, data = await self.get_payment(provider_id)
        if not success or str(data.get("id")) != provider_id or data.get("status") != "new":
            return None
        if data.get("order_id") is not None and str(data["order_id"]) != str(payment.payment_id):
            return None
        if not payment_amount_and_currency_match(
            expected_amount=payment.amount,
            expected_currency=payment.currency,
            received_amount=data.get("amount"),
            received_currency=data.get("currency"),
        ):
            return None
        return str(payment.provider_payment_url or "") or None

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.can_reconcile_payments:
            return web.Response(status=503)
        raw = await request.read()
        signature = request.headers.get("Anore-Signature", "")
        expected = hmac.new(self.config.WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return web.Response(status=403)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return web.Response(status=400)
        if not isinstance(data, dict):
            return web.Response(status=400)
        event = data.get("event")
        if event not in {"payment.succeeded", "payment.expired"}:
            return web.Response(text="ok")
        if (event == "payment.succeeded" and data.get("status") != "paid") or (
            event == "payment.expired" and data.get("status") != "expired"
        ):
            return web.Response(status=400)
        return await settle_hosted_payment(
            self,
            provider="anore",
            provider_id=str(data.get("id") or ""),
            order_id=data.get("orderId"),
            state="succeeded" if event == "payment.succeeded" else "failed",
            amount=data.get("amount"),
            currency=data.get("currency"),
        )


async def anore_webhook_route(request: web.Request) -> web.Response:
    return await app_required(request, "anore_service", AnoreService).webhook_route(request)


router = Router(name="user_subscription_payments_anore_router")


@router.callback_query(F.data.startswith("pay_anore:"))
async def pay_anore_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    anore_service: AnoreService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, anore_service, session)


def create_service(ctx: ServiceFactoryContext) -> AnoreService:
    bundle = ctx.config_for("anore_service")
    config = bundle.config if bundle and isinstance(bundle.config, AnoreConfig) else AnoreConfig()
    return AnoreService(ctx, config)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


_CONFIG_MANIFEST = tuple(
    ProviderManifestField(
        f"ANORE_{attr}", type_, label, subsection="Anore", attr=attr, secret=secret
    )
    for attr, type_, label, secret in (
        ("ENABLED", "bool", "Enabled", False),
        ("API_KEY", "string", "API key", True),
        ("WEBHOOK_SECRET", "string", "Webhook secret", True),
        ("SHOP_ID", "int", "Shop ID", False),
        ("BASE_URL", "url", "Base URL", False),
        ("RETURN_URL", "url", "Return URL", False),
        ("METHODS", "string", "Payment methods (sbp,yoomoney,crypto)", False),
    )
)
_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        f"PAYMENT_ANORE_{attr}",
        "icon" if attr == "WEBAPP_ICON" else "string",
        label,
        subsection="Anore",
        target="presentation",
        attr=attr,
    )
    for attr, label in (
        ("WEBAPP_LABEL_RU", "WebApp button text (RU)"),
        ("WEBAPP_LABEL_EN", "WebApp button text (EN)"),
        ("WEBAPP_ICON", "WebApp button icon"),
        ("TELEGRAM_LABEL_RU", "Telegram button text (RU)"),
        ("TELEGRAM_LABEL_EN", "Telegram button text (EN)"),
        ("TELEGRAM_EMOJI", "Telegram button emoji"),
    )
)
SPEC = PaymentProviderSpec(
    id="anore",
    provider_key="anore",
    label="Anore",
    webapp_label="Anore",
    webapp_icon="CreditCard",
    telegram_labels={"ru": "Anore", "en": "Anore"},
    logo_url="/provider-logos/anore.png",
    pending_status="pending_anore",
    enabled=lambda config: bool(config.ENABLED),
    service_key="anore_service",
    callback_prefix="pay_anore",
    router=router,
    create_service=create_service,
    webhook_path=lambda _source: "/webhook/anore",
    webhook_route=anore_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=AnoreConfig,
    presentation_class=AnorePresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=("RUB", "USD"),
    info_url="https://anore.cc",
    currency_support_url="https://anore.cc/docs",
)


async def _create_payment(service: AnoreService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
    )


_DESCRIPTOR: LinkPaymentDescriptor[AnoreService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="anore",
    pending_status="pending_anore",
    display_name="Anore",
    log_prefix="anore",
    service_app_key="anore_service",
    service_type=AnoreService,
    create=_create_payment,
    reuse=lambda service, payment: service.try_reuse_pending_payment(payment),
    extract_url=lambda data: first_value(data, "paymentUrl"),
    extract_provider_id=lambda data: first_value(data, "id"),
    checkout_ttl_seconds=lambda _service, _request: 14400,
)
