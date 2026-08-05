"""Core migrations 0056 onward.

Keep this module append-only.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0056_add_tariff_binding_audit(connection: Connection) -> None:
    """Record how and when a subscription became linked to a tariff."""

    inspector = inspect(connection)
    if "subscriptions" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("subscriptions")}
    additions = {
        "tariff_binding_source": "VARCHAR(32)",
        "tariff_bound_at": "TIMESTAMPTZ",
        "tariff_binding_note": "VARCHAR(255)",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(text(f"ALTER TABLE subscriptions ADD COLUMN {column} {definition}"))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_subscriptions_tariff_binding_source "
            "ON subscriptions (tariff_binding_source)"
        )
    )


def _migration_0057_add_platega_subscriptions(connection: Connection) -> None:
    """Mirror Platega SBP subscription mandates so renewals stay attributable."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS platega_subscriptions (
                id SERIAL PRIMARY KEY,
                platega_subscription_id VARCHAR NOT NULL UNIQUE,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                amount DOUBLE PRECISION NOT NULL,
                currency VARCHAR NOT NULL,
                interval_code INTEGER NOT NULL,
                months INTEGER NOT NULL,
                sale_mode VARCHAR,
                tariff_key VARCHAR,
                next_charge_at TIMESTAMPTZ,
                last_charge_at TIMESTAMPTZ,
                charges_count INTEGER NOT NULL DEFAULT 0,
                cancelled_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    for statement in (
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_platega_subscriptions_platega_subscription_id "
        "ON platega_subscriptions (platega_subscription_id)",
        "CREATE INDEX IF NOT EXISTS ix_platega_subscriptions_user_id "
        "ON platega_subscriptions (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_platega_subscriptions_status "
        "ON platega_subscriptions (status)",
        "CREATE INDEX IF NOT EXISTS ix_platega_subscriptions_tariff_key "
        "ON platega_subscriptions (tariff_key)",
        "CREATE INDEX IF NOT EXISTS ix_platega_subscriptions_user_status "
        "ON platega_subscriptions (user_id, status)",
    ):
        connection.execute(text(statement))


CHAIN_0056_0070: list[Migration] = [
    Migration(
        id="0056_add_tariff_binding_audit",
        description="Record subscription tariff-binding provenance and repair metadata",
        upgrade=_migration_0056_add_tariff_binding_audit,
    ),
    Migration(
        id="0057_add_platega_subscriptions",
        description="Track Platega SBP subscription mandates for provider-managed renewals",
        upgrade=_migration_0057_add_platega_subscriptions,
    ),
]
