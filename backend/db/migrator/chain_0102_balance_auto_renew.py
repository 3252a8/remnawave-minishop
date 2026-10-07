"""Persist explicit customer consent to subscription renewal from a balance."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0102_balance_auto_renew(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("payments")}
    if "balance_auto_renew" not in columns:
        connection.execute(
            text(
                "ALTER TABLE payments ADD COLUMN balance_auto_renew BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )


CHAIN_0102_BALANCE_AUTO_RENEW = [
    Migration(
        id="0102_balance_auto_renew",
        description="Persist customer consent for fully balance-funded subscription renewal",
        upgrade=_migration_0102_balance_auto_renew,
    )
]
