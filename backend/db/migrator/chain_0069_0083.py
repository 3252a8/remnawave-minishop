"""Core migrations 0069 onward.

Keep this module append-only.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0069_normalize_auto_renew_attempt_index(connection: Connection) -> None:
    """Keep clean installs and migrated databases on the same index shape."""

    inspector = inspect(connection)
    if "payments" not in set(inspector.get_table_names()):
        return

    connection.execute(
        text("ALTER TABLE payments DROP CONSTRAINT IF EXISTS uq_payments_auto_renew_cycle_attempt")
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_auto_renew_cycle_attempt "
            "ON payments (auto_renew_cycle_id, renewal_attempt_number) "
            "WHERE auto_renew_cycle_id IS NOT NULL AND renewal_attempt_number IS NOT NULL"
        )
    )


CHAIN_0069_0083: list[Migration] = [
    Migration(
        id="0069_normalize_auto_renew_attempt_index",
        description="Normalize auto-renew attempt uniqueness as a partial index",
        upgrade=_migration_0069_normalize_auto_renew_attempt_index,
    ),
]
