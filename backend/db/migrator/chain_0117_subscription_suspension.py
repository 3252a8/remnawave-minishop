"""Preserve the current entitlement and its original expiry during an admin pause."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ, "
            "ADD COLUMN IF NOT EXISTS suspension_end_date TIMESTAMPTZ"
        )
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_suspended_user "
            "ON subscriptions (user_id) WHERE suspended_at IS NOT NULL"
        )
    )


CHAIN_0117_SUBSCRIPTION_SUSPENSION = [
    Migration("0117_subscription_suspension", "Track temporary subscription suspension", _upgrade)
]
