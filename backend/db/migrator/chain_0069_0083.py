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


def _migration_0071_add_hwid_device_limit_override(connection: Connection) -> None:
    """Distinguish tariff-owned HWID limits from explicit admin overrides."""

    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "subscriptions" not in table_names:
        return

    subscription_columns = {col["name"] for col in inspector.get_columns("subscriptions")}
    if "hwid_device_limit_is_override" in subscription_columns:
        return

    connection.execute(
        text(
            "ALTER TABLE subscriptions ADD COLUMN "
            "hwid_device_limit_is_override BOOLEAN NOT NULL DEFAULT FALSE"
        )
    )
    if "message_logs" not in table_names:
        return

    # Existing subscriptions predate the explicit source flag. Preserve the
    # latest successful admin choice when its audit record still exists; all
    # other stored values are tariff snapshots and may follow future changes.
    connection.execute(
        text(
            """
            UPDATE subscriptions AS subscription
            SET hwid_device_limit_is_override = TRUE
            FROM (
                SELECT DISTINCT ON (target_user_id)
                    target_user_id,
                    content
                FROM message_logs
                WHERE target_user_id IS NOT NULL
                  AND event_type IN (
                      'admin:hwid_device_limit',
                      'admin_hwid_device_limit_webapp'
                  )
                  AND content IS NOT NULL
                ORDER BY target_user_id, timestamp DESC NULLS LAST, log_id DESC
            ) AS latest_admin_limit
            WHERE subscription.user_id = latest_admin_limit.target_user_id
              AND subscription.is_active = TRUE
              AND latest_admin_limit.content NOT LIKE 'hwid_device_limit=None%'
            """
        )
    )


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
    Migration(
        id="0071_add_hwid_device_limit_override",
        description="Track explicit subscription HWID limit overrides",
        upgrade=_migration_0071_add_hwid_device_limit_override,
    ),
]
