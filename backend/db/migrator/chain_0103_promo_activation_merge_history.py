"""Retain shared promo redemption history when accounts are merged."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0103_promo_activation_merge_history(connection: Connection) -> None:
    inspector = inspect(connection)
    if "promo_code_activations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("promo_code_activations")}
    if "merged_from_user_id" not in columns:
        connection.execute(
            text("ALTER TABLE promo_code_activations ADD COLUMN merged_from_user_id BIGINT")
        )
    connection.execute(text("DROP INDEX IF EXISTS uq_promo_user_activation_standard"))
    connection.execute(
        text(
            "CREATE UNIQUE INDEX uq_promo_user_activation_standard "
            "ON promo_code_activations (promo_code_id, user_id) "
            "WHERE is_manual_override = FALSE AND merged_from_user_id IS NULL"
        )
    )


CHAIN_0103_PROMO_ACTIVATION_MERGE_HISTORY = [
    Migration(
        id="0103_promo_activation_merge_history",
        description="Preserve shared promo activation history during account merge",
        upgrade=_migration_0103_promo_activation_merge_history,
    )
]
