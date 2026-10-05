"""Keep lifecycle delivery markers separate for each subscription expiry."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0100_subscription_notification_periods(connection: Connection) -> None:
    connection.execute(
        text("""
        CREATE TABLE IF NOT EXISTS subscription_lifecycle_notifications (
            notification_id SERIAL PRIMARY KEY,
            subscription_id INTEGER NOT NULL
                REFERENCES subscriptions(subscription_id) ON DELETE CASCADE,
            notification_key VARCHAR(64) NOT NULL,
            period_end_date TIMESTAMP WITH TIME ZONE NOT NULL,
            sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_subscription_lifecycle_notification_period
                UNIQUE (subscription_id, notification_key, period_end_date)
        )
    """)
    )


CHAIN_0100_SUBSCRIPTION_NOTIFICATION_PERIODS: list[Migration] = [
    Migration(
        id="0100_subscription_notification_periods",
        description="Deduplicate lifecycle deliveries by subscription expiry and channel",
        upgrade=_migration_0100_subscription_notification_periods,
    )
]
