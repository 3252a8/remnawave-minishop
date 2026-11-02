"""Persist subscription-day purchases independently from monetary payments."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0109_subscription_days_payments(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS subscription_days_spent INTEGER")
    )
    connection.execute(
        text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS subscription_days_snapshot TEXT")
    )


CHAIN_0109_SUBSCRIPTION_DAYS_PAYMENTS: list[Migration] = [
    Migration(
        id="0109_subscription_days_payments",
        description="Store subscription-day purchase amounts and their quoted terms",
        upgrade=_migration_0109_subscription_days_payments,
    )
]
