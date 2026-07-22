"""Core migrations 0046 onward.

Keep this module append-only. It deliberately starts a fresh range instead of
rewriting the historical 0022-0045 chain.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0046_add_recurring_payment_attribution(connection: Connection) -> None:
    """Persist provider-neutral attribution for automatic renewal attempts."""

    inspector = inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("payments")}
    additions = {
        "is_auto_renew": "BOOLEAN NOT NULL DEFAULT FALSE",
        "renewal_subscription_id": "INTEGER",
        "renewal_cycle_end": "TIMESTAMPTZ",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(text(f"ALTER TABLE payments ADD COLUMN {column} {definition}"))
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_payments_is_auto_renew ON payments (is_auto_renew)")
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_payments_renewal_subscription_id "
            "ON payments (renewal_subscription_id)"
        )
    )


CHAIN_0046_0060: list[Migration] = [
    Migration(
        id="0046_add_recurring_payment_attribution",
        description="Persist auto-renew attribution and renewal cycle references",
        upgrade=_migration_0046_add_recurring_payment_attribution,
    ),
]
