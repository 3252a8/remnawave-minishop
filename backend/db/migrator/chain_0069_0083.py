"""Core migrations 0069 onward.

Keep this module append-only.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0069_normalize_auto_renew_attempt_index(connection: Connection) -> None:
    """Keep clean installs and migrated databases on the same index shape."""

    inspector = inspect(connection)
    if "payments" not in set(inspector.get_table_names()):
        return

    connection.execute(
        text("ALTER TABLE payments DROP CONSTRAINT IF EXISTS uq_payments_auto_renew_cycle_attempt")
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_auto_renew_cycle_attempt "
            "ON payments (auto_renew_cycle_id, renewal_attempt_number) "
            "WHERE auto_renew_cycle_id IS NOT NULL AND renewal_attempt_number IS NOT NULL"
        )
    )


def _migration_0070_add_rollypay_subscriptions(connection: Connection) -> None:
    """Persist RollyPay mandates before their first asynchronous charge callback."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS rollypay_subscriptions (
                id SERIAL PRIMARY KEY,
                rollypay_subscription_id VARCHAR NOT NULL UNIQUE,
                anchor_payment_id INTEGER NOT NULL UNIQUE REFERENCES payments(payment_id),
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                provider_state VARCHAR(32) NOT NULL DEFAULT 'new',
                billing_status VARCHAR(32) NOT NULL DEFAULT 'consent_pending',
                plan_id VARCHAR NOT NULL,
                plan_code VARCHAR NOT NULL,
                plan_version INTEGER NOT NULL,
                interval VARCHAR(16) NOT NULL,
                max_cycles INTEGER,
                amount DOUBLE PRECISION NOT NULL,
                currency VARCHAR(8) NOT NULL DEFAULT 'RUB',
                months INTEGER NOT NULL,
                sale_mode VARCHAR,
                tariff_key VARCHAR,
                next_charge_at TIMESTAMPTZ,
                last_charge_at TIMESTAMPTZ,
                charges_count INTEGER NOT NULL DEFAULT 0,
                first_provider_payment_id VARCHAR UNIQUE,
                activated_at TIMESTAMPTZ,
                stopped_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    for statement in (
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_rollypay_subscriptions_subscription_id "
        "ON rollypay_subscriptions (rollypay_subscription_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_rollypay_subscriptions_anchor_payment_id "
        "ON rollypay_subscriptions (anchor_payment_id)",
        "CREATE INDEX IF NOT EXISTS ix_rollypay_subscriptions_user_id "
        "ON rollypay_subscriptions (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_rollypay_subscriptions_provider_state "
        "ON rollypay_subscriptions (provider_state)",
        "CREATE INDEX IF NOT EXISTS ix_rollypay_subscriptions_billing_status "
        "ON rollypay_subscriptions (billing_status)",
        "CREATE INDEX IF NOT EXISTS ix_rollypay_subscriptions_tariff_key "
        "ON rollypay_subscriptions (tariff_key)",
        "CREATE INDEX IF NOT EXISTS ix_rollypay_subscriptions_user_billing_status "
        "ON rollypay_subscriptions (user_id, billing_status)",
    ):
        connection.execute(text(statement))


CHAIN_0069_0083: list[Migration] = [
    Migration(
        id="0069_normalize_auto_renew_attempt_index",
        description="Normalize auto-renew attempt uniqueness as a partial index",
        upgrade=_migration_0069_normalize_auto_renew_attempt_index,
    ),
    Migration(
        id="0070_add_rollypay_subscriptions",
        description="Add the RollyPay recurring subscription mirror",
        upgrade=_migration_0070_add_rollypay_subscriptions,
    ),
]
