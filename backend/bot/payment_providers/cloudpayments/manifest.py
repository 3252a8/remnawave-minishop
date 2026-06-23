from ..base import ProviderManifestField

_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="CloudPayments",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_CLOUDPAYMENTS_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_CLOUDPAYMENTS_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_CLOUDPAYMENTS_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_CLOUDPAYMENTS_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_CLOUDPAYMENTS_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_CLOUDPAYMENTS_TELEGRAM_EMOJI",
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
        "CLOUDPAYMENTS_ENABLED", "bool", "Enabled", subsection="CloudPayments", attr="ENABLED"
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_PUBLIC_ID",
        "string",
        "Public ID",
        description="Public ID from the CloudPayments dashboard (HTTP Basic auth username).",
        subsection="CloudPayments",
        attr="PUBLIC_ID",
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_API_SECRET",
        "string",
        "API secret",
        description=(
            "API Secret from the CloudPayments dashboard. Used as the HTTP Basic auth "
            "password and to verify notification HMAC signatures."
        ),
        subsection="CloudPayments",
        secret=True,
        attr="API_SECRET",
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://api.cloudpayments.ru",
        subsection="CloudPayments",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_RETURN_URL",
        "url",
        "Return URL",
        subsection="CloudPayments",
        attr="RETURN_URL",
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_FAILED_URL",
        "url",
        "Failed URL",
        subsection="CloudPayments",
        attr="FAILED_URL",
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_RECURRING_ENABLED",
        "bool",
        "Recurring payments",
        description=(
            "Allows CloudPayments token charges for subscription auto-renew. "
            "Requires Pay notifications with Token enabled in CloudPayments."
        ),
        subsection="CloudPayments",
        attr="RECURRING_ENABLED",
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_VERIFY_WEBHOOK_SIGNATURE",
        "bool",
        "Verify webhook signature",
        description="Verify the Content-HMAC header on Pay/Fail notifications.",
        subsection="CloudPayments",
        attr="VERIFY_WEBHOOK_SIGNATURE",
    ),
    ProviderManifestField(
        "CLOUDPAYMENTS_TRUSTED_IPS",
        "string",
        "Trusted IPs",
        description="Optional comma-separated IP addresses accepted for CloudPayments webhooks.",
        subsection="CloudPayments",
        attr="TRUSTED_IPS",
    ),
)
