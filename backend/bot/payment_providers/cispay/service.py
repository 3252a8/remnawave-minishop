from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from aiogram import F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import payment_dal, provider_mandate_dal

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
from ..shared.hosted_settlement import settle_hosted_payment
from ..shared.managed_mandates import (
    ManagedMandateMixin,
    checkout_period_days,
    create_managed_checkout,
    parse_charge_time,
    settle_managed_charge,
    update_mandate_state,
)
from .config import CisPayConfig, CisPayPresentation


class CisPayService(HttpClientMixin, ManagedMandateMixin):
    mandate_providers = ("cispay_subscription_card", "cispay_subscription_sbp")

    def __init__(self, ctx: ServiceFactoryContext, config: CisPayConfig):
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
                or self.config.SUBSCRIPTION_CARD_ENABLED
                or self.config.SUBSCRIPTION_CARD_ADMIN_ONLY_ENABLED
                or self.config.SUBSCRIPTION_SBP_ENABLED
                or self.config.SUBSCRIPTION_SBP_ADMIN_ONLY_ENABLED
            )
            and self.config.API_KEY.strip()
            and self.config.SHOP_ID.strip()
        )

    @property
    def manages_recurrence(self) -> bool:
        return True

    @property
    def can_reconcile_payments(self) -> bool:
        return bool(self.config.API_KEY.strip() and self.config.SHOP_ID.strip())

    @property
    def base_url(self) -> str:
        return self.config.BASE_URL.rstrip("/")

    async def api_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> CreateResult:
        if not self.can_reconcile_payments:
            return False, {"message": "service_not_configured"}
        headers = {
            "X-Shop-ID": self.config.SHOP_ID.strip(),
            "X-Api-Key": self.config.API_KEY.strip(),
        }
        try:
            session = await self._get_session()
            async with session.request(
                method, f"{self.base_url}{path}", json=body, params=params, headers=headers
            ) as response:
                data = await response.json()
                if response.status not in {200, 201} or not isinstance(data, dict):
                    return False, {
                        "message": "provider_request_rejected",
                        "status": response.status,
                    }
                return True, data
        except Exception:
            return False, {"message": "provider_request_failed"}

    @staticmethod
    def normalize_payment(data: dict[str, Any]) -> dict[str, Any]:
        currency = data.get("source_currency") or data.get("currency")
        amount = data.get("source_amount") if data.get("source_currency") else data.get("amount")
        return {
            **data,
            "currency": currency,
            "amount": str(Decimal(amount) / 100)
            if isinstance(amount, int) and not isinstance(amount, bool)
            else None,
        }

    async def create_payment(
        self, *, payment_db_id: int, user_id: int, amount: float, currency: str, description: str
    ) -> CreateResult:
        if not self.configured or currency.upper() not in {"RUB", "USD"}:
            return False, {"message": "service_not_configured_or_unsupported_currency"}
        return_url = self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"
        body = {
            "amount": int(format_decimal_amount(amount) * 100),
            "currency": currency.upper(),
            "order_id": str(payment_db_id),
            "customer_id": str(user_id),
            "description": description[:512],
            "redirect_success_url": return_url,
            "redirect_fail_url": return_url,
        }
        return await self.api_request("POST", "/payments", body=body)

    async def get_payment(self, provider_payment_id: str) -> CreateResult:
        success, data = await self.api_request(
            "GET", "/payments/status", params={"id": provider_payment_id}
        )
        if (
            success
            and data.get("is_sandbox") is not False
            and not self.config.ALLOW_SANDBOX_PAYMENTS
        ):
            return False, {"message": "sandbox_payment_rejected"}
        return success, self.normalize_payment(data) if success else data

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        remote_id = str(payment.provider_payment_id or "")
        success, data = await self.get_payment(remote_id)
        if (
            not success
            or str(data.get("id") or "") != remote_id
            or str(data.get("order_id") or "") != str(payment.payment_id)
            or data.get("status") != "PENDING"
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
        raw = await request.read()
        signature = request.headers.get("X-Signature", "")
        expected = hmac.new(self.config.API_KEY.strip().encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return web.Response(status=403)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return web.Response(status=400)
        if not isinstance(data, dict):
            return web.Response(status=400)
        if str(data.get("store_id") or "") != self.config.SHOP_ID.strip():
            return web.Response(status=403)
        if data.get("is_sandbox") is not False and not self.config.ALLOW_SANDBOX_PAYMENTS:
            return web.Response(status=400, text="sandbox_payment_rejected")
        remote_subscription_id = str(data.get("subscription_id") or "")
        if remote_subscription_id:
            for provider in self.mandate_providers:
                async with self.async_session_factory() as session:
                    record = await provider_mandate_dal.get_mandate(
                        session, provider=provider, remote_id=remote_subscription_id
                    )
                if record is not None:
                    confirmed = await self.reconcile_remote_mandate(
                        provider=provider, remote_id=remote_subscription_id
                    )
                    return web.Response(
                        status=200 if confirmed else 500,
                        text="ok" if confirmed else "reconciliation_failed",
                    )
            return web.Response(status=404)
        normalized = self.normalize_payment(data)
        status = str(data.get("status") or "")
        if status not in {"PAID", "FAILED", "EXPIRED", "REFUNDED"}:
            return web.Response(text="ok")
        # Confirm through the read API as well: crypto checkout may convert RUB
        # to USD, while webhook amounts are in the transaction currency.
        if status == "PAID":
            success, verified = await self.get_payment(str(data.get("id") or ""))
            if (
                not success
                or verified.get("status") != "PAID"
                or str(verified.get("id") or "") != str(data.get("id") or "")
                or str(verified.get("order_id") or "") != str(data.get("order_id") or "")
            ):
                return web.Response(status=500, text="payment_not_verified")
            normalized = verified
        return await settle_hosted_payment(
            self,
            provider="cispay",
            provider_id=str(data.get("id") or ""),
            order_id=data.get("order_id"),
            state="succeeded" if status == "PAID" else "failed",
            amount=normalized.get("amount"),
            currency=normalized.get("currency"),
        )

    async def stop_remote_subscription(self, remote_id: str) -> bool:
        success, data = await self.api_request(
            "POST", f"/subscriptions/{quote(remote_id, safe='')}/cancel"
        )
        return (
            success and str(data.get("id") or "") == remote_id and data.get("status") == "CANCELLED"
        )

    async def reconcile_remote_mandate(self, *, provider: str, remote_id: str) -> bool:
        success, data = await self.api_request("GET", f"/subscriptions/{quote(remote_id, safe='')}")
        if not success or str(data.get("id") or "") != remote_id:
            return False
        async with self.async_session_factory() as session:
            record = await provider_mandate_dal.get_mandate(
                session, provider=provider, remote_id=remote_id
            )
            if (
                record is None
                or str(data.get("customer_id") or "") != str(record.provider_customer_id)
                or data.get("payment_method") != ("CARD" if provider.endswith("_card") else "SBP")
                or data.get("interval_days") != record.period_days
            ):
                return False
        status = {
            "PENDING": "pending",
            "ACTIVE": "active",
            "PAUSED": "paused",
            "CANCELLED": "cancelled",
            "FAILED": "failed",
        }.get(str(data.get("status") or ""))
        if status is None:
            return False
        charges = data.get("charges")
        if not isinstance(charges, list) or any(not isinstance(charge, dict) for charge in charges):
            return False
        for charge in sorted(charges, key=lambda item: str(item.get("created_at") or "")):
            if charge.get("status") != "PAID":
                continue
            charge_id = str(charge.get("id") or "")
            if not charge_id:
                return False
            async with self.async_session_factory() as session:
                existing = await payment_dal.get_payment_by_idempotence_key(
                    session, f"mandate:{provider}:{remote_id}:{charge_id}"
                )
                if existing is not None and existing.status in {
                    "succeeded",
                    "succeeded_pending_review",
                }:
                    continue
            confirmed, payment = await self.get_payment(charge_id)
            if (
                not confirmed
                or payment.get("status") != "PAID"
                or str(payment.get("id") or "") != charge_id
            ):
                return False
            paid_at = parse_charge_time(charge.get("paid_at") or charge.get("created_at"))
            if paid_at is None or not await settle_managed_charge(
                self,
                provider=provider,
                remote_id=remote_id,
                charge_id=charge_id,
                amount=payment.get("amount"),
                currency=payment.get("currency"),
                occurred_at=paid_at,
                remote_state=status,
            ):
                return False
        await update_mandate_state(self, provider=provider, remote_id=remote_id, status=status)
        return True


async def cispay_webhook_route(request: web.Request) -> web.Response:
    return await app_required(request, "cispay_service", CisPayService).webhook_route(request)


router = Router(name="user_subscription_payments_cispay_router")


@router.callback_query(F.data.startswith("pay_cispay:"))
async def pay_cispay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    cispay_service: CisPayService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, cispay_service, session)


def create_service(ctx: ServiceFactoryContext) -> CisPayService:
    bundle = ctx.config_for("cispay_service")
    config = bundle.config if bundle and isinstance(bundle.config, CisPayConfig) else CisPayConfig()
    return CisPayService(ctx, config)


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


_CONFIG_MANIFEST = tuple(
    ProviderManifestField(
        f"CISPAY_{attr}", type_, label, subsection="CisPay", attr=attr, secret=secret
    )
    for attr, type_, label, secret in (
        ("ENABLED", "bool", "Enabled", False),
        ("SHOP_ID", "string", "Shop ID", False),
        ("API_KEY", "string", "API key", True),
        ("BASE_URL", "url", "Base URL", False),
        ("RETURN_URL", "url", "Return URL", False),
        ("ALLOW_SANDBOX_PAYMENTS", "bool", "Allow sandbox payments in a test store", False),
        ("SUBSCRIPTION_CARD_ENABLED", "bool", "Recurring card payments", False),
        (
            "SUBSCRIPTION_CARD_ADMIN_ONLY_ENABLED",
            "bool",
            "Recurring card payments for administrators",
            False,
        ),
        ("SUBSCRIPTION_SBP_ENABLED", "bool", "Recurring SBP payments", False),
        (
            "SUBSCRIPTION_SBP_ADMIN_ONLY_ENABLED",
            "bool",
            "Recurring SBP payments for administrators",
            False,
        ),
    )
)
_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        f"PAYMENT_CISPAY_{attr}",
        "icon" if attr == "WEBAPP_ICON" else "string",
        label,
        subsection="CisPay",
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
    id="cispay",
    provider_key="cispay",
    label="CisPay",
    webapp_label="CisPay",
    webapp_icon="CreditCard",
    telegram_labels={"ru": "CisPay", "en": "CisPay"},
    logo_url="/provider-logos/cispay.png",
    pending_status="pending_cispay",
    enabled=lambda config: bool(config.ENABLED),
    service_key="cispay_service",
    callback_prefix="pay_cispay",
    router=router,
    create_service=create_service,
    webhook_path=lambda _source: "/webhook/cispay",
    webhook_route=cispay_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=CisPayConfig,
    presentation_class=CisPayPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=("RUB", "USD"),
    info_url="https://cispay.app",
    currency_support_url="https://cispay.app/developers",
)


async def _create_payment(service: CisPayService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        user_id=req.user_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
    )


_DESCRIPTOR: LinkPaymentDescriptor[CisPayService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="cispay",
    pending_status="pending_cispay",
    display_name="CisPay",
    log_prefix="cispay",
    service_app_key="cispay_service",
    service_type=CisPayService,
    create=_create_payment,
    reuse=lambda service, payment: service.try_reuse_pending_payment(payment),
    extract_url=lambda data: first_value(data, "payment_url"),
    extract_provider_id=lambda data: first_value(data, "id"),
    checkout_ttl_seconds=lambda _service, _request: 1800,
)


async def create_card_subscription_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_CARD_SUBSCRIPTION_DESCRIPTOR, ctx)


async def create_sbp_subscription_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_SBP_SUBSCRIPTION_DESCRIPTOR, ctx)


async def reuse_subscription_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    descriptor = (
        _CARD_SUBSCRIPTION_DESCRIPTOR
        if ctx.method == "cispay_subscription_card"
        else _SBP_SUBSCRIPTION_DESCRIPTOR
    )
    return await run_reuse_webapp_payment(descriptor, ctx, payment)


@router.callback_query(F.data.startswith("pay_cispay_subscription_card:"))
async def pay_cispay_subscription_card_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    cispay_service: CisPayService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _CARD_SUBSCRIPTION_DESCRIPTOR, callback, settings, i18n_data, cispay_service, session
    )


@router.callback_query(F.data.startswith("pay_cispay_subscription_sbp:"))
async def pay_cispay_subscription_sbp_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    cispay_service: CisPayService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _SBP_SUBSCRIPTION_DESCRIPTOR, callback, settings, i18n_data, cispay_service, session
    )


def _subscription_spec(method: str) -> PaymentProviderSpec:
    lower = method.lower()
    label = "CisPay card recurring" if method == "CARD" else "CisPay SBP recurring"
    return replace(
        SPEC,
        id=f"cispay_subscription_{lower}",
        provider_key=f"cispay_subscription_{lower}",
        label=label,
        webapp_label=label,
        telegram_labels={
            "ru": "CisPay · card recurring" if method == "CARD" else "CisPay · SBP recurring",
            "en": "CisPay · card recurring" if method == "CARD" else "CisPay · SBP recurring",
        },
        pending_status=f"pending_cispay_subscription_{lower}",
        callback_prefix=f"pay_cispay_subscription_{lower}",
        enabled=lambda config: bool(getattr(config, f"SUBSCRIPTION_{method}_ENABLED")),
        enabled_manifest_key=f"CISPAY_SUBSCRIPTION_{method}_ENABLED",
        admin_only_manifest_key=f"CISPAY_SUBSCRIPTION_{method}_ADMIN_ONLY_ENABLED",
        admin_only_config_attr=f"SUBSCRIPTION_{method}_ADMIN_ONLY_ENABLED",
        manages_recurring=True,
        webhook_path=None,
        webhook_route=None,
        manifest_fields=(),
        supported_currencies=("RUB",),
        create_webapp_payment=create_card_subscription_webapp_payment
        if method == "CARD"
        else create_sbp_subscription_webapp_payment,
        reuse_webapp_payment=reuse_subscription_webapp_payment,
        payment_context_resolver=lambda _config, months, sale_mode: (
            (days := checkout_period_days(months, sale_mode)) is not None and 7 <= days <= 360
        ),
        payment_minimum_resolver=lambda _config, _currency: (
            {"min_amount": "50.00", "min_currency": "RUB"} if method == "CARD" else None
        ),
        checkout_promo_resolver=lambda _config, _months, _sale_mode, _promo: False,
        supports_checkout_addons=False,
    )


CARD_SUBSCRIPTION_SPEC = _subscription_spec("CARD")
SBP_SUBSCRIPTION_SPEC = _subscription_spec("SBP")


async def _create_subscription(
    service: CisPayService, req: CreatePaymentRequest, *, method: str
) -> CreateResult:
    days = checkout_period_days(req.months, req.sale_mode)
    if (
        days is None
        or not 7 <= days <= 360
        or req.currency.upper() != "RUB"
        or not (
            getattr(service.config, f"SUBSCRIPTION_{method}_ENABLED")
            or getattr(service.config, f"SUBSCRIPTION_{method}_ADMIN_ONLY_ENABLED")
        )
    ):
        return False, {"message": "unsupported_recurring_checkout"}
    if method == "CARD" and req.amount < 50:
        return False, {"message": "payment_amount_below_minimum"}

    async def create_remote() -> CreateResult:
        return_url = service.config.RETURN_URL or f"https://t.me/{service._default_return_url}"
        body = {
            "amount": int(format_decimal_amount(req.amount) * 100),
            "currency": "RUB",
            "interval_days": days,
            "payment_method": method,
            "customer_id": str(req.user_id),
            "subscription_purpose": (req.description or "Subscription")[:255],
            "redirect_success_url": return_url,
            "redirect_fail_url": return_url,
        }
        return await service.api_request("POST", "/subscriptions", body=body)

    return await create_managed_checkout(
        service,
        req,
        provider=f"cispay_subscription_{method.lower()}",
        period_days=days,
        create_remote=create_remote,
    )


async def _reuse_subscription(service: CisPayService, payment: Any) -> str | None:
    remote_id = str(payment.provider_payment_id or "")
    async with service.async_session_factory() as session:
        record = await provider_mandate_dal.get_mandate(
            session, provider=payment.provider, remote_id=remote_id
        )
    if record is None or int(record.anchor_payment_id) != int(payment.payment_id):
        return None
    success, data = await service.api_request("GET", f"/subscriptions/{quote(remote_id, safe='')}")
    if (
        success
        and str(data.get("id") or "") == remote_id
        and str(data.get("customer_id") or "") == str(record.provider_customer_id)
        and data.get("interval_days") == record.period_days
        and data.get("payment_method") == ("CARD" if payment.provider.endswith("_card") else "SBP")
        and payment_amount_and_currency_match(
            expected_amount=payment.amount,
            expected_currency=payment.currency,
            received_amount=service.normalize_payment(data).get("amount"),
            received_currency=data.get("currency"),
        )
        and data.get("status") == "PENDING"
    ):
        return str(payment.provider_payment_url or "") or None
    return None


_CARD_SUBSCRIPTION_DESCRIPTOR = replace(
    _DESCRIPTOR,
    spec=CARD_SUBSCRIPTION_SPEC,
    provider_key="cispay_subscription_card",
    pending_status="pending_cispay_subscription_card",
    create=lambda service, req: _create_subscription(service, req, method="CARD"),
    reuse=_reuse_subscription,
)
_SBP_SUBSCRIPTION_DESCRIPTOR = replace(
    _DESCRIPTOR,
    spec=SBP_SUBSCRIPTION_SPEC,
    provider_key="cispay_subscription_sbp",
    pending_status="pending_cispay_subscription_sbp",
    create=lambda service, req: _create_subscription(service, req, method="SBP"),
    reuse=_reuse_subscription,
)
