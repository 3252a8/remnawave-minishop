from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlencode

from aiogram import Bot, F, Router, types
from aiohttp import web
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
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
from db.dal import payment_dal

from ..base import (
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
from ..shared import (
    PAYMENT_STATUS_PENDING_FINALIZATION,
    CreatePaymentRequest,
    CreateResult,
    LinkPaymentDescriptor,
    PaymentSuccessRequest,
    decimal_amounts_equal,
    finalize_successful_payment,
    first_value,
    format_decimal_amount,
    lookup_payment_by_order_or_provider_id,
    payment_units_for_activation,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from ..shared.app_context import app_required

_LOG = "epay"
_SUCCESS_STATUSES = {"TRADE_SUCCESS"}


def calculate_signature(params: Mapping[str, Any], key: str) -> str:
    """Return the common 易支付 MD5 signature.

    Most 易支付-compatible gateways sign non-empty params sorted by key,
    excluding ``sign`` and ``sign_type``, then append the merchant key.
    """

    pairs = []
    for param_key in sorted(params):
        if param_key in {"sign", "sign_type"}:
            continue
        value = params[param_key]
        if value is None or value == "":
            continue
        pairs.append(f"{param_key}={value}")
    sign_text = "&".join(pairs) + key
    return hashlib.md5(sign_text.encode("utf-8")).hexdigest()


class EpayConfig(ProviderEnvConfig):
    """Common 易支付 / EPay-compatible gateway settings."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="EPAY_",
        extra="ignore",
    )

    ENABLED: bool = Field(default=False)
    API_BASE_URL: Optional[str] = None
    PID: Optional[str] = None
    KEY: Optional[str] = None
    PAYMENT_TYPE: str = Field(default="alipay")
    RETURN_URL: Optional[str] = None
    SITE_NAME: Optional[str] = None
    SUPPORTED_CURRENCIES: str = Field(default="CNY")

    @field_validator("API_BASE_URL", "PID", "KEY", "RETURN_URL", "SITE_NAME", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("PAYMENT_TYPE", "SUPPORTED_CURRENCIES", mode="before")
    @classmethod
    def _strip_required(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def webhook_path(self) -> str:
        return "/webhook/epay"

    def full_webhook_url(self, base: Optional[str]) -> Optional[str]:
        if not base:
            return None
        return f"{base.rstrip('/')}{self.webhook_path}"


class EpayPresentation(ProviderEnvConfig):
    """Admin-tunable button text/icon overrides for 易支付."""

    model_config = SettingsConfigDict(
        env_file=provider_env_file(),
        env_file_encoding="utf-8",
        env_prefix="PAYMENT_EPAY_",
        extra="ignore",
    )

    WEBAPP_LABEL_RU: Optional[str] = None
    WEBAPP_LABEL_EN: Optional[str] = None
    WEBAPP_LABEL_ZH: Optional[str] = None
    WEBAPP_ICON: Optional[str] = None
    TELEGRAM_LABEL_RU: Optional[str] = None
    TELEGRAM_LABEL_EN: Optional[str] = None
    TELEGRAM_LABEL_ZH: Optional[str] = None
    TELEGRAM_EMOJI: Optional[str] = None


class EpayService:
    """Hosted payment-link integration for EPay-compatible gateways."""

    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: EpayConfig,
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
        self._default_return_url = default_return_url

        if not self.configured:
            logging.warning("EpayService initialized but not fully configured. Payments disabled.")

    @property
    def configured(self) -> bool:
        return bool(
            provider_runtime_enabled(self.config)
            and self.api_base_url
            and self.pid
            and self.sign_key
        )

    @property
    def api_base_url(self) -> str:
        return (self.config.API_BASE_URL or "").rstrip("/")

    @property
    def pid(self) -> str:
        return (self.config.PID or "").strip()

    @property
    def sign_key(self) -> str:
        return (self.config.KEY or "").strip()

    @property
    def payment_type(self) -> str:
        return (self.config.PAYMENT_TYPE or "alipay").strip().lower()

    @property
    def return_url(self) -> str:
        return (
            self.config.RETURN_URL
            or getattr(self.settings, "SUBSCRIPTION_MINI_APP_URL", None)
            or f"https://t.me/{self._default_return_url}"
        )

    @property
    def supported_currencies(self) -> tuple[str, ...]:
        parsed = parse_supported_currency_codes(self.config.SUPPORTED_CURRENCIES)
        return parsed or ("CNY",)

    def _build_payment_url(self, params: Mapping[str, Any]) -> str:
        return f"{self.api_base_url}/submit.php?{urlencode(dict(params))}"

    async def create_payment(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: Optional[str],
        description: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not self.configured:
            logging.error("EpayService is not configured. Cannot create payment.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(currency or "CNY")
        if currency_code not in self.supported_currencies:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(self.supported_currencies),
            }

        notify_url = self.config.full_webhook_url(getattr(self.settings, "WEBHOOK_BASE_URL", None))
        if not notify_url:
            return False, {"message": "webhook_base_url_required"}

        out_trade_no = str(payment_db_id)
        params: Dict[str, Any] = {
            "pid": self.pid,
            "type": self.payment_type,
            "out_trade_no": out_trade_no,
            "notify_url": notify_url,
            "return_url": self.return_url,
            "name": (description or "Subscription")[:127],
            "money": format_decimal_amount(amount),
        }
        if self.config.SITE_NAME:
            params["sitename"] = self.config.SITE_NAME
        params["sign"] = calculate_signature(params, self.sign_key)
        params["sign_type"] = "MD5"

        return True, {
            "payment_url": self._build_payment_url(params),
            "out_trade_no": out_trade_no,
            "provider_payment_id": out_trade_no,
        }

    async def try_reuse_pending_payment(self, payment: Any) -> Optional[str]:
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        provider_payment_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        if payment_url and provider_payment_id:
            return payment_url
        return None

    async def _parse_webhook_payload(self, request: web.Request) -> Dict[str, Any]:
        payload: Dict[str, Any] = {key: value for key, value in request.query.items()}
        if not request.can_read_body:
            return payload
        if request.content_type == "application/json":
            raw_body = await request.read()
            try:
                parsed = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except (UnicodeDecodeError, ValueError, TypeError):
                return payload
            if isinstance(parsed, dict):
                payload.update(parsed)
            return payload
        try:
            form = await request.post()
        except Exception:
            logging.exception("EPay webhook: failed to parse form payload.")
            return payload
        payload.update({key: value for key, value in form.items()})
        return payload

    def verify_callback_signature(self, payload: Mapping[str, Any]) -> bool:
        received = str(payload.get("sign") or "").strip()
        if not received:
            logging.warning("EPay webhook: missing signature.")
            return False
        if not self.sign_key:
            logging.error("EPay webhook: no merchant key configured.")
            return False
        expected = calculate_signature(payload, self.sign_key)
        return received.lower() == expected.lower()

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="epay_disabled")

        payload = await self._parse_webhook_payload(request)
        if not payload:
            return web.Response(status=400, text="bad_request")

        if not self.verify_callback_signature(payload):
            logging.error("EPay webhook: invalid signature.")
            return web.Response(status=403, text="invalid_signature")

        provider_payment_id = str(payload.get("trade_no") or "").strip()
        order_id_raw = payload.get("out_trade_no")
        status = str(payload.get("trade_status") or payload.get("status") or "").strip().upper()

        async with self.async_session_factory() as session:
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                order_id_raw=order_id_raw,
                provider_payment_id=provider_payment_id or None,
            )
            if not payment:
                logging.error(
                    "EPay webhook: payment not found (out_trade_no=%s, trade_no=%s)",
                    order_id_raw,
                    provider_payment_id,
                )
                return web.Response(status=404, text="payment_not_found")

            resolved_provider_id = provider_payment_id or str(order_id_raw or payment.payment_id)
            if status not in _SUCCESS_STATUSES:
                logging.info(
                    "EPay webhook: ignoring non-success status %s for payment %s.",
                    status,
                    resolved_provider_id,
                )
                return web.Response(text="success")

            if payment.status == "succeeded":
                logging.info("EPay webhook: payment %s already succeeded.", payment.payment_id)
                return web.Response(text="success")

            webhook_amount = payload.get("money")
            if webhook_amount is not None and not decimal_amounts_equal(
                webhook_amount,
                payment.amount,
            ):
                logging.error(
                    "EPay webhook: amount mismatch for payment %s (expected=%s, received=%s)",
                    payment.payment_id,
                    payment.amount,
                    webhook_amount,
                )
                return web.Response(status=400, text="amount_mismatch")

            sale_mode = payment.sale_mode or (
                "traffic" if self.settings.traffic_sale_mode else "subscription"
            )
            payment_months = payment_units_for_activation(payment, sale_mode)

            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment.payment_id,
                    resolved_provider_id,
                    PAYMENT_STATUS_PENDING_FINALIZATION,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logging.exception(
                    "EPay webhook: failed to mark payment %s as succeeded.",
                    resolved_provider_id,
                )
                return web.Response(status=500, text="processing_error")

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
                    provider_subscription="epay",
                    provider_notification="epay",
                    db_user=payment.user,
                    log_prefix="EPay webhook",
                )
            )
            if outcome is None:
                return web.Response(status=500, text="processing_error")
            return web.Response(text="success")


async def epay_webhook_route(request: web.Request) -> web.Response:
    service: EpayService = app_required(request, "epay_service", EpayService)
    return await service.webhook_route(request)


router = Router(name="user_subscription_payments_epay_router")


@router.callback_query(F.data.startswith("pay_epay:"))
async def pay_epay_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    epay_service: EpayService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, epay_service, session)


def create_service(ctx: ServiceFactoryContext) -> EpayService:
    bundle = ctx.config_for("epay_service")
    config = bundle.config if bundle and isinstance(bundle.config, EpayConfig) else EpayConfig()
    return EpayService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="EPay",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_EPAY_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_EPAY_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_EPAY_WEBAPP_LABEL_ZH",
            "string",
            "WebApp button text (ZH)",
            "Custom Chinese text shown in the Web App payment method button.",
            "易支付",
            "WEBAPP_LABEL_ZH",
        ),
        (
            "PAYMENT_EPAY_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "QrCode",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_EPAY_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_EPAY_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_EPAY_TELEGRAM_LABEL_ZH",
            "string",
            "Telegram button text (ZH)",
            "Custom Chinese text shown in Telegram bot payment buttons.",
            "易支付",
            "TELEGRAM_LABEL_ZH",
        ),
        (
            "PAYMENT_EPAY_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💳",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "EPAY_ENABLED",
        "bool",
        "Enabled",
        subsection="EPay",
        attr="ENABLED",
    ),
    ProviderManifestField(
        "EPAY_API_BASE_URL",
        "url",
        "Gateway base URL",
        description="Base URL of your 易支付-compatible gateway, without /submit.php.",
        placeholder="https://pay.example.com",
        subsection="EPay",
        attr="API_BASE_URL",
    ),
    ProviderManifestField(
        "EPAY_PID",
        "string",
        "Merchant PID",
        description="Merchant ID / pid assigned by the 易支付 gateway.",
        subsection="EPay",
        attr="PID",
    ),
    ProviderManifestField(
        "EPAY_KEY",
        "string",
        "Merchant key",
        description="MD5 signing key used for payment requests and notify callbacks.",
        subsection="EPay",
        secret=True,
        attr="KEY",
    ),
    ProviderManifestField(
        "EPAY_PAYMENT_TYPE",
        "string",
        "Payment type",
        description="Gateway payment channel, usually alipay, wxpay or qqpay.",
        placeholder="alipay",
        subsection="EPay",
        attr="PAYMENT_TYPE",
    ),
    ProviderManifestField(
        "EPAY_RETURN_URL",
        "url",
        "Return URL",
        description="Where the gateway sends the user after payment. Empty uses the Web App URL.",
        subsection="EPay",
        attr="RETURN_URL",
    ),
    ProviderManifestField(
        "EPAY_SITE_NAME",
        "string",
        "Site name",
        description="Optional site name passed to the gateway.",
        subsection="EPay",
        attr="SITE_NAME",
    ),
    ProviderManifestField(
        "EPAY_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Currencies you allow this gateway to receive. Common 易支付 gateways settle CNY only."
        ),
        placeholder="CNY",
        subsection="EPay",
        attr="SUPPORTED_CURRENCIES",
    ),
)


SPEC = PaymentProviderSpec(
    id="epay",
    provider_key="epay",
    label="易支付",
    webapp_label="易支付",
    webapp_labels={"ru": "EPay", "en": "EPay", "zh": "易支付"},
    webapp_icon="QrCode",
    telegram_labels={"ru": "EPay", "en": "EPay", "zh": "易支付"},
    telegram_emoji="💳",
    aliases=("easypay", "easy_pay", "yipay"),
    pending_status="pending_epay",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="epay_service",
    callback_prefix="pay_epay",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/epay",
    webhook_route=epay_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=EpayConfig,
    presentation_class=EpayPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies=None,
    supported_currencies_resolver=lambda config: parse_supported_currency_codes(
        getattr(config, "SUPPORTED_CURRENCIES", None)
    ),
    currency_support_note=(
        "易支付-compatible gateways usually accept CNY amounts through submit.php. "
        "If your gateway performs its own conversion, configure "
        "EPAY_SUPPORTED_CURRENCIES explicitly."
    ),
)


async def _create_payment(service: EpayService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
    )


async def _reuse_payment(service: EpayService, payment: Any) -> Optional[str]:
    return await service.try_reuse_pending_payment(payment)


_DESCRIPTOR: LinkPaymentDescriptor[EpayService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="epay",
    pending_status="pending_epay",
    display_name="EPay",
    log_prefix=_LOG,
    service_app_key="epay_service",
    service_type=EpayService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda response: first_value(response, "payment_url", "url"),
    extract_provider_id=lambda response: first_value(
        response, "provider_payment_id", "out_trade_no"
    ),
)
