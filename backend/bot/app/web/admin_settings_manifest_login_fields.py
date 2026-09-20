"""Login method settings shown together in the admin Web App."""

from bot.app.web.admin_settings_manifest_types import SettingField

LOGIN_METHOD_SETTINGS_FIELDS: tuple[SettingField, ...] = (
    SettingField(
        "TELEGRAM_LOGIN_ENABLED",
        "bool",
        "login_methods",
        "Telegram login",
        subsection="telegram",
    ),
    SettingField(
        "TELEGRAM_LOGIN_RECOMMENDED",
        "bool",
        "login_methods",
        "Recommended login method",
        description="Prompt users to link this login method until it is configured",
        subsection="telegram",
    ),
    SettingField(
        "TELEGRAM_OAUTH_CLIENT_ID",
        "int",
        "login_methods",
        "Telegram OAuth client ID",
        subsection="telegram",
    ),
    SettingField(
        "TELEGRAM_OAUTH_CLIENT_SECRET",
        "string",
        "login_methods",
        "Telegram OAuth client secret",
        secret=True,
        subsection="telegram",
    ),
    SettingField(
        "TELEGRAM_OAUTH_REQUEST_ACCESS",
        "string",
        "login_methods",
        "Telegram OAuth permissions",
        placeholder="write",
        subsection="telegram",
    ),
    SettingField("EMAIL_LOGIN_ENABLED", "bool", "login_methods", "Email login", subsection="email"),
    SettingField(
        "EMAIL_LOGIN_RECOMMENDED",
        "bool",
        "login_methods",
        "Recommended login method",
        description="Prompt users to link this login method until it is configured",
        subsection="email",
    ),
    SettingField(
        "EMAIL_ADDRESS_CHANGE_ENABLED",
        "bool",
        "login_methods",
        "Email address change",
        description=(
            "Allow users to change their primary email after confirming both the current "
            "and new addresses"
        ),
        subsection="email",
    ),
    SettingField(
        "GOOGLE_OIDC_ENABLED", "bool", "login_methods", "Google login", subsection="google"
    ),
    SettingField(
        "GOOGLE_LOGIN_RECOMMENDED",
        "bool",
        "login_methods",
        "Recommended login method",
        description="Prompt users to link this login method until it is configured",
        subsection="google",
    ),
    SettingField(
        "GOOGLE_OIDC_CLIENT_ID",
        "string",
        "login_methods",
        "Google client ID",
        subsection="google",
    ),
    SettingField(
        "GOOGLE_OIDC_CLIENT_SECRET",
        "string",
        "login_methods",
        "Google client secret",
        secret=True,
        subsection="google",
    ),
    SettingField(
        "YANDEX_OIDC_ENABLED", "bool", "login_methods", "Yandex login", subsection="yandex"
    ),
    SettingField(
        "YANDEX_LOGIN_RECOMMENDED",
        "bool",
        "login_methods",
        "Recommended login method",
        description="Prompt users to link this login method until it is configured",
        subsection="yandex",
    ),
    SettingField(
        "YANDEX_OIDC_CLIENT_ID",
        "string",
        "login_methods",
        "Yandex client ID",
        subsection="yandex",
    ),
    SettingField(
        "YANDEX_OIDC_CLIENT_SECRET",
        "string",
        "login_methods",
        "Yandex client secret",
        secret=True,
        subsection="yandex",
    ),
    SettingField(
        "DISCORD_OIDC_ENABLED", "bool", "login_methods", "Discord login", subsection="discord"
    ),
    SettingField(
        "DISCORD_LOGIN_RECOMMENDED",
        "bool",
        "login_methods",
        "Recommended login method",
        description="Prompt users to link this login method until it is configured",
        subsection="discord",
    ),
    SettingField(
        "DISCORD_OIDC_CLIENT_ID",
        "string",
        "login_methods",
        "Discord client ID",
        subsection="discord",
    ),
    SettingField(
        "DISCORD_OIDC_CLIENT_SECRET",
        "string",
        "login_methods",
        "Discord client secret",
        secret=True,
        subsection="discord",
    ),
    SettingField(
        "PASSKEY_LOGIN_ENABLED", "bool", "login_methods", "Passkey login", subsection="passkey"
    ),
    SettingField(
        "PASSKEY_LOGIN_RECOMMENDED",
        "bool",
        "login_methods",
        "Recommended login method",
        description="Prompt users to link this login method until it is configured",
        subsection="passkey",
    ),
    SettingField(
        "PASSKEY_RP_ID",
        "string",
        "login_methods",
        "Passkey RP ID",
        placeholder="app.example.com",
        subsection="passkey",
    ),
    SettingField(
        "PASSKEY_RP_NAME", "string", "login_methods", "Passkey RP name", subsection="passkey"
    ),
    SettingField(
        "PASSKEY_ORIGINS",
        "string",
        "login_methods",
        "Allowed passkey origins",
        placeholder="https://app.example.com",
        subsection="passkey",
    ),
    SettingField(
        "PASSKEY_CHALLENGE_TTL_SECONDS",
        "int",
        "login_methods",
        "Passkey challenge TTL",
        optional=False,
        min=60,
        max=900,
        subsection="passkey",
    ),
)
