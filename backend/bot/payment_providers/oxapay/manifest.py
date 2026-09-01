from ..base import ProviderManifestField

_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="OxaPay",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_OXAPAY_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_OXAPAY_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_OXAPAY_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "Bitcoin",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_OXAPAY_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_OXAPAY_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_OXAPAY_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "🪙",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("OXAPAY_ENABLED", "bool", "Enabled", subsection="OxaPay", attr="ENABLED"),
    ProviderManifestField(
        "OXAPAY_MERCHANT_API_KEY",
        "string",
        "Merchant API key",
        description="Merchant API key generated in the OxaPay dashboard.",
        subsection="OxaPay",
        secret=True,
        attr="MERCHANT_API_KEY",
    ),
    ProviderManifestField(
        "OXAPAY_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.oxapay.com/v1",
        subsection="OxaPay",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "OXAPAY_RETURN_URL",
        "url",
        "Return URL",
        description="Where OxaPay redirects the payer after a successful payment.",
        subsection="OxaPay",
        attr="RETURN_URL",
    ),
    ProviderManifestField(
        "OXAPAY_LIFETIME_MINUTES",
        "int",
        "Invoice lifetime (minutes)",
        description="OxaPay accepts values from 15 to 2880 minutes.",
        subsection="OxaPay",
        min=15,
        max=2880,
        attr="LIFETIME_MINUTES",
    ),
    ProviderManifestField(
        "OXAPAY_FEE_PAID_BY_PAYER",
        "bool",
        "Fee paid by payer",
        description="Leave unset to use the merchant dashboard setting.",
        subsection="OxaPay",
        attr="FEE_PAID_BY_PAYER",
    ),
    ProviderManifestField(
        "OXAPAY_UNDER_PAID_COVERAGE",
        "float",
        "Underpayment coverage (%)",
        description="Maximum accepted underpayment percentage; leave unset for merchant default.",
        subsection="OxaPay",
        min=0,
        max=60,
        attr="UNDER_PAID_COVERAGE",
    ),
    ProviderManifestField(
        "OXAPAY_TO_CURRENCY",
        "string",
        "Settlement conversion currency",
        description="Optional automatic conversion target. OxaPay currently supports USDT only.",
        placeholder="USDT",
        subsection="OxaPay",
        attr="TO_CURRENCY",
    ),
    ProviderManifestField(
        "OXAPAY_AUTO_WITHDRAWAL",
        "bool",
        "Automatic withdrawal",
        description="Leave unset to use the merchant dashboard setting.",
        subsection="OxaPay",
        attr="AUTO_WITHDRAWAL",
    ),
    ProviderManifestField(
        "OXAPAY_MIXED_PAYMENT",
        "bool",
        "Mixed payment",
        description="Allow the payer to complete an underpaid invoice with another currency.",
        subsection="OxaPay",
        attr="MIXED_PAYMENT",
    ),
    ProviderManifestField(
        "OXAPAY_SANDBOX",
        "bool",
        "Sandbox mode",
        description="Generate test invoices instead of live invoices.",
        subsection="OxaPay",
        attr="SANDBOX",
    ),
    ProviderManifestField(
        "OXAPAY_TRUSTED_IPS",
        "string",
        "Trusted webhook IPs",
        description=(
            "Optional comma-separated OxaPay webhook IPs. Obtain the current list from OxaPay "
            "support; HMAC verification remains mandatory."
        ),
        subsection="OxaPay",
        attr="TRUSTED_IPS",
    ),
)

__all__ = ["_CONFIG_MANIFEST", "_PRESENTATION_MANIFEST"]
