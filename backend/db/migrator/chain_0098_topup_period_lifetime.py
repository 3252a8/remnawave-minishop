"""Panel lifetime traffic at the start of each regular counter period."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0098_topup_period_lifetime(connection: Connection) -> None:
    connection.execute(
        text("""
        ALTER TABLE subscriptions
        ADD COLUMN IF NOT EXISTS traffic_period_lifetime_start_bytes BIGINT
    """)
    )


CHAIN_0098_TOPUP_PERIOD_LIFETIME: list[Migration] = [
    Migration(
        id="0098_topup_period_lifetime",
        description="Track the panel lifetime counter at each regular traffic period start",
        upgrade=_migration_0098_topup_period_lifetime,
    )
]
