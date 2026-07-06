from collections.abc import Callable
from typing import Any

from aiogram import F, Router, types
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from ..shared import (
    CreatePaymentRequest,
    LinkPaymentDescriptor,
    first_value,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
    safe_callback_answer,
)
from .config import (
    _WATA_LINK_MAX_TTL_MINUTES,
    _WATA_LINK_MIN_TTL_MINUTES,
    _WATA_SUPPORTED_CURRENCIES_DEFAULT,
    WATA_CRYPTO_PROVIDER,
    WATA_PROVIDER,
    WATA_SUPPORTED_CURRENCIES,
    WataConfig,
    WataCryptoPresentation,
    WataPresentation,
)
from .service import WataService
from .webhook import wata_webhook_route

router = Router(name="user_subscription_payments_wata_router")
_LOG = "wata"


def _wata_descriptor_for_callback_prefix(
    callback_prefix: str,
) -> LinkPaymentDescriptor[WataService]:
    if callback_prefix == "pay_wata_crypto":
        return _CRYPTO_DESCRIPTOR
    return _DESCRIPTOR


def _wata_descriptor_for_method(method: Any) -> LinkPaymentDescriptor[WataService]:
    normalized = str(method or "").strip().lower()
    if normalized in {WATA_CRYPTO_PROVIDER, "crypto"}:
        return _CRYPTO_DESCRIPTOR
    return _DESCRIPTOR


@router.callback_query(F.data.startswith("pay_wata_crypto:"))
@router.callback_query(F.data.startswith("pay_wata:"))
async def pay_wata_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    wata_service: WataService,
    session: AsyncSession,
) -> None:
    callback_prefix, _, _ = (callback.data or "").partition(":")
    await run_callback_payment(
        _wata_descriptor_for_callback_prefix(callback_prefix),
        callback,
        settings,
        i18n_data,
        wata_service,
        session=session,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    return await run_webapp_payment(_wata_descriptor_for_method(ctx.method), ctx)


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    return await run_reuse_webapp_payment(_wata_descriptor_for_method(ctx.method), ctx, payment)


def create_service(ctx: ServiceFactoryContext) -> WataService:
    bundle = ctx.config_for("wata_service")
    config = bundle.config if bundle and isinstance(bundle.config, WataConfig) else WataConfig()
    return WataService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


def _wata_presentation_manifest(default_icon: str, prefix: str) -> tuple:
    return tuple(
        ProviderManifestField(
            key=f"PAYMENT_{prefix}_{suffix_key}",
            type=type_,
            label=label,
            description=description,
            placeholder=placeholder,
            subsection="Wata",
            target="presentation",
            attr=attr,
        )
        for suffix_key, type_, label, description, placeholder, attr in (
            (
                "WEBAPP_LABEL_RU",
                "string",
                "WebApp button text (RU)",
                "Custom Russian text shown in the Web App payment method button.",
                "",
                "WEBAPP_LABEL_RU",
            ),
            (
                "WEBAPP_LABEL_EN",
                "string",
                "WebApp button text (EN)",
                "Custom English text shown in the Web App payment method button.",
                "",
                "WEBAPP_LABEL_EN",
            ),
            (
                "WEBAPP_ICON",
                "icon",
                "WebApp button icon",
                "Lucide icon name rendered inside the Web App payment method button.",
                default_icon,
                "WEBAPP_ICON",
            ),
            (
                "TELEGRAM_LABEL_RU",
                "string",
                "Telegram button text (RU)",
                "Custom Russian text shown in Telegram bot payment buttons.",
                "",
                "TELEGRAM_LABEL_RU",
            ),
            (
                "TELEGRAM_LABEL_EN",
                "string",
                "Telegram button text (EN)",
                "Custom English text shown in Telegram bot payment buttons.",
                "",
                "TELEGRAM_LABEL_EN",
            ),
            (
                "TELEGRAM_EMOJI",
                "string",
                "Telegram button emoji",
                "Emoji prepended to the Telegram bot payment button when customized.",
                "",
                "TELEGRAM_EMOJI",
            ),
        )
    )


_COMMON_CONFIG_MANIFEST_V2 = (
    ProviderManifestField(
        "WATA_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.wata.pro/api/h2h",
        subsection="Wata",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "WATA_WEBHOOK_VERIFY_SIGNATURE",
        "bool",
        "Verify webhook signature",
        subsection="Wata",
        attr="WEBHOOK_VERIFY_SIGNATURE",
    ),
    ProviderManifestField(
        "WATA_TRUSTED_IPS",
        "string",
        "Trusted IPs",
        description="Comma-separated IP addresses accepted for Wata webhooks.",
        subsection="Wata",
        attr="TRUSTED_IPS",
    ),
)

_FIAT_CONFIG_MANIFEST = (
    ProviderManifestField("WATA_ENABLED", "bool", "Enabled", subsection="Wata", attr="ENABLED"),
    ProviderManifestField(
        "WATA_API_TOKEN",
        "string",
        "API token",
        subsection="Wata",
        secret=True,
        attr="API_TOKEN",
    ),
    ProviderManifestField(
        "WATA_TERMINAL_ID",
        "string",
        "Terminal ID",
        description="Optional internal terminal identifier from the Wata merchant account.",
        subsection="Wata",
        attr="TERMINAL_ID",
    ),
    ProviderManifestField(
        "WATA_TERMINAL_PUBLIC_ID",
        "string",
        "Terminal public ID",
        description="Optional. Used to validate that Wata webhooks belong to this terminal.",
        subsection="Wata",
        attr="TERMINAL_PUBLIC_ID",
    ),
    ProviderManifestField(
        "WATA_RETURN_URL", "url", "Return URL", subsection="Wata", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "WATA_FAILED_URL", "url", "Failed URL", subsection="Wata", attr="FAILED_URL"
    ),
    ProviderManifestField(
        "WATA_LINK_TTL_MINUTES",
        "int",
        "Payment link lifetime (minutes)",
        description=(
            "15..43200; default 15 minutes. Wata requires more than 10 minutes "
            "and allows up to 30 days."
        ),
        subsection="Wata",
        min=_WATA_LINK_MIN_TTL_MINUTES,
        max=_WATA_LINK_MAX_TTL_MINUTES,
        attr="LINK_TTL_MINUTES",
    ),
    ProviderManifestField(
        "WATA_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description="Comma-separated currencies enabled for this Wata terminal.",
        placeholder=_WATA_SUPPORTED_CURRENCIES_DEFAULT,
        subsection="Wata",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "WATA_PUBLIC_KEY",
        "text",
        "Webhook public key",
        description="Optional. If empty, the backend fetches it from Wata.",
        subsection="Wata",
        secret=True,
        attr="PUBLIC_KEY",
    ),
)

_CRYPTO_CONFIG_MANIFEST = (
    ProviderManifestField(
        "WATA_CRYPTO_ENABLED",
        "bool",
        "Crypto terminal enabled",
        subsection="Wata",
        attr="CRYPTO_ENABLED",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_API_TOKEN",
        "string",
        "Crypto API token",
        subsection="Wata",
        secret=True,
        attr="CRYPTO_API_TOKEN",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_TERMINAL_ID",
        "string",
        "Crypto terminal ID",
        description="Optional internal crypto terminal identifier from the Wata merchant account.",
        subsection="Wata",
        attr="CRYPTO_TERMINAL_ID",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_TERMINAL_PUBLIC_ID",
        "string",
        "Crypto terminal public ID",
        description="Optional. Used to validate that Wata webhooks belong to the crypto terminal.",
        subsection="Wata",
        attr="CRYPTO_TERMINAL_PUBLIC_ID",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_RETURN_URL",
        "url",
        "Crypto return URL",
        description="Optional. Falls back to WATA_RETURN_URL.",
        subsection="Wata",
        attr="CRYPTO_RETURN_URL",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_FAILED_URL",
        "url",
        "Crypto failed URL",
        description="Optional. Falls back to WATA_FAILED_URL.",
        subsection="Wata",
        attr="CRYPTO_FAILED_URL",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_LINK_TTL_MINUTES",
        "int",
        "Crypto link lifetime (minutes)",
        description="Optional. Falls back to WATA_LINK_TTL_MINUTES.",
        subsection="Wata",
        min=_WATA_LINK_MIN_TTL_MINUTES,
        max=_WATA_LINK_MAX_TTL_MINUTES,
        attr="CRYPTO_LINK_TTL_MINUTES",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_SUPPORTED_CURRENCIES",
        "string",
        "Crypto supported currencies",
        description="Optional comma-separated currencies. Falls back to WATA_SUPPORTED_CURRENCIES.",
        placeholder=_WATA_SUPPORTED_CURRENCIES_DEFAULT,
        subsection="Wata",
        attr="CRYPTO_SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "WATA_CRYPTO_PUBLIC_KEY",
        "text",
        "Crypto webhook public key",
        description="Optional. Falls back to WATA_PUBLIC_KEY or fetching the key from Wata.",
        subsection="Wata",
        secret=True,
        attr="CRYPTO_PUBLIC_KEY",
    ),
)


def _source_bool(source: Any, *attrs: str) -> bool:
    for attr in attrs:
        if hasattr(source, attr):
            return bool(getattr(source, attr, False))
    return False


def _wata_profile_configured(source: Any, provider: str) -> bool:
    if isinstance(source, WataConfig):
        return source.profile_for_method(provider).configured
    if provider == WATA_CRYPTO_PROVIDER:
        return bool(
            getattr(source, "CRYPTO_API_TOKEN", None)
            or getattr(source, "WATA_CRYPTO_API_TOKEN", None)
        )
    return bool(getattr(source, "API_TOKEN", None) or getattr(source, "WATA_API_TOKEN", None))


def _wata_enabled(source: Any) -> bool:
    return _source_bool(source, "ENABLED", "WATA_ENABLED") and _wata_profile_configured(
        source,
        WATA_PROVIDER,
    )


def _wata_admin_only_enabled(source: Any) -> bool:
    return _source_bool(
        source,
        "ADMIN_ONLY_ENABLED",
        "WATA_ADMIN_ONLY_ENABLED",
    ) and _wata_profile_configured(source, WATA_PROVIDER)


def _wata_crypto_enabled(source: Any) -> bool:
    return _source_bool(
        source,
        "CRYPTO_ENABLED",
        "WATA_CRYPTO_ENABLED",
    ) and _wata_profile_configured(source, WATA_CRYPTO_PROVIDER)


def _wata_crypto_admin_only_enabled(source: Any) -> bool:
    return _source_bool(
        source,
        "CRYPTO_ADMIN_ONLY_ENABLED",
        "WATA_CRYPTO_ADMIN_ONLY_ENABLED",
    ) and _wata_profile_configured(source, WATA_CRYPTO_PROVIDER)


def _wata_supported_currencies(source: Any, provider: str) -> tuple[str, ...]:
    if isinstance(source, WataConfig):
        return source.profile_for_method(provider).supported_currencies
    return WATA_SUPPORTED_CURRENCIES


SPEC = PaymentProviderSpec(
    id=WATA_PROVIDER,
    provider_key=WATA_PROVIDER,
    label="Wata",
    webapp_label="Wata",
    webapp_labels={"ru": "Wata", "en": "Wata"},
    webapp_icon="WalletCards",
    logo_url="/provider-logos/wata.png",
    telegram_labels={"ru": "Wata", "en": "Wata"},
    telegram_emoji="💳",
    pending_status="pending_wata",
    enabled=_wata_enabled,
    admin_only_enabled=_wata_admin_only_enabled,
    service_key="wata_service",
    callback_prefix="pay_wata",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/wata",
    webhook_route=wata_webhook_route,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=WataConfig,
    presentation_class=WataPresentation,
    manifest_fields=_COMMON_CONFIG_MANIFEST_V2
    + _FIAT_CONFIG_MANIFEST
    + _wata_presentation_manifest("WalletCards", "WATA"),
    supported_currencies_resolver=lambda config: _wata_supported_currencies(
        config,
        WATA_PROVIDER,
    ),
    currency_support_note=(
        "WATA H2H payment links document RUB, USD and EUR as payment currencies; "
        "configure the currencies enabled for your terminal."
    ),
    info_url="https://wata.pro/",
    currency_support_url="https://wata.pro/api",
)

CRYPTO_SPEC = PaymentProviderSpec(
    id=WATA_CRYPTO_PROVIDER,
    provider_key=WATA_CRYPTO_PROVIDER,
    label="Wata",
    webapp_label="Wata Crypto",
    webapp_labels={"ru": "Wata Crypto", "en": "Wata Crypto"},
    webapp_icon="Bitcoin",
    logo_url="/provider-logos/wata.png",
    telegram_labels={"ru": "Wata Crypto", "en": "Wata Crypto"},
    telegram_emoji="🪙",
    pending_status="pending_wata",
    enabled=_wata_crypto_enabled,
    admin_only_enabled=_wata_crypto_admin_only_enabled,
    admin_only_config_attr="CRYPTO_ADMIN_ONLY_ENABLED",
    service_key="wata_service",
    callback_prefix="pay_wata_crypto",
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=WataConfig,
    presentation_class=WataCryptoPresentation,
    manifest_fields=_CRYPTO_CONFIG_MANIFEST + _wata_presentation_manifest("Bitcoin", "WATA_CRYPTO"),
    supported_currencies_resolver=lambda config: _wata_supported_currencies(
        config,
        WATA_CRYPTO_PROVIDER,
    ),
    currency_support_note=(
        "WATA H2H payment links document RUB, USD and EUR as payment currencies; "
        "configure the currencies enabled for your crypto terminal."
    ),
    info_url="https://wata.pro/",
    currency_support_url="https://wata.pro/api",
)

SPECS = (SPEC, CRYPTO_SPEC)


def _payment_provider(payment: Any) -> str:
    return str(getattr(payment, "provider", "") or "").strip().lower()


async def _create_payment(
    service: WataService,
    request: CreatePaymentRequest,
) -> tuple[bool, dict[str, Any]]:
    provider = _payment_provider(request.payment) or WATA_PROVIDER
    return await service.create_payment_link(
        payment_db_id=request.payment.payment_id,
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        method=provider,
    )


async def _reuse_payment(service: WataService, payment: Any) -> str | None:
    return await service.try_reuse_pending_link(payment)


def _profile_enabled(provider: str) -> Callable[[WataService], bool]:
    def enabled(service: WataService) -> bool:
        return service.profile_enabled(provider)

    return enabled


def _callback_payment_allowed(
    provider: str,
) -> Callable[[WataService, Settings, int, Any, str], bool]:
    def allowed(
        service: WataService,
        settings: Settings,
        user_id: int,
        amount: Any,
        currency: str,
    ) -> bool:
        return service.profile_enabled(provider)

    return allowed


def _callback_reuse_since_minutes(
    provider: str,
) -> Callable[[WataService, dict[str, Any] | None], int | None]:
    def ttl_minutes(service: WataService, context: dict[str, Any] | None) -> int:
        return service.profile_for_method(provider).link_ttl_minutes

    return ttl_minutes


def _reuse_allowed(provider: str) -> Callable[[Any, dict[str, Any] | None], bool]:
    def allowed(payment: Any, context: dict[str, Any] | None) -> bool:
        return _payment_provider(payment) == provider

    return allowed


def _extract_payment_url(response: dict) -> str | None:
    return first_value(response, "url", "paymentUrl", "payment_url")


def _extract_provider_id(response: dict) -> str | None:
    return first_value(response, "id", "paymentLinkId")


_DESCRIPTOR: LinkPaymentDescriptor[WataService] = LinkPaymentDescriptor(
    spec=SPEC,
    provider_key=WATA_PROVIDER,
    pending_status="pending_wata",
    display_name="Wata",
    log_prefix=_LOG,
    service_app_key="wata_service",
    service_type=WataService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=_extract_payment_url,
    extract_provider_id=_extract_provider_id,
    callback_payment_allowed=_callback_payment_allowed(WATA_PROVIDER),
    callback_before_create=safe_callback_answer,
    callback_reuse_since_minutes=_callback_reuse_since_minutes(WATA_PROVIDER),
    callback_reuse_answer=True,
    reuse_payment_allowed=_reuse_allowed(WATA_PROVIDER),
    webapp_available=_profile_enabled(WATA_PROVIDER),
)

_CRYPTO_DESCRIPTOR: LinkPaymentDescriptor[WataService] = LinkPaymentDescriptor(
    spec=CRYPTO_SPEC,
    provider_key=WATA_CRYPTO_PROVIDER,
    pending_status="pending_wata",
    display_name="Wata",
    log_prefix=_LOG,
    service_app_key="wata_service",
    service_type=WataService,
    create=_create_payment,
    reuse=_reuse_payment,
    extract_url=_extract_payment_url,
    extract_provider_id=_extract_provider_id,
    callback_payment_allowed=_callback_payment_allowed(WATA_CRYPTO_PROVIDER),
    callback_before_create=safe_callback_answer,
    callback_reuse_since_minutes=_callback_reuse_since_minutes(WATA_CRYPTO_PROVIDER),
    callback_reuse_answer=True,
    reuse_payment_allowed=_reuse_allowed(WATA_CRYPTO_PROVIDER),
    webapp_available=_profile_enabled(WATA_CRYPTO_PROVIDER),
)
