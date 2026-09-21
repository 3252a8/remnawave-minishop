"""Bind public install tokens to the panel link version they were issued for."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0088_install_share_binding(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("subscriptions")}
    if "install_share_panel_short_uuid" not in columns:
        connection.execute(
            text("ALTER TABLE subscriptions ADD COLUMN install_share_panel_short_uuid VARCHAR(64)")
        )
    # Existing tokens deliberately remain unbound. An authenticated user or a
    # trusted backfill must verify the current panel link before using them.


CHAIN_0088_INSTALL_SHARE_BINDING: list[Migration] = [
    Migration(
        id="0088_bind_install_share_to_panel_link",
        description="Bind public install tokens to a verified panel link version",
        upgrade=_migration_0088_install_share_binding,
    )
]
