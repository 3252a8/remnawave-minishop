import logging
from typing import Any

from aiogram import F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from config.tariffs_config import (
    default_payment_currency_code_for_settings,
)

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from ..shared import (
    CreatePaymentRequest,
    CreateResult,
    LinkPaymentDescriptor,
    first_value,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)
from .config import (
    PAYKILLA_DEFAULT_EXCHANGE_RATE_URL,
    PAYKILLA_DEFAULT_INVOICE_CURRENCIES,
    PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT,
    PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY,
    PAYKILLA_DEFAULT_PAYMENT_CURRENCIES,
    PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES,
    PaykillaConfig,
    PaykillaPresentation,
    _paykilla_payment_amount_supported,
    _paykilla_payment_minimum_metadata,
)
from .service import PaykillaService
from .webhook import paykilla_webhook_route

router = Router(name="user_subscription_payments_paykilla_router")
_LOG = "paykilla"


@router.callback_query(F.data.startswith("pay_paykilla:"))
async def pay_paykilla_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    paykilla_service: PaykillaService,
    session: AsyncSession,
) -> None:
    await run_callback_payment(
        _DESCRIPTOR, callback, settings, i18n_data, paykilla_service, session
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_DESCRIPTOR, ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)


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
            "Comma-separated PayKilla tickers sent as paymentCurrencies. "
            "Default: USDTTRC,BTC,ETH,USDTBSC,USDTTON."
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
        "PAYKILLA_MIN_PAYMENT_AMOUNT",
        "float",
        "Minimum payment amount",
        description=(
            "Minimum payment amount accepted through PayKilla. The value is interpreted "
            "in PAYKILLA_MIN_PAYMENT_CURRENCY and converted for tariff currencies."
        ),
        placeholder=str(PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT),
        subsection="PayKilla",
        min=0,
        attr="MIN_PAYMENT_AMOUNT",
    ),
    ProviderManifestField(
        "PAYKILLA_MIN_PAYMENT_CURRENCY",
        "string",
        "Minimum payment currency",
        description="Currency for PAYKILLA_MIN_PAYMENT_AMOUNT. Default: USD.",
        placeholder=PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY,
        subsection="PayKilla",
        attr="MIN_PAYMENT_CURRENCY",
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
    reuse_webapp_payment=reuse_webapp_payment,
    emoji="",
    config_class=PaykillaConfig,
    presentation_class=PaykillaPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supported_currencies_resolver=lambda config: getattr(
        config, "SUPPORTED_CURRENCIES", PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES
    ),
    payment_amount_resolver=_paykilla_payment_amount_supported,
    payment_minimum_resolver=_paykilla_payment_minimum_metadata,
    currency_support_note=(
        "PayKilla invoice currency and paymentCurrencies availability can depend on "
        "merchant account settings."
    ),
    currency_support_url="https://paykilla.gitbook.io/paykilla-docs/api-integration/supported-currencies",
)


async def _create_payment(service: PaykillaService, req: CreatePaymentRequest) -> CreateResult:
    return await service.create_payment_link(
        payment_db_id=req.payment.payment_id,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
        url_callback=service.config.full_webhook_url(service.settings.WEBHOOK_BASE_URL),
    )


async def _reuse_payment(service: PaykillaService, payment: Any) -> str | None:
    return await service.try_reuse_pending_invoice(payment)


def _callback_payment_allowed(
    service: PaykillaService,
    settings: Settings,
    user_id: int,
    amount: Any,
    currency: str,
) -> bool:
    allowed = SPEC.is_usable_for_payment_amount(settings, currency, amount)
    if not allowed:
        logging.warning(
            "Paykilla callback rejected below-minimum payment (amount=%s currency=%s user=%s).",
            amount,
            currency,
            user_id,
        )
    return allowed


_DESCRIPTOR: LinkPaymentDescriptor[PaykillaService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key="paykilla",
    pending_status="pending_paykilla",
    display_name="Paykilla",
    log_prefix=_LOG,
    service_app_key="paykilla_service",
    service_type=PaykillaService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=lambda r: first_value(r, "payment_url"),
    extract_provider_id=lambda r: first_value(r, "id"),
    callback_payment_allowed=_callback_payment_allowed,
    callback_reuse_enabled=False,
    webapp_currency=lambda ctx, settings, service: (
        ctx.currency or default_payment_currency_code_for_settings(settings)
    ),
)
