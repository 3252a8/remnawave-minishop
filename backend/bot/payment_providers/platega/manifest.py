"""Admin settings manifest fragments declared by the Platega provider.

Kept out of ``service.py`` so the service module stays about payment flow: the
Platega package now carries three visible buttons (SBP, crypto, recurring SBP
subscription) and their presentation overrides, which is a lot of static data.
"""

from __future__ import annotations

from ..base import ProviderManifestField


def platega_presentation_manifest(
    subsection: str,
    default_icon: str,
    prefix: str,
) -> tuple[ProviderManifestField, ...]:
    return tuple(
        ProviderManifestField(
            key=f"PAYMENT_{prefix}_{suffix_key}",
            type=type_,
            label=label,
            description=description,
            placeholder=placeholder,
            subsection=subsection,
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


CONFIG_MANIFEST: tuple[ProviderManifestField, ...] = (
    ProviderManifestField(
        "PLATEGA_ENABLED", "bool", "Enabled", subsection="Platega", attr="ENABLED"
    ),
    ProviderManifestField(
        "PLATEGA_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://app.platega.io",
        subsection="Platega",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "PLATEGA_MERCHANT_ID", "string", "Merchant ID", subsection="Platega", attr="MERCHANT_ID"
    ),
    ProviderManifestField(
        "PLATEGA_SECRET", "string", "Secret", subsection="Platega", secret=True, attr="SECRET"
    ),
    ProviderManifestField(
        "PLATEGA_PAYMENT_METHOD",
        "int",
        "Payment method (legacy)",
        subsection="Platega",
        attr="PAYMENT_METHOD",
    ),
    ProviderManifestField(
        "PLATEGA_SBP_ENABLED", "bool", "SBP button", subsection="Platega", attr="SBP_ENABLED"
    ),
    ProviderManifestField(
        "PLATEGA_SBP_METHOD", "int", "SBP method ID", subsection="Platega", attr="SBP_METHOD"
    ),
    ProviderManifestField(
        "PLATEGA_CRYPTO_ENABLED",
        "bool",
        "Crypto button",
        subsection="Platega",
        attr="CRYPTO_ENABLED",
    ),
    ProviderManifestField(
        "PLATEGA_CRYPTO_METHOD",
        "int",
        "Crypto method ID",
        subsection="Platega",
        attr="CRYPTO_METHOD",
    ),
    ProviderManifestField(
        "PLATEGA_SUBSCRIPTION_ENABLED",
        "bool",
        "Recurring SBP subscription button",
        description=(
            "Sells a Platega SBP subscription mandate instead of a one-off charge. "
            "Platega charges the payer every period and reports each attempt to the "
            "Platega webhook; only 1-month and 12-month periods map to a Platega "
            "interval, and promo-discounted checkouts are excluded because a mandate "
            "repeats the same amount forever."
        ),
        subsection="Platega",
        attr="SUBSCRIPTION_ENABLED",
    ),
    ProviderManifestField(
        "PLATEGA_SUBSCRIPTION_METHOD",
        "int",
        "Subscription method ID",
        description="Platega paymentMethod used for recurring SBP subscriptions (6).",
        subsection="Platega",
        attr="SUBSCRIPTION_METHOD",
    ),
    ProviderManifestField(
        "PLATEGA_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Comma-separated payment currencies enabled for your Platega merchant. "
            "Public docs expose currency per method/limits but do not publish a fixed global list."
        ),
        placeholder="RUB",
        subsection="Platega",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "PLATEGA_RETURN_URL", "url", "Return URL", subsection="Platega", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "PLATEGA_FAILED_URL", "url", "Failed URL", subsection="Platega", attr="FAILED_URL"
    ),
)
