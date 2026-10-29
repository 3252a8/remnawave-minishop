"""Runtime maintenance controls, shared by the bot and the user application."""

from bot.app.web.admin_settings_manifest_types import SettingField

MAINTENANCE_SETTINGS_FIELDS = [
    SettingField(
        "MAINTENANCE_MODE_ENABLED",
        "bool",
        "general",
        "Maintenance mode",
        (
            "Temporarily pauses the user application and bot commands. Administrators retain "
            "access; subscriptions and background processes continue to work."
        ),
        optional=False,
    ),
    SettingField(
        "MAINTENANCE_MODE_AUTO_ENABLED",
        "bool",
        "general",
        "Automatic panel maintenance",
        (
            "Pause user actions after the panel stays unavailable for the configured delay. "
            "Recovery clears only automatic maintenance. Administrators receive Telegram notices."
        ),
        optional=False,
    ),
    SettingField(
        "MAINTENANCE_MODE_AUTO_DELAY_SECONDS",
        "int",
        "general",
        "Panel outage delay (seconds)",
        (
            "Minimum observed panel outage before automatic maintenance. "
            "Default: 60; checked every 15 seconds."
        ),
        optional=False,
        min=0,
        max=86400,
    ),
]
