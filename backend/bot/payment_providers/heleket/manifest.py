from ..base import ProviderManifestField
from .constants import HELEKET_DEFAULT_SUPPORTED_CURRENCIES

_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Heleket",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_HELEKET_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_HELEKET_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_HELEKET_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Bitcoin",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_HELEKET_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_HELEKET_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_HELEKET_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "🪙",
            "TELEGRAM_EMOJI",
        ),
    )
)


_CONFIG_MANIFEST = (
    ProviderManifestField(
        "HELEKET_ENABLED", "bool", "Enabled", subsection="Heleket", attr="ENABLED"
    ),
    ProviderManifestField(
        "HELEKET_MERCHANT_ID",
        "string",
        "Merchant ID",
        subsection="Heleket",
        secret=True,
        attr="MERCHANT_ID",
    ),
    ProviderManifestField(
        "HELEKET_API_KEY",
        "string",
        "Payment API key",
        subsection="Heleket",
        secret=True,
        attr="API_KEY",
    ),
    ProviderManifestField(
        "HELEKET_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.heleket.com",
        subsection="Heleket",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "HELEKET_CURRENCY",
        "string",
        "Invoice currency",
        description="Fiat or crypto code (RUB, USD, USDT).",
        placeholder="RUB",
        subsection="Heleket",
        attr="CURRENCY",
    ),
    ProviderManifestField(
        "HELEKET_SUPPORTED_CURRENCIES",
        "string",
        "Supported currencies",
        description=(
            "Comma-separated invoice currencies allowed for Heleket in this shop. "
            "Heleket can reject unsupported codes per account/service."
        ),
        placeholder=HELEKET_DEFAULT_SUPPORTED_CURRENCIES,
        subsection="Heleket",
        attr="SUPPORTED_CURRENCIES",
    ),
    ProviderManifestField(
        "HELEKET_TO_CURRENCY",
        "string",
        "Target crypto",
        description="Optional target cryptocurrency for conversion.",
        subsection="Heleket",
        attr="TO_CURRENCY",
    ),
    ProviderManifestField(
        "HELEKET_NETWORK",
        "string",
        "Blockchain network",
        description="Optional blockchain network code (tron, bsc, eth).",
        subsection="Heleket",
        attr="NETWORK",
    ),
    ProviderManifestField(
        "HELEKET_RETURN_URL", "url", "Return URL", subsection="Heleket", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "HELEKET_SUCCESS_URL", "url", "Success URL", subsection="Heleket", attr="SUCCESS_URL"
    ),
    ProviderManifestField(
        "HELEKET_LIFETIME_SECONDS",
        "int",
        "Invoice lifetime (seconds)",
        description="300..43200; Heleket defaults to 3600.",
        subsection="Heleket",
        min=300,
        max=43200,
        attr="LIFETIME_SECONDS",
    ),
    ProviderManifestField(
        "HELEKET_VERIFY_WEBHOOK_SIGNATURE",
        "bool",
        "Verify webhook signature",
        subsection="Heleket",
        attr="VERIFY_WEBHOOK_SIGNATURE",
    ),
    ProviderManifestField(
        "HELEKET_TRUSTED_IPS",
        "string",
        "Trusted IPs",
        description="Comma-separated IP addresses accepted for Heleket webhooks.",
        subsection="Heleket",
        attr="TRUSTED_IPS",
    ),
)
