"""Track the Remnawave tariff tag owned by Core."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0086_add_managed_panel_tariff_tag(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS managed_panel_tariff_tag VARCHAR(255)")
    )


CHAIN_0086_PANEL_TARIFF_TAG: list[Migration] = [
    Migration(
        id="0086_add_managed_panel_tariff_tag",
        description="Track the Remnawave tariff tag managed by Core",
        upgrade=_migration_0086_add_managed_panel_tariff_tag,
    )
]
