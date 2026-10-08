"""Opt in new gift redemptions without replaying historical activations."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0104_gift_referral_qualification(connection: Connection) -> None:
    additions = (
        ("subscription_gifts", "referral_qualified", "BOOLEAN NOT NULL DEFAULT FALSE"),
        (
            "referral_period_accruals",
            "gift_id",
            "INTEGER REFERENCES subscription_gifts(gift_id) ON DELETE SET NULL",
        ),
    )
    inspector = inspect(connection)
    for table, column, definition in additions:
        if table not in inspector.get_table_names():
            continue
        if column not in {item["name"] for item in inspector.get_columns(table)}:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


CHAIN_0104_GIFT_REFERRAL_QUALIFICATION = [
    Migration(
        id="0104_gift_referral_qualification",
        description="Record recipient gift qualification and durable invitation accrual source",
        upgrade=_migration_0104_gift_referral_qualification,
    )
]
