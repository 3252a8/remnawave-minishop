import logging
from typing import Any

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
    payment_record_amounts,
    payment_unavailable,
    quote_hwid_callback_parts,
    render_link_or_fail,
    render_payment_link,
    safe_callback_answer,
)
from ..shared.app_context import app_optional, app_required
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


def _wata_spec_for_callback_prefix(callback_prefix: str) -> PaymentProviderSpec:
    if callback_prefix == "pay_wata_crypto":
        return CRYPTO_SPEC
    return SPEC


@router.callback_query(F.data.startswith("pay_wata_crypto:"))
@router.callback_query(F.data.startswith("pay_wata:"))
async def pay_wata_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict[str, Any],
    wata_service: WataService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    translator = make_translator(i18n, current_lang)

    if not i18n or not callback.message:
        await notify_callback_parse_error(callback, translator)
        return

    callback_prefix, _, _ = (callback.data or "").partition(":")
    spec = _wata_spec_for_callback_prefix(callback_prefix)
    if not spec.is_available_to_user(
        settings,
        user_id=callback.from_user.id,
        require_configured=False,
    ):
        await notify_service_unavailable(callback, translator)
        return

    profile = wata_service.profile_for_method(spec.id) if wata_service else None
    if not wata_service or not profile or not wata_service.profile_enabled(profile.provider):
        logging.error("Wata service is not configured or unavailable.")
        await notify_service_unavailable(callback, translator)
        return

    parts = parse_payment_callback(callback.data or "")
    if not parts:
        logging.error("Invalid pay_wata data in callback: %s", callback.data)
        await notify_callback_parse_error(callback, translator)
        return
    parts, hwid_quote = await quote_hwid_callback_parts(
        session=session,
        user_id=callback.from_user.id,
        parts=parts,
        subscription_service=wata_service.subscription_service,
        currency=default_currency_key_for_settings(settings),
    )
    if not parts:
        await notify_callback_parse_error(callback, translator)
        return

    currency_code = default_payment_currency_code_for_settings(settings)
    payment_description = describe_payment(translator, parts)

    reuse_amounts = payment_record_amounts(
        months=parts.months,
        sale_mode=parts.sale_mode,
        hwid_device_count=hwid_quote.get("device_count") if hwid_quote else None,
    )
    reusable_payment = await payment_dal.find_recent_pending_provider_payment(
        session,
        user_id=callback.from_user.id,
        provider=profile.provider,
        pending_status="pending_wata",
        amount=parts.price,
        currency=currency_code,
        sale_mode=parts.sale_mode,
        months=reuse_amounts.months,
        purchased_gb=reuse_amounts.purchased_gb,
        purchased_hwid_devices=reuse_amounts.purchased_hwid_devices,
        tariff_key=reuse_amounts.tariff_key,
        since_minutes=profile.link_ttl_minutes,
    )
    if reusable_payment is not None:
        reusable_url = await wata_service.try_reuse_pending_link(reusable_payment)
        if reusable_url:
            await safe_callback_answer(callback)
            await render_payment_link(
                callback,
                translator=translator,
                current_lang=current_lang,
                i18n=i18n,
                parts=parts,
                payment_url=reusable_url,
                log_prefix=_LOG,
            )
            return

    record_payload = build_payment_record_payload(
        user_id=callback.from_user.id,
        amount=parts.price,
        currency=currency_code,
        status="pending_wata",
        description=payment_description,
        months=parts.months,
        provider=profile.provider,
        sale_mode=parts.sale_mode,
        hwid_quote=hwid_quote,
    )

    try:
        payment_record = await payment_dal.create_payment_record(session, record_payload)
        await session.commit()
    except Exception:
        await session.rollback()
        logging.exception(
            "Wata: failed to create payment record for user %s.", callback.from_user.id
        )
        await notify_payment_record_failure(callback, translator)
        return

    await safe_callback_answer(callback)

    success, response_data = await wata_service.create_payment_link(
        payment_db_id=payment_record.payment_id,
        amount=parts.price,
        currency=currency_code,
        description=payment_description,
        method=profile.provider,
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
        payment_url=first_value(response_data, "url", "paymentUrl", "payment_url"),
        provider_payment_id=first_value(response_data, "id", "paymentLinkId"),
        provider_response=response_data,
        log_prefix=_LOG,
    )


async def create_webapp_payment(ctx: WebAppPaymentContext) -> web.Response:
    settings: Settings = app_required(ctx.request, "settings", Settings)
    service: WataService = app_required(ctx.request, "wata_service", WataService)
    profile = service.profile_for_method(ctx.method) if service else None
    if not service or not profile or not service.profile_enabled(profile.provider):
        return payment_unavailable()

    currency = ctx.currency or settings.DEFAULT_CURRENCY_SYMBOL or "RUB"

    try:
        payment = await create_webapp_payment_record(
            ctx,
            amount=ctx.price,
            currency=currency,
            status="pending_wata",
            provider=profile.provider,
        )
        success, response_data = await service.create_payment_link(
            payment_db_id=payment.payment_id,
            amount=ctx.price,
            currency=currency,
            description=ctx.description,
            method=profile.provider,
        )
    except Exception:
        await ctx.session.rollback()
        logging.exception("Wata WebApp payment failed")
        return payment_failed()

    return await finalize_webapp_link_payment(
        session=ctx.session,
        payment=payment,
        api_success=success,
        payment_url=first_value(response_data, "url", "paymentUrl", "payment_url")
        if success
        else None,
        provider_payment_id=first_value(response_data, "id", "paymentLinkId"),
        provider_response=response_data,
        log_prefix="Wata",
    )


async def reuse_webapp_payment(ctx: WebAppPaymentContext, payment: Any) -> str | None:
    service = app_optional(ctx.request, "wata_service", WataService)
    profile = service.profile_for_method(ctx.method) if service else None
    if not service or not profile or not service.profile_enabled(profile.provider):
        return None
    if str(getattr(payment, "provider", "") or "").strip().lower() != profile.provider:
        return None
    return await service.try_reuse_pending_link(payment)


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
    currency_support_url="https://wata.pro/api",
)

CRYPTO_SPEC = PaymentProviderSpec(
    id=WATA_CRYPTO_PROVIDER,
    provider_key=WATA_CRYPTO_PROVIDER,
    label="Wata",
    webapp_label="Wata Crypto",
    webapp_labels={"ru": "Wata Crypto", "en": "Wata Crypto"},
    webapp_icon="Bitcoin",
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
    currency_support_url="https://wata.pro/api",
)

SPECS = (SPEC, CRYPTO_SPEC)
