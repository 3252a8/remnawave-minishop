"""Trial settings exposed by the admin settings editor."""

from bot.app.web.admin_settings_manifest_types import TRAFFIC_STRATEGY_CHOICES, SettingField

TRIAL_SETTINGS_FIELDS: tuple[SettingField, ...] = (
    SettingField(
        "TRIAL_ENABLED",
        "bool",
        "pricing",
        "Trial Enabled",
        optional=False,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_PAYMENT_ENABLED",
        "bool",
        "pricing",
        "Paid trial activation",
        "Require a successful payment before trial activation.",
        optional=False,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_PAYMENT_PRICE",
        "float",
        "pricing",
        "Trial activation price",
        (
            "Price in the default payment currency. "
            "Set a positive value when paid activation is enabled."
        ),
        optional=False,
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_PAYMENT_STARS_PRICE",
        "int",
        "pricing",
        "Trial activation price in Stars",
        "Telegram Stars price. Set to 0 to hide Stars from the trial checkout.",
        optional=False,
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_DURATION_DAYS",
        "int",
        "pricing",
        "Trial Duration Days",
        optional=False,
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_TRAFFIC_LIMIT_GB",
        "float",
        "pricing",
        "Trial Traffic Limit Gb",
        optional=False,
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB",
        "float",
        "pricing",
        "Trial premium traffic limit (GB)",
        (
            "Separate premium traffic limit for trial subscriptions. "
            "0 disables premium traffic enforcement."
        ),
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_HWID_DEVICE_LIMIT",
        "int",
        "pricing",
        "Trial HWID device limit",
        (
            "Hardware device limit for trial subscriptions. "
            "Empty keeps the panel/default limit; 0 means unlimited."
        ),
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_DAYS_STRATEGY",
        "string",
        "pricing",
        "Trial days purchase strategy",
        (
            "Choose whether remaining trial days are added to a purchased tariff or the paid "
            "period starts on the payment date."
        ),
        optional=False,
        choices=(
            ("add_remaining", "Add remaining trial days"),
            ("start_from_payment", "Start from payment date"),
        ),
        subsection="trial",
    ),
    SettingField(
        "TRIAL_TRAFFIC_STRATEGY",
        "string",
        "pricing",
        "Trial Traffic Strategy",
        optional=False,
        choices=TRAFFIC_STRATEGY_CHOICES,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_WITHOUT_OAUTH_ENABLED",
        "bool",
        "system",
        "Trial without OAuth",
        (
            "If disabled, users must link Telegram or an external OAuth provider before "
            "activating a trial. "
            "Disposable email domains always require Telegram."
        ),
        optional=False,
        subsection="email_anti_abuse",
    ),
    SettingField(
        "TRIAL_SQUAD_UUIDS",
        "string",
        "pricing",
        "Trial Internal Squads",
        "Comma-separated UUIDs. Uses USER_SQUAD_UUIDS when empty.",
        subsection="trial",
    ),
    SettingField(
        "TRIAL_PREMIUM_SQUAD_UUIDS",
        "string",
        "pricing",
        "Premium Internal Squads for trial",
        (
            "Comma-separated premium internal squad UUIDs. "
            "Empty value disables premium squads for trials."
        ),
        subsection="trial",
    ),
)
