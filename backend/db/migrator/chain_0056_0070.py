"""Core migrations 0056 onward.

Keep this module append-only.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0056_add_tariff_binding_audit(connection: Connection) -> None:
    """Record how and when a subscription became linked to a tariff."""

    inspector = inspect(connection)
    if "subscriptions" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("subscriptions")}
    additions = {
        "tariff_binding_source": "VARCHAR(32)",
        "tariff_bound_at": "TIMESTAMPTZ",
        "tariff_binding_note": "VARCHAR(255)",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(text(f"ALTER TABLE subscriptions ADD COLUMN {column} {definition}"))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_subscriptions_tariff_binding_source "
            "ON subscriptions (tariff_binding_source)"
        )
    )


CHAIN_0056_0070: list[Migration] = [
    Migration(
        id="0056_add_tariff_binding_audit",
        description="Record subscription tariff-binding provenance and repair metadata",
        upgrade=_migration_0056_add_tariff_binding_audit,
    ),
]
