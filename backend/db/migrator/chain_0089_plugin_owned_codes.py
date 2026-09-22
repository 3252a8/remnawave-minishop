"""Persist the owner of extension-issued codes before plugins can be disabled."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0089_plugin_owned_codes(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("promo_codes")}
    if "owner_plugin_id" not in columns:
        connection.execute(text("ALTER TABLE promo_codes ADD COLUMN owner_plugin_id VARCHAR(64)"))


CHAIN_0089_PLUGIN_OWNED_CODES: list[Migration] = [
    Migration(
        id="0089_persist_plugin_owned_codes",
        description="Persist extension ownership of customer codes",
        upgrade=_migration_0089_plugin_owned_codes,
    )
]
