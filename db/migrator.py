import logging
from dataclasses import dataclass
from typing import Callable, List, Set

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class Migration:
    id: str
    description: str
    upgrade: Callable[[Connection], None]


def _ensure_migrations_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )


def _migration_0001_add_channel_subscription_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}
    statements: List[str] = []

    if "channel_subscription_verified" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN channel_subscription_verified BOOLEAN"
        )
    if "channel_subscription_checked_at" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN channel_subscription_checked_at TIMESTAMPTZ"
        )
    if "channel_subscription_verified_for" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN channel_subscription_verified_for BIGINT"
        )

    for stmt in statements:
        connection.execute(text(stmt))


def _migration_0002_add_referral_code(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}

    if "referral_code" not in columns:
        connection.execute(
            text("ALTER TABLE users ADD COLUMN referral_code VARCHAR(16)")
        )

    connection.execute(
        text(
            """
            WITH generated_codes AS (
                SELECT
                    user_id,
                    UPPER(
                        SUBSTRING(
                            md5(
                                user_id::text
                                || clock_timestamp()::text
                                || random()::text
                            )
                            FROM 1 FOR 9
                        )
                    ) AS referral_code
                FROM users
                WHERE referral_code IS NULL OR referral_code = ''
            )
            UPDATE users AS u
            SET referral_code = g.referral_code
            FROM generated_codes AS g
            WHERE u.user_id = g.user_id
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_referral_code
            ON users (referral_code)
            WHERE referral_code IS NOT NULL
            """
        )
    )


def _migration_0003_normalize_referral_codes(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "referral_code" not in columns:
        return

    connection.execute(
        text(
            """
            UPDATE users
            SET referral_code = UPPER(referral_code)
            WHERE referral_code IS NOT NULL
              AND referral_code <> UPPER(referral_code)
            """
        )
    )


def _migration_0004_add_lifetime_used_traffic(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "lifetime_used_traffic_bytes" in columns:
        return

    connection.execute(
        text(
            "ALTER TABLE users ADD COLUMN lifetime_used_traffic_bytes BIGINT"
        )
    )


def _migration_0005_add_email_auth_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}

    if "email" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR"))
    if "email_verified_at" not in columns:
        connection.execute(
            text("ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ")
        )
    if "telegram_id" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN telegram_id BIGINT"))

    connection.execute(
        text(
            """
            UPDATE users
            SET telegram_id = user_id
            WHERE telegram_id IS NULL
              AND user_id > 0
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email
            ON users (email)
            WHERE email IS NOT NULL
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id
            ON users (telegram_id)
            WHERE telegram_id IS NOT NULL
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS email_verification_codes (
                code_id SERIAL PRIMARY KEY,
                email VARCHAR NOT NULL,
                code_hash VARCHAR NOT NULL,
                purpose VARCHAR NOT NULL,
                target_user_id BIGINT NULL REFERENCES users(user_id),
                expires_at TIMESTAMPTZ NOT NULL,
                consumed_at TIMESTAMPTZ NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_email_verification_codes_lookup
            ON email_verification_codes (email, purpose, target_user_id, created_at DESC)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_email_verification_codes_expires_at
            ON email_verification_codes (expires_at)
            """
        )
    )


def _migration_0006_add_security_throttles(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS security_throttles (
                throttle_id SERIAL PRIMARY KEY,
                scope VARCHAR(64) NOT NULL,
                identifier VARCHAR(512) NOT NULL,
                failures INTEGER NOT NULL DEFAULT 0,
                window_started_at TIMESTAMPTZ NULL,
                locked_until TIMESTAMPTZ NULL,
                last_attempt_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                CONSTRAINT uq_security_throttles_scope_identifier UNIQUE (scope, identifier)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_security_throttles_scope
            ON security_throttles (scope)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_security_throttles_locked_until
            ON security_throttles (locked_until)
            """
        )
    )


def _migration_0007_add_telegram_photo_url(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "telegram_photo_url" in columns:
        return

    connection.execute(
        text("ALTER TABLE users ADD COLUMN telegram_photo_url TEXT")
    )


def _migration_0008_add_email_verification_code_status(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("email_verification_codes")}

    if "status" not in columns:
        connection.execute(
            text(
                "ALTER TABLE email_verification_codes ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active'"
            )
        )
    else:
        connection.execute(
            text(
                """
                UPDATE email_verification_codes
                SET status = 'active'
                WHERE status IS NULL OR status = ''
                """
            )
        )

    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_email_verification_codes_status
            ON email_verification_codes (status)
            """
        )
    )


def _migration_0010_add_email_magic_token_hash(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("email_verification_codes")}

    if "magic_token_hash" not in columns:
        connection.execute(
            text(
                "ALTER TABLE email_verification_codes ADD COLUMN magic_token_hash VARCHAR"
            )
        )

    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_email_verification_codes_magic_token_hash
            ON email_verification_codes (magic_token_hash)
            """
        )
    )


def _migration_0009_add_composite_indexes(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_subscriptions_is_active_end_date
            ON subscriptions (is_active, end_date)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id_is_active
            ON subscriptions (user_id, is_active)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_payments_user_id_status
            ON payments (user_id, status)
            """
        )
    )


MIGRATIONS: List[Migration] = [
    Migration(
        id="0001_add_channel_subscription_fields",
        description="Add columns to track required channel subscription verification",
        upgrade=_migration_0001_add_channel_subscription_fields,
    ),
    Migration(
        id="0002_add_referral_code",
        description="Store short referral codes for users and backfill existing rows",
        upgrade=_migration_0002_add_referral_code,
    ),
    Migration(
        id="0003_normalize_referral_codes",
        description="Normalize referral codes to uppercase for consistent lookups",
        upgrade=_migration_0003_normalize_referral_codes,
    ),
    Migration(
        id="0004_add_lifetime_used_traffic",
        description="Store lifetime traffic usage for users",
        upgrade=_migration_0004_add_lifetime_used_traffic,
    ),
    Migration(
        id="0005_add_email_auth_fields",
        description="Add email login identities and verification codes",
        upgrade=_migration_0005_add_email_auth_fields,
    ),
    Migration(
        id="0006_add_security_throttles",
        description="Add generic lockout tracking for brute-force protection",
        upgrade=_migration_0006_add_security_throttles,
    ),
    Migration(
        id="0007_add_telegram_photo_url",
        description="Store Telegram profile photo URLs for linked users",
        upgrade=_migration_0007_add_telegram_photo_url,
    ),
    Migration(
        id="0008_add_email_verification_code_status",
        description="Track superseded email verification codes explicitly",
        upgrade=_migration_0008_add_email_verification_code_status,
    ),
    Migration(
        id="0009_add_composite_indexes",
        description="Add composite indexes for subscription and payment lookups",
        upgrade=_migration_0009_add_composite_indexes,
    ),
    Migration(
        id="0010_add_email_magic_token_hash",
        description="Store hashed magic-link tokens for email login deeplinks",
        upgrade=_migration_0010_add_email_magic_token_hash,
    ),
]


def run_database_migrations(connection: Connection) -> None:
    """
    Apply pending migrations sequentially. Already applied revisions are skipped.
    """
    _ensure_migrations_table(connection)

    applied_revisions: Set[str] = {
        row[0]
        for row in connection.execute(
            text("SELECT id FROM schema_migrations")
        )
    }

    for migration in MIGRATIONS:
        if migration.id in applied_revisions:
            continue

        logging.info(
            "Migrator: applying %s – %s", migration.id, migration.description
        )
        try:
            with connection.begin_nested():
                migration.upgrade(connection)
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations (id) VALUES (:revision)"
                    ),
                    {"revision": migration.id},
                )
        except Exception as exc:
            logging.error(
                "Migrator: failed to apply %s (%s)",
                migration.id,
                migration.description,
                exc_info=True,
            )
            raise exc
        else:
            logging.info("Migrator: migration %s applied successfully", migration.id)
