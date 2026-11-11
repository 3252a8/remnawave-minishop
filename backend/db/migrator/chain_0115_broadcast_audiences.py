"""Persist multiple broadcast targets and per-user audience exclusions."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(text("ALTER TABLE admin_broadcasts ADD COLUMN IF NOT EXISTS targets JSON"))
    connection.execute(
        text("""
        CREATE TABLE IF NOT EXISTS broadcast_audience_exclusions (
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            target VARCHAR(64) NOT NULL,
            PRIMARY KEY (user_id, target)
        )
        """)
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_broadcast_audience_exclusions_target "
            "ON broadcast_audience_exclusions (target)"
        )
    )


CHAIN_0115_BROADCAST_AUDIENCES = [
    Migration("0115_broadcast_audiences", "Store broadcast targets and exclusions", _upgrade)
]
