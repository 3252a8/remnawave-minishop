"""Persist the current manual source refresh request across processes."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from db.migrator.engine import Migration


def _add_refresh_request(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE ext_minishop_blacklist_settings "
            "ADD COLUMN refresh_requested_at TIMESTAMPTZ"
        )
    )


def refresh_migration() -> Migration:
    return Migration(
        id="minishop-blacklist.0003_source_refresh",
        description="Add the manual source refresh request timestamp",
        upgrade=_add_refresh_request,
    )
