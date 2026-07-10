from ..base import ProviderManifestField

_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Overpay",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_OVERPAY_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_OVERPAY_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_OVERPAY_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_OVERPAY_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_OVERPAY_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_OVERPAY_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            r"\U0001f4b3",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "OVERPAY_ENABLED", "bool", "Enabled", subsection="Overpay", attr="ENABLED"
    ),
    ProviderManifestField(
        "OVERPAY_SHOP_ID",
        "string",
        "Shop ID",
        description="Overpay Shop ID (HTTP Basic auth username).",
        subsection="Overpay",
        attr="SHOP_ID",
    ),
    ProviderManifestField(
        "OVERPAY_SECRET_KEY",
        "string",
        "Secret key",
        description=(
            "Overpay Secret Key (HTTP Basic auth password). Also authenticates incoming webhooks."
        ),
        subsection="Overpay",
        secret=True,
        attr="SECRET_KEY",
    ),
    ProviderManifestField(
        "OVERPAY_CHECKOUT_URL",
        "url",
        "Checkout URL",
        placeholder="https://checkout.overpay.io",
        description="Base URL of the Overpay checkout (payment token) API.",
        subsection="Overpay",
        attr="CHECKOUT_URL",
    ),
    ProviderManifestField(
        "OVERPAY_GATEWAY_URL",
        "url",
        "Gateway URL",
        placeholder="https://gateway.overpay.io",
        description="Base URL of the Overpay gateway API used for saved-token auto-renew charges.",
        subsection="Overpay",
        attr="GATEWAY_URL",
    ),
    ProviderManifestField(
        "OVERPAY_RETURN_URL", "url", "Return URL", subsection="Overpay", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "OVERPAY_SUCCESS_URL", "url", "Success URL", subsection="Overpay", attr="SUCCESS_URL"
    ),
    ProviderManifestField(
        "OVERPAY_DECLINE_URL", "url", "Decline URL", subsection="Overpay", attr="DECLINE_URL"
    ),
    ProviderManifestField(
        "OVERPAY_FAIL_URL", "url", "Fail URL", subsection="Overpay", attr="FAIL_URL"
    ),
    ProviderManifestField(
        "OVERPAY_LANGUAGE",
        "string",
        "Payment page language",
        description=(
            "Optional payment form language code (e.g. ru, en). "
            "Empty follows the user's language where possible."
        ),
        subsection="Overpay",
        attr="LANGUAGE",
    ),
    ProviderManifestField(
        "OVERPAY_TEST_MODE",
        "bool",
        "Test mode",
        description="Sends test transactions to the Overpay sandbox.",
        subsection="Overpay",
        attr="TEST_MODE",
    ),
    ProviderManifestField(
        "OVERPAY_RECURRING_ENABLED",
        "bool",
        "Recurring enabled",
        description=(
            "Requests a saved card token on checkout and charges it for subscription auto-renew."
        ),
        subsection="Overpay",
        attr="RECURRING_ENABLED",
    ),
    ProviderManifestField(
        "OVERPAY_VERIFY_WEBHOOK_SIGNATURE",
        "bool",
        "Verify webhook auth",
        description="Require incoming webhooks to carry the Shop ID / Secret Key HTTP Basic auth.",
        subsection="Overpay",
        attr="VERIFY_WEBHOOK_SIGNATURE",
    ),
    ProviderManifestField(
        "OVERPAY_TRUSTED_IPS",
        "string",
        "Trusted webhook IPs",
        description="Optional comma-separated allowlist of webhook source IPs.",
        subsection="Overpay",
        attr="TRUSTED_IPS",
    ),
)
