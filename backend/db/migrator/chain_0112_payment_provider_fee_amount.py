"""Store the estimated provider fee at payment confirmation."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS provider_fee_amount DOUBLE PRECISION")
    )


CHAIN_0112_PAYMENT_PROVIDER_FEE_AMOUNT = [
    Migration("0112_payment_provider_fee_amount", "Record the payment provider fee", _upgrade)
]
