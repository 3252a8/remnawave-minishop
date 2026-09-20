"""RollyPay hosted payments, signed webhooks and recurring SBP mandates."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from aiogram import Bot, F, Router, types
from aiohttp import ClientError, web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal

from ..base import PaymentProviderSpec, ServiceFactoryContext, WebAppPaymentContext
from ..shared import (
    CreatePaymentRequest,
    HttpClientMixin,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    finalize_successful_payment,
    first_value,
    format_number_for_payload,
    notify_user_payment_failed,
    payment_amount_and_currency_match,
    payment_units_for_activation,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required
from .config import RollyPayConfig
from .manifest import CONFIG_MANIFEST
from .subscriptions import (
    ROLLYPAY_SUBSCRIPTION_PROVIDER,
    RollyPaySubscriptionMixin,
    subscription_context_supported,
    subscription_promo_supported,
)

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

PENDING_STATUS = "pending_rollypay"
ONE_OFF_PROVIDERS = frozenset(
    {
        "rollypay",
        "rollypay_sbp",
        "rollypay_card",
        "rollypay_international",
        "rollypay_crypto",
    }
)
TERMINAL_FAILURE_STATUSES = frozenset({"canceled", "cancelled", "expired"})
REVERSAL_STATUSES = {"chargeback": "reversed", "refunded": "refunded"}
METHOD_BY_VARIANT = {
    "all_methods": None,
    "sbp": "sbp",
    "card": "card",
    "international": "intl_card",
    "crypto": "crypto",
}


def _unwrap_object(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = data
    for key in keys:
        nested = current.get(key) if isinstance(current, dict) else None
        if isinstance(nested, dict):
            return nested
    nested = data.get("data")
    return nested if isinstance(nested, dict) else data


def _order_payment_id(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text.startswith("minishop-"):
        return None
    try:
        return int(text.removeprefix("minishop-"))
    except ValueError:
        return None


class RollyPayService(HttpClientMixin, RollyPaySubscriptionMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: RollyPayConfig,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        default_return_url: str,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.config = config
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        normalized_return = str(default_return_url or "").strip()
        self.default_return_url = (
            normalized_return
            if normalized_return.startswith(("http://", "https://"))
            else f"https://t.me/{normalized_return}"
            if normalized_return
            else ""
        )
        self._subscription_plans_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._init_http_client(total_timeout=lambda: settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)

    @property
    def configured(self) -> bool:
        return bool(self.config.ENABLED and self.config.API_KEY and self.config.SIGNING_SECRET)

    @property
    def webhook_available(self) -> bool:
        return self.configured

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": str(self.config.API_KEY or ""),
            "X-Nonce": str(uuid.uuid4()),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key[:128]
        return headers

    async def api_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            return False, {"message": "service_not_configured"}
        normalized_method = method.upper()
        attempts = 2 if normalized_method == "GET" or idempotency_key else 1
        last_error: dict[str, Any] = {"message": "request_failed"}
        for attempt in range(attempts):
            session = await self._get_session()
            try:
                request = session.request(
                    normalized_method,
                    f"{self.config.BASE_URL}{path}",
                    headers=self._headers(idempotency_key=idempotency_key),
                    json=json_body,
                    params=params,
                )
                if timeout_seconds is None:
                    response_context = request
                    async with response_context as response:
                        raw = await response.json(content_type=None)
                        data = raw if isinstance(raw, dict) else {"data": raw}
                        if 200 <= response.status < 300:
                            return True, _unwrap_object(data, "payment", "subscription")
                        last_error = {"status": response.status, "message": data}
                        if response.status < 500:
                            return False, last_error
                else:
                    async with asyncio.timeout(timeout_seconds):
                        async with request as response:
                            raw = await response.json(content_type=None)
                            data = raw if isinstance(raw, dict) else {"data": raw}
                            if 200 <= response.status < 300:
                                return True, _unwrap_object(data, "payment", "subscription")
                            last_error = {"status": response.status, "message": data}
                            if response.status < 500:
                                return False, last_error
            except (ClientError, TimeoutError, ValueError) as exc:
                last_error = {"message": str(exc)}
            if attempt + 1 < attempts:
                await asyncio.sleep(0)
        logger.warning("RollyPay API %s %s failed: %s", normalized_method, path, last_error)
        return False, last_error

    async def create_payment(
        self,
        request: CreatePaymentRequest,
        *,
        variant: str,
    ) -> tuple[bool, dict[str, Any]]:
        if variant == "subscription":
            return await self.create_rollypay_subscription(request)
        method = METHOD_BY_VARIANT[variant]
        currency = str(request.currency or "RUB").upper()
        if currency != "RUB" and not (variant == "international" and currency == "EUR"):
            return False, {"message": "unsupported_currency"}
        payment_id = int(request.payment.payment_id)
        payload: dict[str, Any] = {
            "amount": f"{float(request.amount):.2f}",
            "payment_currency": currency,
            "order_id": f"minishop-{payment_id}",
            "description": request.description,
            "customer_id": str(request.user_id),
            "metadata": {
                "payment_db_id": payment_id,
                "user_id": int(request.user_id),
                "sale_mode": str(request.sale_mode),
                "rollypay_variant": variant,
            },
            "test": bool(self.config.TEST_MODE),
        }
        if method:
            payload["payment_method"] = method
        if self.config.TERMINAL_ID:
            payload["terminal_id"] = self.config.TERMINAL_ID
        success_url = self.config.SUCCESS_URL or self.default_return_url
        fail_url = self.config.FAIL_URL or self.default_return_url
        if success_url:
            payload["success_redirect_url"] = success_url
            payload["redirect_url"] = success_url
        if fail_url:
            payload["fail_redirect_url"] = fail_url
        return await self.api_request("POST", "/payments", json_body=payload)

    async def get_payment(self, payment_id: str) -> tuple[bool, dict[str, Any]]:
        return await self.api_request(
            "GET",
            f"/payments/{str(payment_id).strip()}",
            timeout_seconds=float(self.config.WEBHOOK_LOOKUP_TIMEOUT_SECONDS),
        )

    async def try_reuse_pending_payment(self, payment: Any) -> str | None:
        remote_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not remote_id or not payment_url:
            return None
        success, remote = await self.get_payment(remote_id)
        if not success or str(remote.get("status") or "").lower() not in {
            "created",
            "processing",
        }:
            return None
        if _order_payment_id(remote.get("order_id")) != int(payment.payment_id):
            return None
        return payment_url

    def verify_webhook(self, raw_body: bytes, timestamp: str, signature: str) -> bool:
        try:
            sent_at = int(timestamp)
        except (TypeError, ValueError):
            return False
        if abs(int(time.time()) - sent_at) > int(self.config.WEBHOOK_TOLERANCE_SECONDS):
            return False
        message = timestamp.encode("ascii") + b"." + raw_body
        expected = hmac.new(
            str(self.config.SIGNING_SECRET or "").encode(), message, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected.lower(), str(signature or "").strip().lower())

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="rollypay_disabled")
        raw_body = await request.read()
        if not self.verify_webhook(
            raw_body,
            request.headers.get("X-Timestamp", ""),
            request.headers.get("X-Signature", ""),
        ):
            return web.Response(status=401, text="invalid_signature")
        try:
            payload = json.loads(raw_body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return web.Response(status=400, text="bad_request")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad_request")
        event = str(payload.get("event") or payload.get("type") or "").lower()
        if event in {"payout.completed", "refund_request.completed"}:
            return web.Response(text="ok")
        event_data = payload.get("data")
        if not isinstance(event_data, dict):
            event_data = payload
        nested_payment = event_data.get("payment") or event_data.get("object")
        if not isinstance(nested_payment, dict):
            nested_payment = {}
        payment_id = str(
            first_value(nested_payment, "payment_id", "id")
            or first_value(event_data, "payment_id", "id")
            or first_value(payload, "payment_id")
            or ""
        ).strip()
        if not payment_id:
            return web.Response(status=400, text="missing_payment_id")
        success, remote = await self.get_payment(payment_id)
        if not success:
            # A non-2xx response asks RollyPay to retry; remote lookup is authoritative.
            return web.Response(status=503, text="lookup_failed")
        if str(remote.get("payment_id") or remote.get("id") or "") != payment_id:
            return web.Response(status=400, text="payment_id_mismatch")
        if remote.get("subscription_id"):
            return await self.handle_subscription_payment(remote)
        return await self._handle_one_off_payment(remote)

    async def _handle_one_off_payment(self, remote: dict[str, Any]) -> web.Response:
        remote_id = str(remote.get("payment_id") or remote.get("id") or "").strip()
        local_id = _order_payment_id(remote.get("order_id"))
        if local_id is None:
            return web.Response(status=400, text="order_id_mismatch")
        async with self.async_session_factory() as session:
            payment = await payment_dal.get_payment_by_db_id(session, local_id)
            if payment is None or str(payment.provider or "").lower() not in ONE_OFF_PROVIDERS:
                return web.Response(status=404, text="payment_not_found")
            if payment.provider_payment_id and str(payment.provider_payment_id) != remote_id:
                return web.Response(status=400, text="payment_id_mismatch")
            if bool(remote.get("test")) and int(payment.user_id) not in set(
                self.settings.ADMIN_IDS or []
            ):
                return web.Response(status=403, text="test_payment_forbidden")
            if not payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=remote.get("amount"),
                received_currency=remote.get("currency") or remote.get("payment_currency"),
                places=2,
            ):
                return web.Response(status=400, text="amount_mismatch")
            status = str(remote.get("status") or "").lower()
            if status == "paid":
                claimed = await payment_dal.claim_payment_finalization(
                    session, int(payment.payment_id), provider_payment_id=remote_id
                )
                if claimed is None:
                    return web.Response(text="ok")
                sale_mode = claimed.sale_mode or (
                    "traffic" if self.settings.traffic_sale_mode else "subscription"
                )
                units = payment_units_for_activation(claimed, sale_mode)
                outcome = await finalize_successful_payment(
                    PaymentSuccessRequest(
                        bot=self.bot,
                        settings=self.settings,
                        i18n=self.i18n,
                        session=session,
                        subscription_service=self.subscription_service,
                        referral_service=self.referral_service,
                        payment=claimed,
                        user_id=int(claimed.user_id),
                        amount=float(claimed.amount),
                        currency=str(claimed.currency),
                        sale_mode=sale_mode,
                        months=units,
                        traffic_amount=float(units),
                        provider_subscription=str(claimed.provider),
                        provider_notification="rollypay",
                        log_prefix="RollyPay webhook",
                    )
                )
                return (
                    web.Response(text="ok")
                    if outcome is not None
                    else web.Response(status=500, text="processing_error")
                )
            if status in TERMINAL_FAILURE_STATUSES:
                await payment_dal.update_provider_payment_and_status(
                    session, int(payment.payment_id), remote_id, "canceled"
                )
                await session.commit()
                await notify_user_payment_failed(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    payment=payment,
                )
                return web.Response(text="ok")
            if status in REVERSAL_STATUSES:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    int(payment.payment_id),
                    remote_id,
                    REVERSAL_STATUSES[status],
                )
                await session.commit()
                return web.Response(text="ok")
            return web.Response(status=202, text="pending")


async def rollypay_webhook_route(request: web.Request) -> web.Response:
    service = app_required(request, "rollypay_service", RollyPayService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_rollypay_router")


@router.callback_query(
    F.data.startswith("pay_rollypay_all:")
    | F.data.startswith("pay_rollypay_sbp:")
    | F.data.startswith("pay_rollypay_card:")
    | F.data.startswith("pay_rollypay_intl:")
    | F.data.startswith("pay_rollypay_crypto:")
    | F.data.startswith("pay_rollypay_sub:")
)
async def pay_rollypay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    rollypay_service: RollyPayService,
    session: AsyncSession,
) -> None:
    prefix, _, _ = (callback.data or "").partition(":")
    await run_callback_payment(
        _DESCRIPTORS_BY_PREFIX[prefix],
        callback,
        settings,
        i18n_data,
        rollypay_service,
        session,
    )


def create_service(ctx: ServiceFactoryContext) -> RollyPayService:
    bundle = ctx.config_for("rollypay_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, RollyPayConfig) else RollyPayConfig()
    )
    return RollyPayService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


def _context_for_variant(variant: str) -> Any:
    def callback_context(
        callback: types.CallbackQuery, parts: Any, service: RollyPayService
    ) -> dict[str, Any]:
        return {"rollypay_variant": variant, "source": "callback"}

    return callback_context


def _webapp_context_for_variant(variant: str) -> Any:
    def webapp_context(ctx: WebAppPaymentContext) -> dict[str, Any]:
        return {
            "rollypay_variant": variant,
            "source": "webapp",
            "traffic_gb": format_number_for_payload(ctx.traffic_gb),
            "hwid_device_count": ctx.hwid_device_count,
        }

    return webapp_context


async def _create_payment(
    service: RollyPayService, request: CreatePaymentRequest
) -> tuple[bool, dict[str, Any]]:
    variant = str((request.provider_context or {}).get("rollypay_variant") or "all_methods")
    return await service.create_payment(request, variant=variant)


async def _reuse_with_context(
    service: RollyPayService,
    payment: Any,
    context: dict[str, Any] | None,
) -> str | None:
    if (context or {}).get("rollypay_variant") == "subscription":
        return await service.try_reuse_pending_subscription(payment)
    return await service.try_reuse_pending_payment(payment)


def _extract_url(data: dict[str, Any]) -> str | None:
    return first_value(data, "pay_url", "payment_url", "url")


def _extract_id(data: dict[str, Any]) -> str | None:
    return first_value(data, "payment_id", "subscription_id", "id") if _extract_url(data) else None


def _enabled(attr: str) -> Any:
    return lambda config: bool(
        getattr(config, "ENABLED", False)
        and not getattr(config, "TEST_MODE", False)
        and getattr(config, attr, False)
    )


def _admin_enabled(enabled_attr: str, admin_attr: str, *, allow_test: bool = True) -> Any:
    return lambda config: bool(
        getattr(config, "ENABLED", False)
        and (
            getattr(config, admin_attr, False)
            or (
                allow_test
                and getattr(config, "TEST_MODE", False)
                and getattr(config, enabled_attr, False)
            )
        )
    )


def _available(variant: str) -> Any:
    enabled_attr, admin_attr = _TOGGLES[variant]

    def predicate(service: RollyPayService) -> bool:
        if not service.configured:
            return False
        if variant == "subscription":
            return bool(service.subscriptions_enabled)
        return bool(
            getattr(service.config, enabled_attr, False)
            or getattr(service.config, admin_attr, False)
        )

    return predicate


_TOGGLES = {
    "all_methods": ("ALL_METHODS_ENABLED", "ALL_METHODS_ADMIN_ONLY_ENABLED"),
    "sbp": ("SBP_ENABLED", "SBP_ADMIN_ONLY_ENABLED"),
    "card": ("CARD_ENABLED", "CARD_ADMIN_ONLY_ENABLED"),
    "international": ("INTERNATIONAL_ENABLED", "INTERNATIONAL_ADMIN_ONLY_ENABLED"),
    "crypto": ("CRYPTO_ENABLED", "CRYPTO_ADMIN_ONLY_ENABLED"),
    "subscription": ("SUBSCRIPTION_ENABLED", "SUBSCRIPTION_ADMIN_ONLY_ENABLED"),
}


def _spec(
    *,
    id: str,
    provider_key: str,
    variant: str,
    callback_prefix: str,
    webapp_label: str,
    webapp_labels: dict[str, str],
    telegram_labels: dict[str, str],
    icon: str,
    emoji: str,
    currencies: tuple[str, ...] = ("RUB",),
    first: bool = False,
    recurring: bool = False,
) -> PaymentProviderSpec:
    enabled_attr, admin_attr = _TOGGLES[variant]
    enabled_predicate = _enabled(enabled_attr)
    admin_predicate = _admin_enabled(enabled_attr, admin_attr, allow_test=not recurring)
    if recurring:
        enabled_predicate = lambda config: bool(
            getattr(config, "TERMINAL_ID", "") and _enabled(enabled_attr)(config)
        )
        admin_predicate = lambda config: bool(
            getattr(config, "TERMINAL_ID", "")
            and _admin_enabled(enabled_attr, admin_attr, allow_test=False)(config)
        )
    return PaymentProviderSpec(
        id=id,
        provider_key=provider_key,
        label="RollyPay",
        webapp_label=webapp_label,
        webapp_labels=webapp_labels,
        webapp_icon=icon,
        logo_url="/provider-logos/rollypay.png",
        telegram_labels=telegram_labels,
        telegram_emoji=emoji,
        pending_status=PENDING_STATUS,
        enabled=enabled_predicate,
        admin_only_enabled=admin_predicate,
        enabled_manifest_key=f"ROLLYPAY_{enabled_attr}",
        admin_only_manifest_key=f"ROLLYPAY_{admin_attr}",
        admin_only_config_attr=admin_attr,
        service_key="rollypay_service",
        callback_prefix=callback_prefix,
        aliases=("rollypay",) if id == "rollypay" else (),
        router=router if first else None,
        create_service=create_service if first else None,
        webhook_path=(lambda source: "/webhook/rollypay") if first else None,
        webhook_route=rollypay_webhook_route if first else None,
        create_webapp_payment=_WEBAPP_FACTORIES[variant],
        reuse_webapp_payment=reuse_webapp_payment,
        config_class=RollyPayConfig,
        manifest_fields=CONFIG_MANIFEST if first else (),
        manages_recurring=recurring,
        supported_currencies=currencies,
        payment_context_resolver=subscription_context_supported if recurring else None,
        checkout_promo_resolver=subscription_promo_supported if recurring else None,
        supports_checkout_addons=not recurring,
        currency_support_note=(
            "RollyPay recurring SBP subscriptions are charged in RUB and support "
            "1-month, quarterly and annual Core periods."
            if recurring
            else "RollyPay accepts RUB; the international-card method also accepts EUR."
        ),
        info_url="https://rollypay.io/",
        currency_support_url="https://docs.rollypay.io/",
    )


async def create_all_methods_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_ALL_METHODS_DESCRIPTOR, ctx)


async def create_sbp_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_SBP_DESCRIPTOR, ctx)


async def create_card_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_CARD_DESCRIPTOR, ctx)


async def create_international_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_INTERNATIONAL_DESCRIPTOR, ctx)


async def create_crypto_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_CRYPTO_DESCRIPTOR, ctx)


async def create_subscription_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_SUBSCRIPTION_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTORS_BY_METHOD[ctx.method], ctx, payment)


_WEBAPP_FACTORIES = {
    "all_methods": create_all_methods_webapp_payment,
    "sbp": create_sbp_webapp_payment,
    "card": create_card_webapp_payment,
    "international": create_international_webapp_payment,
    "crypto": create_crypto_webapp_payment,
    "subscription": create_subscription_webapp_payment,
}

ALL_METHODS_SPEC = _spec(
    id="rollypay",
    provider_key="rollypay",
    variant="all_methods",
    callback_prefix="pay_rollypay_all",
    webapp_label="RollyPay · All methods",
    webapp_labels={"ru": "All payment methods", "en": "All payment methods"},
    telegram_labels={"ru": "Choose payment method", "en": "Choose payment method"},
    icon="WalletCards",
    emoji="💳",
    first=True,
)
SBP_SPEC = _spec(
    id="rollypay_sbp",
    provider_key="rollypay_sbp",
    variant="sbp",
    callback_prefix="pay_rollypay_sbp",
    webapp_label="RollyPay · SBP",
    webapp_labels={"ru": "SBP", "en": "SBP"},
    telegram_labels={"ru": "Pay via SBP", "en": "Pay via SBP"},
    icon="Landmark",
    emoji="🏦",
)
CARD_SPEC = _spec(
    id="rollypay_card",
    provider_key="rollypay_card",
    variant="card",
    callback_prefix="pay_rollypay_card",
    webapp_label="RollyPay · Card",
    webapp_labels={"ru": "Bank card", "en": "Bank card"},
    telegram_labels={"ru": "Pay by card", "en": "Pay by card"},
    icon="CreditCard",
    emoji="💳",
)
INTERNATIONAL_SPEC = _spec(
    id="rollypay_international",
    provider_key="rollypay_international",
    variant="international",
    callback_prefix="pay_rollypay_intl",
    webapp_label="RollyPay · International card",
    webapp_labels={"ru": "International card", "en": "International card"},
    telegram_labels={"ru": "Pay by international card", "en": "Pay by international card"},
    icon="Globe2",
    emoji="🌍",
    currencies=("RUB", "EUR"),
)
CRYPTO_SPEC = _spec(
    id="rollypay_crypto",
    provider_key="rollypay_crypto",
    variant="crypto",
    callback_prefix="pay_rollypay_crypto",
    webapp_label="RollyPay · Crypto",
    webapp_labels={"ru": "Crypto", "en": "Crypto"},
    telegram_labels={"ru": "Pay with crypto", "en": "Pay with crypto"},
    icon="Bitcoin",
    emoji="🪙",
)
SUBSCRIPTION_SPEC = _spec(
    id=ROLLYPAY_SUBSCRIPTION_PROVIDER,
    provider_key=ROLLYPAY_SUBSCRIPTION_PROVIDER,
    variant="subscription",
    callback_prefix="pay_rollypay_sub",
    webapp_label="RollyPay · Subscription",
    webapp_labels={"ru": "SBP subscription", "en": "SBP subscription"},
    telegram_labels={"ru": "Subscribe via SBP", "en": "Subscribe via SBP"},
    icon="RefreshCw",
    emoji="🔁",
    recurring=True,
)
SPECS = (
    ALL_METHODS_SPEC,
    SBP_SPEC,
    CARD_SPEC,
    INTERNATIONAL_SPEC,
    CRYPTO_SPEC,
    SUBSCRIPTION_SPEC,
)


def _descriptor(spec: PaymentProviderSpec, variant: str) -> LinkPaymentDescriptor[RollyPayService]:
    return LinkPaymentDescriptor(
        spec=spec,
        provider_key=spec.provider_key,
        pending_status=PENDING_STATUS,
        display_name="RollyPay",
        log_prefix="rollypay",
        service_app_key="rollypay_service",
        service_type=RollyPayService,
        create=_create_payment,
        reuse=lambda service, payment: service.try_reuse_pending_payment(payment),
        reuse_with_context=_reuse_with_context,
        extract_url=_extract_url,
        extract_provider_id=_extract_id,
        callback_context=_context_for_variant(variant),
        webapp_context=_webapp_context_for_variant(variant),
        webapp_available=_available(variant),
    )


_ALL_METHODS_DESCRIPTOR = _descriptor(ALL_METHODS_SPEC, "all_methods")
_SBP_DESCRIPTOR = _descriptor(SBP_SPEC, "sbp")
_CARD_DESCRIPTOR = _descriptor(CARD_SPEC, "card")
_INTERNATIONAL_DESCRIPTOR = _descriptor(INTERNATIONAL_SPEC, "international")
_CRYPTO_DESCRIPTOR = _descriptor(CRYPTO_SPEC, "crypto")
_SUBSCRIPTION_DESCRIPTOR = _descriptor(SUBSCRIPTION_SPEC, "subscription")
_DESCRIPTORS_BY_METHOD = {
    spec.id: descriptor
    for spec, descriptor in zip(
        SPECS,
        (
            _ALL_METHODS_DESCRIPTOR,
            _SBP_DESCRIPTOR,
            _CARD_DESCRIPTOR,
            _INTERNATIONAL_DESCRIPTOR,
            _CRYPTO_DESCRIPTOR,
            _SUBSCRIPTION_DESCRIPTOR,
        ),
        strict=True,
    )
}
_DESCRIPTORS_BY_PREFIX = {
    spec.callback_prefix: _DESCRIPTORS_BY_METHOD[spec.id] for spec in SPECS if spec.callback_prefix
}
_DESCRIPTOR = _ALL_METHODS_DESCRIPTOR


__all__ = [
    "ALL_METHODS_SPEC",
    "CARD_SPEC",
    "CRYPTO_SPEC",
    "INTERNATIONAL_SPEC",
    "SBP_SPEC",
    "SPECS",
    "SUBSCRIPTION_SPEC",
    "RollyPayService",
    "create_service",
    "rollypay_webhook_route",
    "router",
]
