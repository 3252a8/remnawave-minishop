"""Pin each verified panel link to its configured panel origin."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0092_panel_origin(connection: Connection) -> None:
    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS panel_origin VARCHAR(64)"))


CHAIN_0092_PANEL_ORIGIN: list[Migration] = [
    Migration(
        id="0092_panel_origin",
        description="Record the panel origin for verified native user links",
        upgrade=_migration_0092_panel_origin,
    )
]
