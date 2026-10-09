from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import replace
from datetime import timedelta, timezone
from typing import Any

from aiogram import F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import provider_mandate_dal

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
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required
from ..shared.common import payment_amount_matches
from ..shared.hosted_settlement import settle_hosted_payment
from ..shared.managed_mandates import (
    ManagedMandateMixin,
    checkout_period_days,
    create_managed_checkout,
    parse_charge_time,
    settle_managed_charge,
    update_mandate_state,
)
from .config import CryptomusConfig, CryptomusPresentation


class CryptomusService(HttpClientMixin, ManagedMandateMixin):
    mandate_providers = ("cryptomus_subscription",)

    def __init__(self, ctx: ServiceFactoryContext, config: CryptomusConfig):
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
        return bool(
            (
                provider_runtime_enabled(self.config)
                or self.config.SUBSCRIPTION_ENABLED
                or self.config.SUBSCRIPTION_ADMIN_ONLY_ENABLED
            )
            and self.config.API_KEY.strip()
            and self.config.MERCHANT_ID.strip()
        )

    @property
    def manages_recurrence(self) -> bool:
        # Missing credentials must not make cancellation report false success.
        return True

    @property
    def can_reconcile_payments(self) -> bool:
        return bool(self.config.API_KEY.strip() and self.config.MERCHANT_ID.strip())

    @property
    def base_url(self) -> str:
        return self.config.BASE_URL.rstrip("/")

    def signature(self, raw: bytes) -> str:
        return hashlib.md5(
            base64.b64encode(raw) + self.config.API_KEY.strip().encode(), usedforsecurity=False
        ).hexdigest()

    async def api_request(self, path: str, body: dict[str, Any]) -> CreateResult:
        if not self.can_reconcile_payments:
            return False, {"message": "service_not_configured"}
        raw = (
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).replace("/", "\\/").encode()
        )
        headers = {
            "merchant": self.config.MERCHANT_ID.strip(),
            "sign": self.signature(raw),
            "Content-Type": "application/json",
        }
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/{path}", data=raw, headers=headers
            ) as response:
                data = await response.json()
                if (
                    response.status != 200
                    or not isinstance(data, dict)
                    or data.get("state") != 0
                    or not isinstance(data.get("result"), dict)
                ):
                    return False, {
                        "message": "provider_request_rejected",
                        "status": response.status,
                    }
                return True, data["result"]
        except Exception:
            return False, {"message": "provider_request_failed"}

    async def create_payment(
        self, *, payment_db_id: int, amount: float, currency: str, description: str
    ) -> CreateResult:
        if not self.configured or currency.upper() not in {"RUB", "USD"}:
            return False, {"message": "service_not_configured_or_unsupported_currency"}
        body: dict[str, Any] = {
            "amount": f"{format_decimal_amount(amount):.2f}",
            "currency": currency.upper(),
            "order_id": str(payment_db_id),
            "url_callback": f"{self.settings.WEBHOOK_BASE_URL.rstrip('/')}/webhook/cryptomus",
            "url_return": self.config.RETURN_URL or f"https://t.me/{self._default_return_url}",
            "lifetime": self.config.LIFETIME_SECONDS,
            "accuracy_payment_percent": 0,
            "is_payment_multiple": True,
        }
        if self.config.TO_CURRENCY:
            body["to_currency"] = self.config.TO_CURRENCY
        if self.config.NETWORK:
            body["network"] = self.config.NETWORK
        success, data = await self.api_request("payment", body)
        if success:
            data["id"] = data.get("uuid")
            data["paymentUrl"] = data.get("url")
        return success, data

    async def get_payment(self, provider_payment_id: str) -> CreateResult:
        success, data = await self.api_request("payment/info", {"uuid": provider_payment_id})
        if success:
            data["id"] = data.get("uuid")
        return success, data

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        provider_id = str(payment.provider_payment_id or "")
        success, data = await self.get_payment(provider_id)
        if (
            not success
            or str(data.get("id")) != provider_id
            or str(data.get("order_id")) != str(payment.payment_id)
            or data.get("status")
            not in {"check", "confirm_check", "wrong_amount", "wrong_amount_waiting"}
            or data.get("is_final") is True
        ):
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
        try:
            data = json.loads(await request.read())
        except (ValueError, UnicodeDecodeError):
            return web.Response(status=400)
        if not isinstance(data, dict):
            return web.Response(status=400)
        provided = data.pop("sign", "")
        raw = (
            json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("/", "\\/").encode()
        )
        if not isinstance(provided, str) or not hmac.compare_digest(
            provided.encode(), self.signature(raw).encode()
        ):
            return web.Response(status=403)
        # Recurrence callbacks have no separate published wire schema. Never infer
        # a debit from their shape: refresh known mandates through recurrence/info.
        if data.get("type") != "payment":
            await self.reconcile_recurring_payments()
            return web.Response(text="ok")
        status = str(data.get("status") or "")
        if status not in {"paid", "paid_over", "cancel", "fail", "system_fail", "wrong_amount"}:
            return web.Response(text="ok")
        state = "succeeded" if status in {"paid", "paid_over"} else "failed"
        if status == "wrong_amount" and data.get("is_final") is not True:
            return web.Response(text="ok")
        if state == "succeeded" and not payment_amount_matches(
            expected_amount=data.get("amount"),
            received_amount=data.get("payment_amount"),
            allow_overpayment=True,
        ):
            return web.Response(status=400, text="underpayment")
        response = await settle_hosted_payment(
            self,
            provider="cryptomus",
            provider_id=str(data.get("uuid") or ""),
            order_id=data.get("order_id"),
            state=state,
            amount=data.get("amount"),
            currency=data.get("currency"),
        )
        if response.status == 404 and str(data.get("order_id") or "").isdigit():
            async with self.async_session_factory() as session:
                record = await provider_mandate_dal.get_by_anchor(
                    session,
                    provider="cryptomus_subscription",
                    anchor_payment_id=int(data["order_id"]),
                )
                remote_id = str(record.remote_id) if record is not None else ""
            if remote_id:
                confirmed = await self.reconcile_remote_mandate(
                    provider="cryptomus_subscription", remote_id=remote_id
                )
                return web.Response(
                    status=200 if confirmed else 500,
                    text="ok" if confirmed else "reconciliation_failed",
                )
        return response

    async def stop_remote_subscription(self, remote_id: str) -> bool:
        success, data = await self.api_request("recurrence/cancel", {"uuid": remote_id})
        if not success or str(data.get("uuid") or "") != remote_id:
            return False
        if data.get("status") not in {"cancel_by_merchant", "cancel_by_user"}:
            success, data = await self.api_request("recurrence/info", {"uuid": remote_id})
        return bool(
            success
            and str(data.get("uuid") or "") == remote_id
            and data.get("status") in {"cancel_by_merchant", "cancel_by_user"}
        )

    async def reconcile_remote_mandate(self, *, provider: str, remote_id: str) -> bool:
        success, data = await self.api_request("recurrence/info", {"uuid": remote_id})
        if not success or str(data.get("uuid") or "") != remote_id:
            return False
        async with self.async_session_factory() as session:
            record = await provider_mandate_dal.get_mandate(
                session, provider=provider, remote_id=remote_id
            )
            if record is None or str(data.get("order_id") or "") != str(record.anchor_payment_id):
                return False
        state = str(data.get("status") or "")
        status = {
            "active": "active",
            "wait_accept": "pending",
            "cancel_by_merchant": "cancelled",
            "cancel_by_user": "cancelled",
        }.get(state)
        if status is None:
            return False
        paid_at = parse_charge_time(
            data.get("last_pay_off"), default_timezone=timezone(timedelta(hours=3))
        )
        if paid_at is not None and not await settle_managed_charge(
            self,
            provider=provider,
            remote_id=remote_id,
            charge_id=paid_at.isoformat(),
            amount=data.get("amount"),
            currency=data.get("currency"),
            occurred_at=paid_at,
            remote_state=status,
        ):
            return False
        await update_mandate_state(self, provider=provider, remote_id=remote_id, status=status)
        return True


async def cryptomus_webhook_route(request: web.Request) -> web.Response:
    return await app_required(request, "cryptomus_service", CryptomusService).webhook_route(request)


router = Router(name="user_subscription_payments_cryptomus_router")


@router.callback_query(F.data.startswith("pay_cryptomus:"))
async def pay_cryptomus_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    cryptomus_service: CryptomusService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _DESCRIPTOR, callback, settings, i18n_data, cryptomus_service, session
    )


def create_service(ctx: ServiceFactoryContext) -> CryptomusService:
    bundle = ctx.config_for("cryptomus_service")
    config = (
        bundle.config
        if bundle and isinstance(bundle.config, CryptomusConfig)
        else CryptomusConfig()
    )
    return CryptomusService(ctx, config)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


_CONFIG_MANIFEST = tuple(
    ProviderManifestField(
        f"CRYPTOMUS_{attr}", type_, label, subsection="Cryptomus", attr=attr, secret=secret
    )
    for attr, type_, label, secret in (
        ("ENABLED", "bool", "Enabled", False),
        ("MERCHANT_ID", "string", "Merchant ID", False),
        ("API_KEY", "string", "Payment API key", True),
        ("BASE_URL", "url", "Base URL", False),
        ("RETURN_URL", "url", "Return URL", False),
        ("TO_CURRENCY", "string", "Payment cryptocurrency", False),
        ("NETWORK", "string", "Blockchain network", False),
        ("LIFETIME_SECONDS", "int", "Invoice lifetime (seconds)", False),
        ("SUBSCRIPTION_ENABLED", "bool", "Recurring payments", False),
        ("SUBSCRIPTION_ADMIN_ONLY_ENABLED", "bool", "Recurring payments for administrators", False),
    )
)
_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        f"PAYMENT_CRYPTOMUS_{attr}",
        "icon" if attr == "WEBAPP_ICON" else "string",
        label,
        subsection="Cryptomus",
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
    id="cryptomus",
    provider_key="cryptomus",
    label="Cryptomus",
    webapp_label="Cryptomus",
    webapp_icon="Bitcoin",
    telegram_labels={"ru": "Cryptomus", "en": "Cryptomus"},
    logo_url="/provider-logos/cryptomus.png",
    pending_status="pending_cryptomus",
    enabled=lambda config: bool(config.ENABLED),
    service_key="cryptomus_service",
    callback_prefix="pay_cryptomus",
    router=router,
    create_service=create_service,
    webhook_path=lambda _source: "/webhook/cryptomus",
    webhook_route=cryptomus_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=CryptomusConfig,
    presentation_class=CryptomusPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=("RUB", "USD"),
    info_url="https://cryptomus.com",
    currency_support_url="https://doc.cryptomus.com/merchant-api/payments/creating-invoice",
)


async def _create_payment(service: CryptomusService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
    )


_DESCRIPTOR: LinkPaymentDescriptor[CryptomusService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="cryptomus",
    pending_status="pending_cryptomus",
    display_name="Cryptomus",
    log_prefix="cryptomus",
    service_app_key="cryptomus_service",
    service_type=CryptomusService,
    create=_create_payment,
    reuse=lambda service, payment: service.try_reuse_pending_payment(payment),
    extract_url=lambda data: first_value(data, "paymentUrl"),
    extract_provider_id=lambda data: first_value(data, "id"),
    checkout_ttl_seconds=lambda service, _request: service.config.LIFETIME_SECONDS,
)


async def create_subscription_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_SUBSCRIPTION_DESCRIPTOR, ctx)


async def reuse_subscription_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_SUBSCRIPTION_DESCRIPTOR, ctx, payment)


@router.callback_query(F.data.startswith("pay_cryptomus_subscription:"))
async def pay_cryptomus_subscription_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    cryptomus_service: CryptomusService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _SUBSCRIPTION_DESCRIPTOR, callback, settings, i18n_data, cryptomus_service, session
    )


SUBSCRIPTION_SPEC = replace(
    SPEC,
    id="cryptomus_subscription",
    provider_key="cryptomus_subscription",
    label="Cryptomus recurring",
    webapp_label="Cryptomus recurring",
    webapp_labels={"ru": "Cryptomus · recurring", "en": "Cryptomus recurring"},
    telegram_labels={"ru": "Cryptomus · recurring", "en": "Cryptomus recurring"},
    pending_status="pending_cryptomus_subscription",
    callback_prefix="pay_cryptomus_subscription",
    enabled=lambda config: bool(config.SUBSCRIPTION_ENABLED),
    admin_only_config_attr="SUBSCRIPTION_ADMIN_ONLY_ENABLED",
    enabled_manifest_key="CRYPTOMUS_SUBSCRIPTION_ENABLED",
    admin_only_manifest_key="CRYPTOMUS_SUBSCRIPTION_ADMIN_ONLY_ENABLED",
    manages_recurring=True,
    webhook_route=None,
    webhook_path=None,
    manifest_fields=(),
    create_webapp_payment=create_subscription_webapp_payment,
    reuse_webapp_payment=reuse_subscription_webapp_payment,
    payment_context_resolver=lambda _config, months, sale_mode: (
        checkout_period_days(months, sale_mode) in {7, 30, 90}
    ),
    checkout_promo_resolver=lambda _config, _months, _sale_mode, _promo: False,
    supports_checkout_addons=False,
)


async def _create_subscription(
    service: CryptomusService, req: CreatePaymentRequest
) -> CreateResult:
    days = checkout_period_days(req.months, req.sale_mode)
    periods = {7: "weekly", 30: "monthly", 90: "three_month"}
    if days not in periods or not (
        service.config.SUBSCRIPTION_ENABLED or service.config.SUBSCRIPTION_ADMIN_ONLY_ENABLED
    ):
        return False, {"message": "unsupported_recurring_checkout"}

    async def create_remote() -> CreateResult:
        body = {
            "amount": f"{format_decimal_amount(req.amount):.2f}",
            "currency": req.currency.upper(),
            "name": req.description[:60] if len(req.description.strip()) >= 3 else "Subscription",
            "period": periods[days],
            "order_id": str(req.payment.payment_id),
            "url_callback": f"{service.settings.WEBHOOK_BASE_URL.rstrip('/')}/webhook/cryptomus",
        }
        if service.config.TO_CURRENCY:
            body["to_currency"] = service.config.TO_CURRENCY
        success, data = await service.api_request("recurrence/create", body)
        if success:
            data["id"] = data.get("uuid")
            data["payment_url"] = data.get("url")
        return success, data

    return await create_managed_checkout(
        service,
        req,
        provider="cryptomus_subscription",
        period_days=days,
        create_remote=create_remote,
    )


async def _reuse_subscription(service: CryptomusService, payment: Any) -> str | None:
    success, data = await service.api_request(
        "recurrence/info", {"uuid": str(payment.provider_payment_id or "")}
    )
    if (
        success
        and data.get("status") == "wait_accept"
        and str(data.get("uuid") or "") == str(payment.provider_payment_id)
        and str(data.get("order_id") or "") == str(payment.payment_id)
        and payment_amount_and_currency_match(
            expected_amount=payment.amount,
            expected_currency=payment.currency,
            received_amount=data.get("amount"),
            received_currency=data.get("currency"),
        )
    ):
        return str(payment.provider_payment_url or "") or None
    return None


_SUBSCRIPTION_DESCRIPTOR = replace(
    _DESCRIPTOR,
    spec=SUBSCRIPTION_SPEC,
    provider_key="cryptomus_subscription",
    pending_status="pending_cryptomus_subscription",
    create=_create_subscription,
    reuse=_reuse_subscription,
    extract_url=lambda data: first_value(data, "payment_url"),
    checkout_ttl_seconds=lambda _service, _request: None,
)
