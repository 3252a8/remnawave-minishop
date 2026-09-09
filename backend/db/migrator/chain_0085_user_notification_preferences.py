"""Per-user email and Telegram notification preferences."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0085_add_user_notification_preferences(connection: Connection) -> None:
    for column_name in (
        "marketing_notifications_email_enabled",
        "marketing_notifications_telegram_enabled",
        "system_notifications_email_enabled",
        "system_notifications_telegram_enabled",
    ):
        connection.execute(
            text(
                f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} "
                "BOOLEAN NOT NULL DEFAULT TRUE"
            )
        )


CHAIN_0085_USER_NOTIFICATION_PREFERENCES: list[Migration] = [
    Migration(
        id="0085_add_user_notification_preferences",
        description="Add per-user marketing and system notification preferences",
        upgrade=_migration_0085_add_user_notification_preferences,
    )
]
