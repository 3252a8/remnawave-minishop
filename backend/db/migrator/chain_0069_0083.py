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


def _migration_0072_add_external_login_credentials(connection: Connection) -> None:
    """Persist external identities, passkeys, and replay-safe WebAuthn challenges."""

    statements = (
        """
            CREATE TABLE IF NOT EXISTS user_external_identities (
                identity_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                provider VARCHAR(32) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                email VARCHAR(254),
                email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                display_name VARCHAR(255),
                picture_url TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_used_at TIMESTAMPTZ,
                CONSTRAINT uq_external_identity_provider_subject UNIQUE (provider, subject),
                CONSTRAINT uq_external_identity_user_provider UNIQUE (user_id, provider)
            )
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_user_external_identities_user_id
                ON user_external_identities (user_id)
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_user_external_identities_provider
                ON user_external_identities (provider)
        """,
        """
            CREATE TABLE IF NOT EXISTS user_passkey_credentials (
                credential_pk SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                credential_id VARCHAR(1024) NOT NULL UNIQUE,
                public_key BYTEA NOT NULL,
                sign_count BIGINT NOT NULL DEFAULT 0,
                transports VARCHAR(255),
                device_type VARCHAR(32),
                backed_up BOOLEAN NOT NULL DEFAULT FALSE,
                name VARCHAR(80) NOT NULL DEFAULT 'Passkey',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_used_at TIMESTAMPTZ
            )
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_user_passkey_credentials_user_id
                ON user_passkey_credentials (user_id)
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_user_passkey_credentials_credential_id
                ON user_passkey_credentials (credential_id)
        """,
        """
            CREATE TABLE IF NOT EXISTS webauthn_challenges (
                challenge_hash VARCHAR(64) PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                ceremony VARCHAR(16) NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                consumed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_webauthn_challenges_user_id
                ON webauthn_challenges (user_id)
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_webauthn_challenges_ceremony
                ON webauthn_challenges (ceremony)
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_webauthn_challenges_expires_at
                ON webauthn_challenges (expires_at)
        """,
    )
    for statement in statements:
        connection.execute(text(statement))


def _migration_0073_add_user_email_addresses(connection: Connection) -> None:
    """Separate verified account addresses from the primary sign-in address."""

    statements = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_email VARCHAR(254)",
        """
            CREATE TABLE IF NOT EXISTS user_email_addresses (
                email_address_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                email VARCHAR(254) NOT NULL,
                source VARCHAR(32) NOT NULL DEFAULT 'email',
                verified_at TIMESTAMPTZ NOT NULL,
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                is_notification BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_user_email_address_email UNIQUE (email)
            )
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_user_email_addresses_user_id
                ON user_email_addresses (user_id)
        """,
        """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_user_email_addresses_primary
                ON user_email_addresses (user_id) WHERE is_primary
        """,
        """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_user_email_addresses_notification
                ON user_email_addresses (user_id) WHERE is_notification
        """,
        """
            INSERT INTO user_email_addresses (
                user_id,
                email,
                source,
                verified_at,
                is_primary,
                is_notification
            )
            SELECT DISTINCT ON (LOWER(TRIM(email)))
                user_id,
                LOWER(TRIM(email)),
                'email',
                email_verified_at,
                TRUE,
                TRUE
            FROM users
            WHERE email IS NOT NULL
              AND TRIM(email) <> ''
              AND email_verified_at IS NOT NULL
            ORDER BY LOWER(TRIM(email)), email_verified_at ASC, user_id ASC
            ON CONFLICT (email) DO UPDATE SET
                verified_at = EXCLUDED.verified_at,
                is_primary = TRUE,
                is_notification = TRUE,
                updated_at = NOW()
        """,
        """
            UPDATE users
            SET notification_email = LOWER(TRIM(email))
            WHERE notification_email IS NULL
              AND email IS NOT NULL
              AND TRIM(email) <> ''
              AND email_verified_at IS NOT NULL
        """,
    )
    for statement in statements:
        connection.execute(text(statement))


def _migration_0074_add_user_balance(connection: Connection) -> None:
    """Add append-only user balances and checkout funding attribution."""

    statements = (
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS user_balance_amount_minor BIGINT",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS user_balance_currency_scale INTEGER",
        """
            CREATE TABLE IF NOT EXISTS user_balance_ledger_entries (
                entry_id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                currency VARCHAR(16) NOT NULL,
                currency_scale INTEGER NOT NULL,
                amount_minor BIGINT NOT NULL,
                kind VARCHAR(32) NOT NULL,
                state VARCHAR(16) NOT NULL DEFAULT 'posted',
                reference_type VARCHAR(32) NOT NULL,
                reference_id VARCHAR(64) NOT NULL,
                idempotency_key VARCHAR(128) NOT NULL UNIQUE,
                actor_admin_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
                reason TEXT,
                metadata_json TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                posted_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT ck_user_balance_ledger_state CHECK (state IN ('posted', 'void')),
                CONSTRAINT ck_user_balance_ledger_kind CHECK (
                    kind IN ('payment_topup', 'payment_topup_reversal', 'admin_adjustment',
                    'checkout_spend', 'checkout_spend_release', 'partner_conversion_in',
                    'partner_conversion_out')
                )
            )
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_user_balance_ledger_user_currency
                ON user_balance_ledger_entries (user_id, currency, created_at)
        """,
        """
            CREATE INDEX IF NOT EXISTS ix_user_balance_ledger_reference
                ON user_balance_ledger_entries (reference_type, reference_id)
        """,
        (
            "ALTER TABLE partner_ledger_entries ADD COLUMN IF NOT EXISTS "
            "withdrawable_amount_minor BIGINT"
        ),
        """
            UPDATE partner_ledger_entries
            SET withdrawable_amount_minor = amount_minor
            WHERE withdrawable_amount_minor IS NULL
        """,
        "ALTER TABLE partner_ledger_entries ALTER COLUMN withdrawable_amount_minor SET DEFAULT 0",
        "ALTER TABLE partner_ledger_entries ALTER COLUMN withdrawable_amount_minor SET NOT NULL",
        "ALTER TABLE partner_ledger_entries DROP CONSTRAINT IF EXISTS ck_partner_ledger_kind",
        """
            ALTER TABLE partner_ledger_entries ADD CONSTRAINT ck_partner_ledger_kind CHECK (
                kind IN ('commission_credit', 'manual_adjustment', 'withdrawal_reserve',
                'withdrawal_release', 'subscription_spend', 'subscription_spend_release',
                'checkout_spend', 'checkout_spend_release', 'commission_reversal',
                'balance_conversion_in', 'balance_conversion_out')
            )
        """,
    )
    for statement in statements:
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
    Migration(
        id="0071_add_hwid_device_limit_override",
        description="Track explicit subscription HWID limit overrides",
        upgrade=_migration_0071_add_hwid_device_limit_override,
    ),
    Migration(
        id="0072_add_external_login_credentials",
        description="Add external OAuth identities and WebAuthn passkeys",
        upgrade=_migration_0072_add_external_login_credentials,
    ),
    Migration(
        id="0073_add_user_email_addresses",
        description="Add verified account email addresses and notification selection",
        upgrade=_migration_0073_add_user_email_addresses,
    ),
    Migration(
        id="0074_add_user_balance",
        description="Add user balance ledgers and checkout funding attribution",
        upgrade=_migration_0074_add_user_balance,
    ),
]
