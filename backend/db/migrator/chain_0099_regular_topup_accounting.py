"""Pair regular traffic counters with immutable accounting observations."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0099_regular_topup_accounting(connection: Connection) -> None:
    connection.execute(
        text("""
        ALTER TABLE subscriptions
        ADD COLUMN IF NOT EXISTS traffic_topup_accounting_state TEXT
    """)
    )


CHAIN_0099_REGULAR_TOPUP_ACCOUNTING: list[Migration] = [
    Migration(
        id="0099_regular_topup_accounting",
        description="Persist regular traffic quota and lifetime anchor observations together",
        upgrade=_migration_0099_regular_topup_accounting,
    )
]
