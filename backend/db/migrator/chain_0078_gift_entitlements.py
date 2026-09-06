"""Keep redeemed gift entitlements independent of later catalog edits."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0078_gift_entitlements(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS gift_terms_snapshot TEXT")
    )


CHAIN_0078_GIFT_ENTITLEMENTS = [
    Migration(
        id="0078_gift_entitlements",
        description="Preserve redeemed gift tariff conditions",
        upgrade=_migration_0078_gift_entitlements,
    )
]
