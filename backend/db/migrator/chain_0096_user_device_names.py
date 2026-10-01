"""User-chosen device labels; append-only schema addition."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0096_user_device_names(connection: Connection) -> None:
    connection.execute(
        text("""
        CREATE TABLE IF NOT EXISTS user_device_names (
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            device_token VARCHAR(32) NOT NULL,
            name VARCHAR(32) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, device_token)
        )
    """)
    )


CHAIN_0096_USER_DEVICE_NAMES: list[Migration] = [
    Migration(
        id="0096_user_device_names",
        description="Store user-chosen labels for panel HWID devices",
        upgrade=_migration_0096_user_device_names,
    )
]
