import logging
from typing import Any, Optional

from aiogram import F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import payment_dal

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from ..shared import (
    build_payment_record_payload,
    create_webapp_payment_record,
    describe_payment,
    finalize_webapp_link_payment,
    first_value,
    make_translator,
    notify_callback_parse_error,
    notify_payment_record_failure,
    notify_service_unavailable,
    parse_payment_callback,
    payment_failed,
    payment_unavailable,
    quote_hwid_callback_parts,
    render_link_or_fail,
)
from ..shared.app_context import app_optional, app_required
from .config import (
    PAYKILLA_DEFAULT_EXCHANGE_RATE_URL,
    PAYKILLA_DEFAULT_INVOICE_CURRENCIES,
    PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT,
    PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY,
    PAYKILLA_DEFAULT_PAYMENT_CURRENCIES,
    PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES,
    PaykillaConfig,
    PaykillaPresentation,
    _clean_paykilla_text,
    _paykilla_payment_amount_supported,
    _paykilla_payment_minimum_metadata,
    _sign_query,
    _webhook_signature,
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
    if not SPEC.is_usable_for_payment_amount(settings, currency_code, parts.price):
        logging.warning(
            "Paykilla callback rejected below-minimum payment (amount=%s currency=%s user=%s).",
            parts.price,
            currency_code,
            callback.from_user.id,
        )
        await notify_service_unavailable(callback, translator)
        return
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
        provider_response=response_data,
        log_prefix=_LOG,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = app_required(ctx.request, "settings", Settings)
    service: PaykillaService = app_required(ctx.request, "paykilla_service", PaykillaService)
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
        provider_response=response_data,
        log_prefix="Paykilla",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> Optional[str]:
    service = app_optional(ctx.request, "paykilla_service", PaykillaService)
    if not service or not service.configured:
        return None
    return await service.try_reuse_pending_invoice(payment)


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

__all__ = [
    "PAYKILLA_DEFAULT_EXCHANGE_RATE_URL",
    "PAYKILLA_DEFAULT_INVOICE_CURRENCIES",
    "PAYKILLA_DEFAULT_MIN_PAYMENT_AMOUNT",
    "PAYKILLA_DEFAULT_MIN_PAYMENT_CURRENCY",
    "PAYKILLA_DEFAULT_PAYMENT_CURRENCIES",
    "PAYKILLA_DEFAULT_SUPPORTED_CURRENCIES",
    "PaykillaConfig",
    "PaykillaPresentation",
    "PaykillaService",
    "SPEC",
    "_clean_paykilla_text",
    "_paykilla_payment_amount_supported",
    "_paykilla_payment_minimum_metadata",
    "_sign_query",
    "_webhook_signature",
    "create_service",
    "create_webapp_payment",
    "pay_paykilla_callback_handler",
    "paykilla_webhook_route",
    "reuse_webapp_payment",
    "router",
]
