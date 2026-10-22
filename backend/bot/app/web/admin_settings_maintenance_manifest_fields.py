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
]
