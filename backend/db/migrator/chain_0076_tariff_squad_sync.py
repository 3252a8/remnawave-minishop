"""Track tariff-managed squads so catalog edits can be reconciled safely."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0076_track_tariff_managed_squads(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS tariff_managed_squad_uuids TEXT")
    )


CHAIN_0076_TARIFF_SQUAD_SYNC = [
    Migration(
        id="0076_track_tariff_managed_squads",
        description="Track tariff-managed squads for subscriber reconciliation",
        upgrade=_migration_0076_track_tariff_managed_squads,
    )
]
