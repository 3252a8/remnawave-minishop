"""Persistent extension operations and orders; append-only schema addition."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("""
        CREATE TABLE IF NOT EXISTS extension_presentation (
            owner VARCHAR(64) NOT NULL, target VARCHAR(140) NOT NULL,
            enabled BOOLEAN NOT NULL, position INTEGER NOT NULL,
            PRIMARY KEY(owner, target)
        )
    """)
    )
    connection.execute(
        text("""
        CREATE TABLE IF NOT EXISTS extension_operations (
            id VARCHAR(32) PRIMARY KEY, owner VARCHAR(64) NOT NULL,
            kind VARCHAR(80) NOT NULL, user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            idempotency_key VARCHAR(128) NOT NULL, payload_json TEXT NOT NULL,
            state VARCHAR(16) NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 10, not_before TIMESTAMPTZ NOT NULL,
            lease_token VARCHAR(32), lease_until TIMESTAMPTZ, result_json TEXT,
            error_code VARCHAR(128), created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_extension_operation_key UNIQUE(owner, kind, idempotency_key)
        )
    """)
    )
    connection.execute(
        text("""
        CREATE INDEX IF NOT EXISTS ix_extension_operations_due
        ON extension_operations(state, not_before)
    """)
    )
    connection.execute(
        text("""
        CREATE TABLE IF NOT EXISTS extension_orders (
            id VARCHAR(32) PRIMARY KEY, owner VARCHAR(64) NOT NULL,
            product VARCHAR(64) NOT NULL,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            idempotency_key VARCHAR(128) NOT NULL, request_json TEXT NOT NULL,
            quote_json TEXT NOT NULL,
            payment_id INTEGER UNIQUE REFERENCES payments(payment_id) ON DELETE RESTRICT,
            payment_state VARCHAR(24) NOT NULL, fulfillment_state VARCHAR(24) NOT NULL,
            reference VARCHAR(256), result_json TEXT,
            created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_extension_order_key UNIQUE(user_id, idempotency_key)
        )
    """)
    )
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_extension_orders_owner ON extension_orders(owner)")
    )
    connection.execute(
        text(
            "ALTER TABLE user_balance_ledger_entries "
            "DROP CONSTRAINT IF EXISTS ck_user_balance_ledger_kind"
        )
    )
    connection.execute(
        text("""
        ALTER TABLE user_balance_ledger_entries ADD CONSTRAINT ck_user_balance_ledger_kind CHECK (
            kind IN ('payment_topup', 'payment_topup_reversal', 'admin_adjustment',
                'checkout_spend', 'checkout_spend_release', 'gift_refund',
                'partner_conversion_in', 'partner_conversion_out', 'extension_grant',
                'extension_purchase', 'extension_refund')
        )
    """)
    )


CHAIN_0090_EXTENSIONS = [
    Migration(
        id="0090_extension_operations_and_orders",
        description="Persist extension operations, external orders and ledger references",
        upgrade=_upgrade,
    )
]
