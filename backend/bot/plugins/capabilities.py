"""Versioned Core contracts available to portable plugin packages."""

CORE_PLUGIN_CAPABILITIES: dict[str, int] = {
    "support_connector": 3,
    "user_ui": 1,
    "ui_composition": 3,
    "message_composition": 1,
    "install_guides": 1,
    "external_orders": 1,
    "durable_jobs": 1,
    "rewards": 1,
    "backups": 1,
}
