"""Persist the payment method for provider commission reporting."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS provider_method VARCHAR(48)")
    )


CHAIN_0111_PAYMENT_PROVIDER_METHOD = [
    Migration("0111_payment_provider_method", "Record the payment provider method", _upgrade)
]
