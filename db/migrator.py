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


def _migration_0011_add_user_telegram_avatars(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS user_telegram_avatars (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                file_unique_id VARCHAR,
                content_type VARCHAR(64) NOT NULL DEFAULT 'image/jpeg',
                image_bytes BYTEA NOT NULL,
                size_bytes INTEGER NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_user_telegram_avatars_file_unique_id
            ON user_telegram_avatars (file_unique_id)
            """
        )
    )


def _migration_0012_add_tariffs_schema(connection: Connection) -> None:
    inspector = inspect(connection)

    sub_columns: Set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    sub_statements: List[str] = []
    if "tariff_key" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tariff_key VARCHAR")
    if "tier_baseline_bytes" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tier_baseline_bytes BIGINT")
    if "topup_balance_bytes" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN topup_balance_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_baseline_bytes" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_baseline_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_topup_balance_bytes" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_topup_balance_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_topup_used_bytes" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_used_bytes" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_used_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_is_limited" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_is_limited BOOLEAN NOT NULL DEFAULT FALSE")
    if "premium_period_start_at" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_period_start_at TIMESTAMPTZ")
    if "period_start_at" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN period_start_at TIMESTAMPTZ")
    if "is_throttled" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN is_throttled BOOLEAN NOT NULL DEFAULT FALSE")
    if "effective_monthly_price_rub" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN effective_monthly_price_rub NUMERIC")
    if "hwid_device_limit" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN hwid_device_limit INTEGER")
    if "extra_hwid_devices" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN extra_hwid_devices INTEGER NOT NULL DEFAULT 0")
    for stmt in sub_statements:
        connection.execute(text(stmt))

    payment_columns: Set[str] = {col["name"] for col in inspector.get_columns("payments")}
    payment_statements: List[str] = []
    if "sale_mode" not in payment_columns:
        payment_statements.append("ALTER TABLE payments ADD COLUMN sale_mode VARCHAR")
    if "tariff_key" not in payment_columns:
        payment_statements.append("ALTER TABLE payments ADD COLUMN tariff_key VARCHAR")
    if "purchased_gb" not in payment_columns:
        payment_statements.append("ALTER TABLE payments ADD COLUMN purchased_gb DOUBLE PRECISION")
    if "purchased_hwid_devices" not in payment_columns:
        payment_statements.append("ALTER TABLE payments ADD COLUMN purchased_hwid_devices INTEGER")
    for stmt in payment_statements:
        connection.execute(text(stmt))

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS traffic_topups (
                topup_id SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
                payment_id INTEGER NULL REFERENCES payments(payment_id),
                purchased_bytes BIGINT NOT NULL,
                kind VARCHAR NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS traffic_warnings (
                warning_id SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
                period_start_at TIMESTAMPTZ NULL,
                level INTEGER NOT NULL,
                traffic_limit_bytes BIGINT NULL,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_traffic_warning_period_level UNIQUE (subscription_id, period_start_at, level)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS hwid_device_purchases (
                purchase_id SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
                payment_id INTEGER NULL REFERENCES payments(payment_id),
                purchased_devices INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tariff_changes (
                change_id SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
                from_tariff_key VARCHAR NULL,
                to_tariff_key VARCHAR NOT NULL,
                mode VARCHAR NOT NULL,
                payment_id INTEGER NULL REFERENCES payments(payment_id),
                days_before INTEGER NULL,
                days_after INTEGER NULL,
                converted_bytes BIGINT NULL,
                eff_price_before NUMERIC NULL,
                eff_price_after NUMERIC NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    for stmt in [
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_tariff_key ON subscriptions (tariff_key)",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_is_throttled ON subscriptions (is_throttled)",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_premium_is_limited ON subscriptions (premium_is_limited)",
        "CREATE INDEX IF NOT EXISTS ix_payments_sale_mode ON payments (sale_mode)",
        "CREATE INDEX IF NOT EXISTS ix_payments_tariff_key ON payments (tariff_key)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_topups_subscription_id ON traffic_topups (subscription_id)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_topups_payment_id ON traffic_topups (payment_id)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_topups_kind ON traffic_topups (kind)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_warnings_subscription_id ON traffic_warnings (subscription_id)",
        "CREATE INDEX IF NOT EXISTS ix_tariff_changes_subscription_id ON tariff_changes (subscription_id)",
        "CREATE INDEX IF NOT EXISTS ix_hwid_device_purchases_subscription_id ON hwid_device_purchases (subscription_id)",
        "CREATE INDEX IF NOT EXISTS ix_hwid_device_purchases_payment_id ON hwid_device_purchases (payment_id)",
    ]:
        connection.execute(text(stmt))


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


def _migration_0014_add_premium_squad_traffic_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    sub_columns: Set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    statements: List[str] = []
    if "premium_baseline_bytes" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_baseline_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_topup_balance_bytes" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_topup_balance_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_topup_used_bytes" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_used_bytes" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_used_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_is_limited" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_is_limited BOOLEAN NOT NULL DEFAULT FALSE")
    if "premium_period_start_at" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_period_start_at TIMESTAMPTZ")
    for stmt in statements:
        connection.execute(text(stmt))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_subscriptions_premium_is_limited ON subscriptions (premium_is_limited)"
        )
    )


def _migration_0015_add_premium_topup_carryover_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    sub_columns: Set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    statements: List[str] = []
    if "premium_topup_used_bytes" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0")
    if "premium_period_start_at" not in sub_columns:
        statements.append("ALTER TABLE subscriptions ADD COLUMN premium_period_start_at TIMESTAMPTZ")
    for stmt in statements:
        connection.execute(text(stmt))


def _migration_0016_add_message_logs_admin_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: Set[str] = {col["name"] for col in inspector.get_columns("message_logs")}
    statements: List[str] = []

    if "is_admin_event" not in columns:
        statements.append(
            "ALTER TABLE message_logs ADD COLUMN is_admin_event BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if "target_user_id" not in columns:
        statements.append(
            "ALTER TABLE message_logs ADD COLUMN target_user_id BIGINT REFERENCES users(user_id)"
        )

    for stmt in statements:
        connection.execute(text(stmt))

    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_message_logs_target_user_id ON message_logs (target_user_id)"
        )
    )


def _migration_0017_reconcile_legacy_admin_api_schema(connection: Connection) -> None:
    """Backfill columns required by admin user detail API on legacy databases.

    Some self-hosted instances were upgraded from older builds where parts of
    the tariffs/admin schema were missing. This migration is intentionally
    idempotent and only adds absent columns/indexes.
    """
    inspector = inspect(connection)

    table_names = set(inspector.get_table_names())
    if "subscriptions" in table_names:
        sub_columns: Set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
        sub_statements: List[str] = []
        if "tariff_key" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tariff_key VARCHAR")
        if "tier_baseline_bytes" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tier_baseline_bytes BIGINT")
        if "topup_balance_bytes" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN topup_balance_bytes BIGINT NOT NULL DEFAULT 0")
        if "premium_baseline_bytes" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_baseline_bytes BIGINT NOT NULL DEFAULT 0")
        if "premium_topup_balance_bytes" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_topup_balance_bytes BIGINT NOT NULL DEFAULT 0")
        if "premium_topup_used_bytes" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0")
        if "premium_used_bytes" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_used_bytes BIGINT NOT NULL DEFAULT 0")
        if "premium_is_limited" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN premium_is_limited BOOLEAN NOT NULL DEFAULT FALSE")
        if "is_throttled" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN is_throttled BOOLEAN NOT NULL DEFAULT FALSE")
        for stmt in sub_statements:
            connection.execute(text(stmt))

    if "payments" in table_names:
        pay_columns: Set[str] = {col["name"] for col in inspector.get_columns("payments")}
        pay_statements: List[str] = []
        if "sale_mode" not in pay_columns:
            pay_statements.append("ALTER TABLE payments ADD COLUMN sale_mode VARCHAR")
        if "tariff_key" not in pay_columns:
            pay_statements.append("ALTER TABLE payments ADD COLUMN tariff_key VARCHAR")
        if "purchased_gb" not in pay_columns:
            pay_statements.append("ALTER TABLE payments ADD COLUMN purchased_gb DOUBLE PRECISION")
        if "purchased_hwid_devices" not in pay_columns:
            pay_statements.append("ALTER TABLE payments ADD COLUMN purchased_hwid_devices INTEGER")
        for stmt in pay_statements:
            connection.execute(text(stmt))

    if "message_logs" in table_names:
        msg_columns: Set[str] = {col["name"] for col in inspector.get_columns("message_logs")}
        msg_statements: List[str] = []
        if "is_admin_event" not in msg_columns:
            msg_statements.append("ALTER TABLE message_logs ADD COLUMN is_admin_event BOOLEAN NOT NULL DEFAULT FALSE")
        if "target_user_id" not in msg_columns:
            msg_statements.append("ALTER TABLE message_logs ADD COLUMN target_user_id BIGINT REFERENCES users(user_id)")
        for stmt in msg_statements:
            connection.execute(text(stmt))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_message_logs_target_user_id ON message_logs (target_user_id)"
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
    Migration(
        id="0011_add_user_telegram_avatars",
        description="Cache compact Telegram profile avatars for WebApp profiles",
        upgrade=_migration_0011_add_user_telegram_avatars,
    ),
    Migration(
        id="0012_add_tariffs_schema",
        description="Add tariff catalog columns and traffic accounting tables",
        upgrade=_migration_0012_add_tariffs_schema,
    ),
    Migration(
        id="0013_add_app_setting_overrides",
        description="Persisted runtime overrides for application settings managed via admin webapp",
        upgrade=lambda connection: connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS app_setting_overrides (
                    key VARCHAR(128) PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_by BIGINT
                )
                """
            )
        ),
    ),
    Migration(
        id="0014_add_premium_squad_traffic_fields",
        description="Track premium squad traffic limits and top-ups per subscription",
        upgrade=_migration_0014_add_premium_squad_traffic_fields,
    ),
    Migration(
        id="0015_add_premium_topup_carryover_fields",
        description="Track premium top-up usage within the current monthly period",
        upgrade=_migration_0015_add_premium_topup_carryover_fields,
    ),
    Migration(
        id="0016_add_message_logs_admin_fields",
        description="Add admin-related message log fields used by admin user detail APIs",
        upgrade=_migration_0016_add_message_logs_admin_fields,
    ),
    Migration(
        id="0017_reconcile_legacy_admin_api_schema",
        description="Reconcile legacy DB schema for admin user detail endpoint compatibility",
        upgrade=_migration_0017_reconcile_legacy_admin_api_schema,
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
