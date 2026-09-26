"""Persist provider-managed Wata recurring subscriptions."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0087_add_wata_subscriptions(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS wata_subscriptions (
                id SERIAL PRIMARY KEY,
                wata_subscription_id VARCHAR NOT NULL UNIQUE,
                anchor_payment_id INTEGER NOT NULL UNIQUE REFERENCES payments(payment_id),
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                interval VARCHAR(16) NOT NULL,
                period INTEGER NOT NULL,
                max_periods INTEGER NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                currency VARCHAR(8) NOT NULL,
                months INTEGER NOT NULL,
                duration_days INTEGER,
                subscription_terms_snapshot TEXT,
                checkout_bundle_snapshot TEXT,
                period_semantics VARCHAR(32),
                sale_mode VARCHAR,
                tariff_key VARCHAR,
                charges_count INTEGER NOT NULL DEFAULT 0,
                first_provider_payment_id VARCHAR UNIQUE,
                last_charge_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    for statement in (
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_wata_subscriptions_subscription_id "
        "ON wata_subscriptions (wata_subscription_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_wata_subscriptions_anchor_payment_id "
        "ON wata_subscriptions (anchor_payment_id)",
        "CREATE INDEX IF NOT EXISTS ix_wata_subscriptions_user_id ON wata_subscriptions (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_wata_subscriptions_status ON wata_subscriptions (status)",
        "CREATE INDEX IF NOT EXISTS ix_wata_subscriptions_tariff_key "
        "ON wata_subscriptions (tariff_key)",
        "CREATE INDEX IF NOT EXISTS ix_wata_subscriptions_user_status "
        "ON wata_subscriptions (user_id, status)",
    ):
        connection.execute(text(statement))


CHAIN_0087_WATA_SUBSCRIPTIONS: list[Migration] = [
    Migration(
        id="0087_add_wata_subscriptions",
        description="Add the Wata recurring subscription mirror",
        upgrade=_migration_0087_add_wata_subscriptions,
    )
]
