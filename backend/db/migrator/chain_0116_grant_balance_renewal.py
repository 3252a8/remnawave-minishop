"""Keep paid renewal terms separate from granted subscription entitlements."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE subscriptions "
            "ADD COLUMN IF NOT EXISTS balance_renewal_provider VARCHAR(32), "
            "ADD COLUMN IF NOT EXISTS balance_renewal_tariff_key VARCHAR, "
            "ADD COLUMN IF NOT EXISTS balance_renewal_duration_days INTEGER"
        )
    )


CHAIN_0116_GRANT_BALANCE_RENEWAL = [
    Migration("0116_grant_balance_renewal", "Store consent for renewing granted terms", _upgrade)
]
