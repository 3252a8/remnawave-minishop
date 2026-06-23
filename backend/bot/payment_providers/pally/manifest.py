from ..base import ProviderManifestField

_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="Pally",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_PALLY_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_PALLY_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_PALLY_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "WalletCards",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_PALLY_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_PALLY_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_PALLY_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            r"\U0001f4b3",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField("PALLY_ENABLED", "bool", "Enabled", subsection="Pally", attr="ENABLED"),
    ProviderManifestField(
        "PALLY_API_TOKEN",
        "string",
        "API token",
        description="Bearer token from the Pally API integrations page.",
        subsection="Pally",
        secret=True,
        attr="API_TOKEN",
    ),
    ProviderManifestField(
        "PALLY_SIGNATURE_TOKEN",
        "string",
        "Signature token",
        description="Token used to verify postback MD5 signatures. Leave empty to use API token.",
        subsection="Pally",
        secret=True,
        attr="SIGNATURE_TOKEN",
    ),
    ProviderManifestField(
        "PALLY_SHOP_ID",
        "string",
        "Shop ID",
        description="Pally shop identifier used by bills and Result URL postbacks.",
        subsection="Pally",
        attr="SHOP_ID",
    ),
    ProviderManifestField(
        "PALLY_BASE_URL",
        "url",
        "Base URL",
        placeholder="https://pally.info/api/v1",
        subsection="Pally",
        attr="BASE_URL",
    ),
    ProviderManifestField(
        "PALLY_RETURN_URL", "url", "Return URL", subsection="Pally", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "PALLY_SUCCESS_URL", "url", "Success URL", subsection="Pally", attr="SUCCESS_URL"
    ),
    ProviderManifestField("PALLY_FAIL_URL", "url", "Fail URL", subsection="Pally", attr="FAIL_URL"),
    ProviderManifestField(
        "PALLY_TTL_SECONDS",
        "int",
        "Bill lifetime (seconds)",
        description="Optional Pally bill lifetime in seconds.",
        subsection="Pally",
        min=1,
        attr="TTL_SECONDS",
    ),
    ProviderManifestField(
        "PALLY_PAYER_PAYS_COMMISSION",
        "bool",
        "Payer pays commission",
        description="Sends payer_pays_commission=1 when enabled.",
        subsection="Pally",
        attr="PAYER_PAYS_COMMISSION",
    ),
    ProviderManifestField(
        "PALLY_PAYMENT_METHOD",
        "string",
        "Preselected payment method",
        description="Optionally lock the hosted payment form to bank card or SBP.",
        subsection="Pally",
        choices=(("BANK_CARD", "Bank card"), ("SBP", "SBP")),
        attr="PAYMENT_METHOD",
    ),
    ProviderManifestField(
        "PALLY_LOCALE",
        "string",
        "Payment page locale",
        description=(
            "Optional payment form locale. Empty follows the user's language where possible."
        ),
        subsection="Pally",
        choices=(("ru", "Russian"), ("en", "English")),
        attr="LOCALE",
    ),
    ProviderManifestField(
        "PALLY_NAME",
        "string",
        "Payment form title",
        description="Optional link name displayed on the Pally payment form.",
        subsection="Pally",
        attr="NAME",
    ),
)
