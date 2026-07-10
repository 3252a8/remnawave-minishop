from __future__ import annotations

import logging
from typing import Any

from db.dal import payment_dal, user_billing_dal

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    parse_supported_currency_codes,
)
from ..shared import PAYMENT_STATUS_PENDING_FINALIZATION
from .config import (
    StripeConfig,
    StripePresentation,
    _stripe_amount_to_minor_units,
)
from .payments import create_webapp_payment, reuse_webapp_payment
from .router import router
from .service import StripeService
from .webhook import stripe_webhook_route

logger = logging.getLogger(__name__)
_LOG = "stripe"


def create_service(ctx: ServiceFactoryContext) -> StripeService:
    bundle = ctx.config_for("stripe_service")
    config = bundle.config if bundle and isinstance(bundle.config, StripeConfig) else StripeConfig()
    return StripeService(
        bot=ctx.bot,
        settings=ctx.settings,
        config=config,
        i18n=ctx.i18n,
        async_session_factory=ctx.async_session_factory,
        subscription_service=ctx.subscription_service,
        referral_service=ctx.referral_service,
        default_return_url=ctx.bot_username_for_default_return,
    )


def _supported_currencies(config: Any) -> tuple[str, ...] | None:
    values = parse_supported_currency_codes(getattr(config, "SUPPORTED_CURRENCIES", None))
    return values or None


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Stripe",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_STRIPE_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_STRIPE_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_STRIPE_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_STRIPE_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_STRIPE_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_STRIPE_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("STRIPE_ENABLED", "bool", "Enabled", subsection="Stripe", attr="ENABLED"),
    ProviderManifestField(
        "STRIPE_SECRET_KEY",
        "string",
        "Secret key",
        description="Stripe secret API key used for Checkout Sessions and PaymentIntents.",
        subsection="Stripe",
        secret=True,
        attr="SECRET_KEY",
    ),
    ProviderManifestField(
        "STRIPE_WEBHOOK_SECRET",
        "string",
        "Webhook secret",
        description="Stripe endpoint signing secret that starts with whsec_.",
        subsection="Stripe",
        secret=True,
        attr="WEBHOOK_SECRET",
    ),
    ProviderManifestField(
        "STRIPE_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.stripe.com",
        subsection="Stripe",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "STRIPE_RETURN_URL",
        "url",
        "Return URL",
        subsection="Stripe",
        attr="RETURN_URL",
    ),
    ProviderManifestField(
        "STRIPE_CANCEL_URL",
        "url",
        "Cancel URL",
        subsection="Stripe",
        attr="CANCEL_URL",
    ),
    ProviderManifestField(
        "STRIPE_PAYMENT_METHOD_TYPES",
        "string",
        "Payment method types",
        description="Comma-separated Checkout payment method types. Default: card.",
        placeholder="card",
        subsection="Stripe",
        attr="PAYMENT_METHOD_TYPES",
    ),
    ProviderManifestField(
        "STRIPE_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Optional comma-separated presentment currencies allowed for this Stripe account. "
            "Empty means no local filter."
        ),
        placeholder="USD,EUR,GBP",
        subsection="Stripe",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "STRIPE_RECURRING_ENABLED",
        "bool",
        "Recurring payments",
        description="Save Checkout payment methods for off-session PaymentIntent auto-renewal.",
        subsection="Stripe",
        attr="RECURRING_ENABLED",
    ),
    ProviderManifestField(
        "STRIPE_VERIFY_WEBHOOK_SIGNATURE",
        "bool",
        "Verify webhook signature",
        description="Verify the Stripe-Signature header using STRIPE_WEBHOOK_SECRET.",
        subsection="Stripe",
        attr="VERIFY_WEBHOOK_SIGNATURE",
    ),
    ProviderManifestField(
        "STRIPE_WEBHOOK_TOLERANCE_SECONDS",
        "int",
        "Webhook tolerance seconds",
        description="Allowed clock skew for Stripe webhook signatures.",
        subsection="Stripe",
        min=0,
        max=86400,
        attr="WEBHOOK_TOLERANCE_SECONDS",
    ),
)


SPEC = PaymentProviderSpec(
    id="stripe",
    provider_key="stripe",
    label="Stripe",
    webapp_label="Stripe",
    webapp_labels={"ru": "Stripe", "en": "Stripe"},
    webapp_icon="CreditCard",
    logo_url="/provider-logos/stripe.png",
    telegram_labels={"ru": "Stripe", "en": "Stripe"},
    emoji="",
    telegram_emoji="",
    pending_status="pending_stripe",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="stripe_service",
    callback_prefix="pay_stripe",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/stripe",
    webhook_route=stripe_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=StripeConfig,
    presentation_class=StripePresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supports_recurring=True,
    supported_currencies_resolver=_supported_currencies,
    currency_support_note=(
        "Stripe supports many presentment currencies, but availability depends on the account "
        "country and enabled payment methods. Use STRIPE_SUPPORTED_CURRENCIES to restrict UI."
    ),
    info_url="https://stripe.com/",
    currency_support_url="https://docs.stripe.com/currencies",
)

__all__ = [
    "PAYMENT_STATUS_PENDING_FINALIZATION",
    "SPEC",
    "StripeConfig",
    "StripePresentation",
    "StripeService",
    "_stripe_amount_to_minor_units",
    "create_service",
    "create_webapp_payment",
    "logger",
    "payment_dal",
    "reuse_webapp_payment",
    "router",
    "stripe_webhook_route",
    "user_billing_dal",
]
