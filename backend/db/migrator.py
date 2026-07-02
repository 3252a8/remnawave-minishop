import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from config.settings import Settings

CORE_MIGRATION_NAMESPACE = "core"


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
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
    statements: list[str] = []

    if "channel_subscription_verified" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN channel_subscription_verified BOOLEAN")
    if "channel_subscription_checked_at" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN channel_subscription_checked_at TIMESTAMPTZ"
        )
    if "channel_subscription_verified_for" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN channel_subscription_verified_for BIGINT")

    for stmt in statements:
        connection.execute(text(stmt))


def _migration_0002_add_referral_code(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}

    if "referral_code" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN referral_code VARCHAR(16)"))

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
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
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
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "lifetime_used_traffic_bytes" in columns:
        return

    connection.execute(text("ALTER TABLE users ADD COLUMN lifetime_used_traffic_bytes BIGINT"))


def _migration_0005_add_email_auth_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}

    if "email" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR"))
    if "email_verified_at" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ"))
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
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "telegram_photo_url" in columns:
        return

    connection.execute(text("ALTER TABLE users ADD COLUMN telegram_photo_url TEXT"))


def _migration_0008_add_email_verification_code_status(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("email_verification_codes")}

    if "status" not in columns:
        connection.execute(
            text(
                "ALTER TABLE email_verification_codes ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active'"  # noqa: E501
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
    columns: set[str] = {col["name"] for col in inspector.get_columns("email_verification_codes")}

    if "magic_token_hash" not in columns:
        connection.execute(
            text("ALTER TABLE email_verification_codes ADD COLUMN magic_token_hash VARCHAR")
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

    sub_columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    sub_statements: list[str] = []
    if "tariff_key" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tariff_key VARCHAR")
    if "tier_baseline_bytes" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tier_baseline_bytes BIGINT")
    if "topup_balance_bytes" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN topup_balance_bytes BIGINT NOT NULL DEFAULT 0"
        )
    if "premium_baseline_bytes" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_baseline_bytes BIGINT NOT NULL DEFAULT 0"
        )
    if "premium_topup_balance_bytes" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_topup_balance_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
        )
    if "premium_topup_used_bytes" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
        )
    if "premium_used_bytes" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_used_bytes BIGINT NOT NULL DEFAULT 0"
        )
    if "premium_is_limited" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_is_limited BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if "premium_period_start_at" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_period_start_at TIMESTAMPTZ"
        )
    if "period_start_at" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN period_start_at TIMESTAMPTZ")
    if "is_throttled" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN is_throttled BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if "effective_monthly_price_rub" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN effective_monthly_price_rub NUMERIC"
        )
    if "hwid_device_limit" not in sub_columns:
        sub_statements.append("ALTER TABLE subscriptions ADD COLUMN hwid_device_limit INTEGER")
    if "extra_hwid_devices" not in sub_columns:
        sub_statements.append(
            "ALTER TABLE subscriptions ADD COLUMN extra_hwid_devices INTEGER NOT NULL DEFAULT 0"
        )
    for stmt in sub_statements:
        connection.execute(text(stmt))

    payment_columns: set[str] = {col["name"] for col in inspector.get_columns("payments")}
    payment_statements: list[str] = []
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
            """  # noqa: E501
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
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_premium_is_limited ON subscriptions (premium_is_limited)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_payments_sale_mode ON payments (sale_mode)",
        "CREATE INDEX IF NOT EXISTS ix_payments_tariff_key ON payments (tariff_key)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_topups_subscription_id ON traffic_topups (subscription_id)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_traffic_topups_payment_id ON traffic_topups (payment_id)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_topups_kind ON traffic_topups (kind)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_warnings_subscription_id ON traffic_warnings (subscription_id)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_tariff_changes_subscription_id ON tariff_changes (subscription_id)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_hwid_device_purchases_subscription_id ON hwid_device_purchases (subscription_id)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_hwid_device_purchases_payment_id ON hwid_device_purchases (payment_id)",  # noqa: E501
    ]:
        connection.execute(text(stmt))


def _migration_0013_add_app_setting_overrides(connection: Connection) -> None:
    connection.execute(
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


def _migration_0014_add_premium_squad_traffic_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    sub_columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    statements: list[str] = []
    if "premium_baseline_bytes" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_baseline_bytes BIGINT NOT NULL DEFAULT 0"
        )
    if "premium_topup_balance_bytes" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_topup_balance_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
        )
    if "premium_topup_used_bytes" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
        )
    if "premium_used_bytes" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_used_bytes BIGINT NOT NULL DEFAULT 0"
        )
    if "premium_is_limited" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_is_limited BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if "premium_period_start_at" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_period_start_at TIMESTAMPTZ"
        )
    for stmt in statements:
        connection.execute(text(stmt))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_subscriptions_premium_is_limited ON subscriptions (premium_is_limited)"  # noqa: E501
        )
    )


def _migration_0015_add_premium_topup_carryover_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    sub_columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    statements: list[str] = []
    if "premium_topup_used_bytes" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
        )
    if "premium_period_start_at" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_period_start_at TIMESTAMPTZ"
        )
    for stmt in statements:
        connection.execute(text(stmt))


def _migration_0016_add_message_logs_admin_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("message_logs")}
    statements: list[str] = []

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
            "CREATE INDEX IF NOT EXISTS ix_message_logs_target_user_id ON message_logs (target_user_id)"  # noqa: E501
        )
    )


def _migration_0018_add_premium_admin_overrides(connection: Connection) -> None:
    """Per-subscription overrides letting admins gift extra premium traffic or unlimited access."""
    inspector = inspect(connection)
    sub_columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    statements: list[str] = []
    if "premium_unlimited_override" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_unlimited_override BOOLEAN NOT NULL DEFAULT FALSE"  # noqa: E501
        )
    if "premium_bonus_bytes" not in sub_columns:
        statements.append(
            "ALTER TABLE subscriptions ADD COLUMN premium_bonus_bytes BIGINT NOT NULL DEFAULT 0"
        )
    for stmt in statements:
        connection.execute(text(stmt))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_subscriptions_premium_unlimited_override "
            "ON subscriptions (premium_unlimited_override)"
        )
    )


def _migration_0021_add_regular_unlimited_override(connection: Connection) -> None:
    inspector = inspect(connection)
    sub_columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    if "regular_unlimited_override" not in sub_columns:
        connection.execute(
            text(
                "ALTER TABLE subscriptions ADD COLUMN regular_unlimited_override BOOLEAN NOT NULL DEFAULT FALSE"  # noqa: E501
            )
        )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_subscriptions_regular_unlimited_override "
            "ON subscriptions (regular_unlimited_override)"
        )
    )


def _migration_0020_add_regular_bonus_bytes(connection: Connection) -> None:
    """Admin-granted extra bytes on main (non-premium) traffic limit, like premium_bonus_bytes."""
    inspector = inspect(connection)
    sub_columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    if "regular_bonus_bytes" not in sub_columns:
        connection.execute(
            text(
                "ALTER TABLE subscriptions ADD COLUMN regular_bonus_bytes BIGINT NOT NULL DEFAULT 0"
            )
        )


def _migration_0019_clear_subscription_months_for_non_subscription_payments(
    connection: Connection,
) -> None:
    """Null out subscription_duration_months for legacy non-subscription payments.

    Older builds stored the raw `months` callback value into
    `subscription_duration_months` for every sale_mode, including traffic
    top-ups and HWID device packs. This polluted CSV exports and made admin
    log messages render top-ups as "N мес.". The new code only sets the
    column for subscription sales; this migration aligns historical rows.
    """
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "payments" not in table_names:
        return
    pay_columns: set[str] = {col["name"] for col in inspector.get_columns("payments")}
    if "subscription_duration_months" not in pay_columns or "sale_mode" not in pay_columns:
        return
    connection.execute(
        text(
            """
            UPDATE payments
            SET subscription_duration_months = NULL
            WHERE subscription_duration_months IS NOT NULL
              AND sale_mode IS NOT NULL
              AND split_part(split_part(sale_mode, '@', 1), '|', 1) <> 'subscription'
            """
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
        sub_columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
        sub_statements: list[str] = []
        if "tariff_key" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tariff_key VARCHAR")
        if "tier_baseline_bytes" not in sub_columns:
            sub_statements.append("ALTER TABLE subscriptions ADD COLUMN tier_baseline_bytes BIGINT")
        if "topup_balance_bytes" not in sub_columns:
            sub_statements.append(
                "ALTER TABLE subscriptions ADD COLUMN topup_balance_bytes BIGINT NOT NULL DEFAULT 0"
            )
        if "premium_baseline_bytes" not in sub_columns:
            sub_statements.append(
                "ALTER TABLE subscriptions ADD COLUMN premium_baseline_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
            )
        if "premium_topup_balance_bytes" not in sub_columns:
            sub_statements.append(
                "ALTER TABLE subscriptions ADD COLUMN premium_topup_balance_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
            )
        if "premium_topup_used_bytes" not in sub_columns:
            sub_statements.append(
                "ALTER TABLE subscriptions ADD COLUMN premium_topup_used_bytes BIGINT NOT NULL DEFAULT 0"  # noqa: E501
            )
        if "premium_used_bytes" not in sub_columns:
            sub_statements.append(
                "ALTER TABLE subscriptions ADD COLUMN premium_used_bytes BIGINT NOT NULL DEFAULT 0"
            )
        if "premium_is_limited" not in sub_columns:
            sub_statements.append(
                "ALTER TABLE subscriptions ADD COLUMN premium_is_limited BOOLEAN NOT NULL DEFAULT FALSE"  # noqa: E501
            )
        if "is_throttled" not in sub_columns:
            sub_statements.append(
                "ALTER TABLE subscriptions ADD COLUMN is_throttled BOOLEAN NOT NULL DEFAULT FALSE"
            )
        for stmt in sub_statements:
            connection.execute(text(stmt))

    if "payments" in table_names:
        pay_columns: set[str] = {col["name"] for col in inspector.get_columns("payments")}
        pay_statements: list[str] = []
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
        msg_columns: set[str] = {col["name"] for col in inspector.get_columns("message_logs")}
        msg_statements: list[str] = []
        if "is_admin_event" not in msg_columns:
            msg_statements.append(
                "ALTER TABLE message_logs ADD COLUMN is_admin_event BOOLEAN NOT NULL DEFAULT FALSE"
            )
        if "target_user_id" not in msg_columns:
            msg_statements.append(
                "ALTER TABLE message_logs ADD COLUMN target_user_id BIGINT REFERENCES users(user_id)"  # noqa: E501
            )
        for stmt in msg_statements:
            connection.execute(text(stmt))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_message_logs_target_user_id ON message_logs (target_user_id)"  # noqa: E501
            )
        )


def _migration_0022_add_indexes_for_admin_reports(connection: Connection) -> None:
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_payments_status_created_at "
            "ON payments (status, created_at)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_message_logs_timestamp ON message_logs (timestamp DESC)"
        )
    )


def _migration_0023_add_email_password_auth_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}

    if "password_hash" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR"))
    if "password_set_at" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN password_set_at TIMESTAMPTZ"))


def _migration_0024_add_support_tickets(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                ticket_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                subject VARCHAR(160) NOT NULL,
                category VARCHAR(32) NOT NULL DEFAULT 'other',
                priority VARCHAR(16) NOT NULL DEFAULT 'normal',
                status VARCHAR(24) NOT NULL DEFAULT 'open',
                assigned_admin_id BIGINT NULL,
                last_message_at TIMESTAMPTZ DEFAULT NOW(),
                last_message_role VARCHAR(16) NULL,
                unread_user_count INTEGER NOT NULL DEFAULT 0,
                unread_admin_count INTEGER NOT NULL DEFAULT 0,
                admin_last_notified_at TIMESTAMPTZ NULL,
                admin_last_emailed_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                closed_at TIMESTAMPTZ NULL,
                closed_by_admin_id BIGINT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS support_ticket_messages (
                message_id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES support_tickets(ticket_id) ON DELETE CASCADE,
                author_role VARCHAR(16) NOT NULL,
                author_user_id BIGINT NULL REFERENCES users(user_id),
                body TEXT NOT NULL,
                is_internal_note BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                read_by_user_at TIMESTAMPTZ NULL,
                read_by_admin_at TIMESTAMPTZ NULL
            )
            """
        )
    )

    inspector = inspect(connection)
    ticket_columns: set[str] = {col["name"] for col in inspector.get_columns("support_tickets")}
    ticket_column_sql = {
        "user_id": "BIGINT NOT NULL REFERENCES users(user_id)",
        "subject": "VARCHAR(160) NOT NULL DEFAULT ''",
        "category": "VARCHAR(32) NOT NULL DEFAULT 'other'",
        "priority": "VARCHAR(16) NOT NULL DEFAULT 'normal'",
        "status": "VARCHAR(24) NOT NULL DEFAULT 'open'",
        "assigned_admin_id": "BIGINT NULL",
        "last_message_at": "TIMESTAMPTZ DEFAULT NOW()",
        "last_message_role": "VARCHAR(16) NULL",
        "unread_user_count": "INTEGER NOT NULL DEFAULT 0",
        "unread_admin_count": "INTEGER NOT NULL DEFAULT 0",
        "admin_last_notified_at": "TIMESTAMPTZ NULL",
        "admin_last_emailed_at": "TIMESTAMPTZ NULL",
        "created_at": "TIMESTAMPTZ DEFAULT NOW()",
        "updated_at": "TIMESTAMPTZ NULL",
        "closed_at": "TIMESTAMPTZ NULL",
        "closed_by_admin_id": "BIGINT NULL",
    }
    for column, definition in ticket_column_sql.items():
        if column not in ticket_columns:
            connection.execute(
                text(f"ALTER TABLE support_tickets ADD COLUMN {column} {definition}")
            )

    message_columns: set[str] = {
        col["name"] for col in inspector.get_columns("support_ticket_messages")
    }
    message_column_sql = {
        "ticket_id": "INTEGER NOT NULL REFERENCES support_tickets(ticket_id) ON DELETE CASCADE",
        "author_role": "VARCHAR(16) NOT NULL DEFAULT 'user'",
        "author_user_id": "BIGINT NULL REFERENCES users(user_id)",
        "body": "TEXT NOT NULL DEFAULT ''",
        "is_internal_note": "BOOLEAN NOT NULL DEFAULT FALSE",
        "created_at": "TIMESTAMPTZ DEFAULT NOW()",
        "read_by_user_at": "TIMESTAMPTZ NULL",
        "read_by_admin_at": "TIMESTAMPTZ NULL",
    }
    for column, definition in message_column_sql.items():
        if column not in message_columns:
            connection.execute(
                text(f"ALTER TABLE support_ticket_messages ADD COLUMN {column} {definition}")
            )

    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_user_id ON support_tickets (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_category ON support_tickets (category)",
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_priority ON support_tickets (priority)",
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets (status)",
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_assigned_admin_id ON support_tickets (assigned_admin_id)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_last_message_at ON support_tickets (last_message_at)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_status_last_msg ON support_tickets (status, last_message_at)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_support_ticket_messages_ticket_id ON support_ticket_messages (ticket_id)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_support_ticket_messages_author_user_id ON support_ticket_messages (author_user_id)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_support_ticket_messages_is_internal_note ON support_ticket_messages (is_internal_note)",  # noqa: E501
        "CREATE INDEX IF NOT EXISTS ix_support_ticket_messages_created_at ON support_ticket_messages (created_at)",  # noqa: E501
    ]
    for stmt in index_statements:
        connection.execute(text(stmt))


def _migration_0025_add_support_notification_timestamps(connection: Connection) -> None:
    inspector = inspect(connection)
    ticket_columns: set[str] = {col["name"] for col in inspector.get_columns("support_tickets")}
    column_sql = {
        "admin_last_notified_at": "TIMESTAMPTZ NULL",
        "admin_last_emailed_at": "TIMESTAMPTZ NULL",
    }
    for column, definition in column_sql.items():
        if column not in ticket_columns:
            connection.execute(
                text(f"ALTER TABLE support_tickets ADD COLUMN {column} {definition}")
            )


def _migration_0026_add_lifetime_traffic_synced_at(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "lifetime_used_traffic_synced_at" not in columns:
        connection.execute(
            text("ALTER TABLE users ADD COLUMN lifetime_used_traffic_synced_at TIMESTAMPTZ")
        )


def _migration_0027_add_subscription_install_share_token(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}

    if "install_share_token" not in columns:
        connection.execute(
            text("ALTER TABLE subscriptions ADD COLUMN install_share_token VARCHAR(32)")
        )

    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_install_share_token
            ON subscriptions (install_share_token)
            WHERE install_share_token IS NOT NULL
            """
        )
    )


def _migration_0028_add_locale_overrides(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS locale_overrides (
                lang VARCHAR(16) NOT NULL,
                key VARCHAR(255) NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by BIGINT,
                PRIMARY KEY (lang, key)
            )
            """
        )
    )


def _migration_0029_add_hwid_device_purchase_validity(connection: Connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "hwid_device_purchases" not in table_names or "subscriptions" not in table_names:
        return

    columns: set[str] = {col["name"] for col in inspector.get_columns("hwid_device_purchases")}
    if "valid_from" not in columns:
        connection.execute(
            text("ALTER TABLE hwid_device_purchases ADD COLUMN valid_from TIMESTAMPTZ")
        )
    if "valid_until" not in columns:
        connection.execute(
            text("ALTER TABLE hwid_device_purchases ADD COLUMN valid_until TIMESTAMPTZ")
        )

    connection.execute(
        text(
            """
            UPDATE hwid_device_purchases hp
            SET
                valid_from = COALESCE(hp.valid_from, hp.created_at, s.start_date, NOW()),
                valid_until = COALESCE(hp.valid_until, s.end_date)
            FROM subscriptions s
            WHERE hp.subscription_id = s.subscription_id
              AND (hp.valid_from IS NULL OR hp.valid_until IS NULL)
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO hwid_device_purchases (
                subscription_id,
                payment_id,
                purchased_devices,
                valid_from,
                valid_until
            )
            SELECT
                s.subscription_id,
                NULL,
                s.extra_hwid_devices,
                COALESCE(s.start_date, NOW()),
                s.end_date
            FROM subscriptions s
            WHERE COALESCE(s.extra_hwid_devices, 0) > 0
              AND s.end_date IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM hwid_device_purchases hp
                  WHERE hp.subscription_id = s.subscription_id
              )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_hwid_device_purchases_subscription_window "
            "ON hwid_device_purchases (subscription_id, valid_from, valid_until)"
        )
    )


def _migration_0030_add_hwid_pricing_metadata(connection: Connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "payments" in table_names:
        payment_columns: set[str] = {col["name"] for col in inspector.get_columns("payments")}
        payment_additions = {
            "hwid_valid_from": "TIMESTAMPTZ",
            "hwid_valid_until": "TIMESTAMPTZ",
            "hwid_pricing_period_months": "INTEGER",
            "hwid_proration_ratio": "DOUBLE PRECISION",
            "hwid_full_price": "DOUBLE PRECISION",
        }
        for column, ddl_type in payment_additions.items():
            if column not in payment_columns:
                connection.execute(text(f"ALTER TABLE payments ADD COLUMN {column} {ddl_type}"))

    if "tariff_changes" in table_names:
        change_columns: set[str] = {col["name"] for col in inspector.get_columns("tariff_changes")}
        change_additions = {
            "converted_hwid_value_rub": "NUMERIC",
            "converted_hwid_days": "INTEGER",
        }
        for column, ddl_type in change_additions.items():
            if column not in change_columns:
                connection.execute(
                    text(f"ALTER TABLE tariff_changes ADD COLUMN {column} {ddl_type}")
                )


def _migration_0031_add_subscription_notifications(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS subscription_notifications (
                notification_id SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
                notification_key VARCHAR(64) NOT NULL,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_subscription_notification_key UNIQUE (
                    subscription_id,
                    notification_key
                )
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_subscription_notifications_subscription_id
            ON subscription_notifications (subscription_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_subscription_notifications_notification_key
            ON subscription_notifications (notification_key)
            """
        )
    )


def _migration_0032_add_telegram_notification_status(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
    additions = {
        "telegram_notifications_status": "VARCHAR(32) NOT NULL DEFAULT 'unknown'",
        "telegram_notifications_checked_at": "TIMESTAMPTZ",
        "telegram_notifications_enabled_at": "TIMESTAMPTZ",
        "telegram_notifications_blocked_at": "TIMESTAMPTZ",
    }
    for column, ddl_type in additions.items():
        if column not in columns:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {column} {ddl_type}"))


def _migration_0033_add_trial_eligibility_reset_marker(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "trial_eligibility_reset_at" not in columns:
        connection.execute(
            text("ALTER TABLE users ADD COLUMN trial_eligibility_reset_at TIMESTAMPTZ")
        )


def _migration_0034_add_legacy_import_compatibility(connection: Connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())

    if "users" in table_names:
        columns = {col["name"]: col for col in inspector.get_columns("users")}
        referral_column = columns.get("referral_code")
        length = getattr(referral_column.get("type"), "length", None) if referral_column else None
        if referral_column and (length is None or int(length) < 64):
            connection.execute(
                text("ALTER TABLE users ALTER COLUMN referral_code TYPE VARCHAR(64)")
            )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS legacy_referral_codes (
                legacy_code_id SERIAL PRIMARY KEY,
                source VARCHAR(64) NOT NULL DEFAULT 'remnashop',
                code VARCHAR(128) NOT NULL,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                CONSTRAINT uq_legacy_referral_source_code UNIQUE (source, code)
            )
            """
        )
    )
    for stmt in [
        (
            "CREATE INDEX IF NOT EXISTS ix_legacy_referral_codes_source "
            "ON legacy_referral_codes (source)"
        ),
        "CREATE INDEX IF NOT EXISTS ix_legacy_referral_codes_code ON legacy_referral_codes (code)",
        (
            "CREATE INDEX IF NOT EXISTS ix_legacy_referral_codes_user_id "
            "ON legacy_referral_codes (user_id)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS ix_legacy_referral_codes_is_active "
            "ON legacy_referral_codes (is_active)"
        ),
    ]:
        connection.execute(text(stmt))

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS legacy_import_mappings (
                source VARCHAR(64) NOT NULL,
                entity_type VARCHAR(64) NOT NULL,
                source_id VARCHAR(128) NOT NULL,
                target_table VARCHAR(128) NOT NULL,
                target_id VARCHAR(128) NOT NULL,
                metadata_json TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                PRIMARY KEY (source, entity_type, source_id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_legacy_import_mappings_target
            ON legacy_import_mappings (target_table, target_id)
            """
        )
    )


def _migration_0035_add_subscription_promo_expiry_flag(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    if "suppress_early_expiry_notifications" not in columns:
        connection.execute(
            text(
                "ALTER TABLE subscriptions ADD COLUMN suppress_early_expiry_notifications "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )


def _migration_0036_add_provider_payment_url(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("payments")}
    if "provider_payment_url" not in columns:
        connection.execute(text("ALTER TABLE payments ADD COLUMN provider_payment_url VARCHAR"))


def _migration_0037_add_referral_welcome_bonus_marker(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("users")}
    if "referral_welcome_bonus_claimed_at" not in columns:
        connection.execute(
            text("ALTER TABLE users ADD COLUMN referral_welcome_bonus_claimed_at TIMESTAMPTZ")
        )


def _migration_0038_extend_promo_code_effects(connection: Connection) -> None:
    inspector = inspect(connection)
    columns_info = inspector.get_columns("promo_codes")
    columns: set[str] = {col["name"] for col in columns_info}
    statements: list[str] = []

    if "discount_percent" not in columns:
        statements.append("ALTER TABLE promo_codes ADD COLUMN discount_percent NUMERIC(5, 2)")
    if "duration_multiplier" not in columns:
        statements.append("ALTER TABLE promo_codes ADD COLUMN duration_multiplier NUMERIC(6, 3)")
    if "traffic_multiplier" not in columns:
        statements.append("ALTER TABLE promo_codes ADD COLUMN traffic_multiplier NUMERIC(6, 3)")
    if "applies_to" not in columns:
        statements.append(
            "ALTER TABLE promo_codes ADD COLUMN applies_to VARCHAR(32) NOT NULL DEFAULT 'all'"
        )
    if "min_subscription_months" not in columns:
        statements.append("ALTER TABLE promo_codes ADD COLUMN min_subscription_months INTEGER")
    if "min_traffic_gb" not in columns:
        statements.append("ALTER TABLE promo_codes ADD COLUMN min_traffic_gb NUMERIC(10, 2)")
    if "origin" not in columns:
        statements.append(
            "ALTER TABLE promo_codes ADD COLUMN origin VARCHAR(32) NOT NULL DEFAULT 'admin'"
        )

    for stmt in statements:
        connection.execute(text(stmt))

    created_by = next(
        (col for col in columns_info if col["name"] == "created_by_admin_id"),
        None,
    )
    if (
        created_by is not None
        and created_by.get("nullable") is False
        and connection.dialect.name == "postgresql"
    ):
        connection.execute(
            text("ALTER TABLE promo_codes ALTER COLUMN created_by_admin_id DROP NOT NULL")
        )


def _migration_0039_add_promo_activation_effect_snapshots(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("promo_code_activations")}
    statements: list[str] = []

    if "effect_summary" not in columns:
        statements.append("ALTER TABLE promo_code_activations ADD COLUMN effect_summary VARCHAR")
    if "bonus_days" not in columns:
        statements.append("ALTER TABLE promo_code_activations ADD COLUMN bonus_days INTEGER")
    if "discount_percent" not in columns:
        statements.append(
            "ALTER TABLE promo_code_activations ADD COLUMN discount_percent NUMERIC(5, 2)"
        )
    if "duration_multiplier" not in columns:
        statements.append(
            "ALTER TABLE promo_code_activations ADD COLUMN duration_multiplier NUMERIC(6, 3)"
        )
    if "traffic_multiplier" not in columns:
        statements.append(
            "ALTER TABLE promo_code_activations ADD COLUMN traffic_multiplier NUMERIC(6, 3)"
        )
    if "applies_to" not in columns:
        statements.append("ALTER TABLE promo_code_activations ADD COLUMN applies_to VARCHAR(32)")

    for stmt in statements:
        connection.execute(text(stmt))


def _migration_0040_add_code_checkout_snapshots(connection: Connection) -> None:
    inspector = inspect(connection)
    payment_columns: set[str] = {col["name"] for col in inspector.get_columns("payments")}
    activation_columns: set[str] = {
        col["name"] for col in inspector.get_columns("promo_code_activations")
    }
    code_columns: set[str] = {col["name"] for col in inspector.get_columns("promo_codes")}
    statements: list[str] = []

    payment_additions = {
        "promo_effect_summary": "VARCHAR",
        "promo_bonus_days": "INTEGER",
        "promo_discount_percent": "NUMERIC(5, 2)",
        "promo_duration_multiplier": "NUMERIC(6, 3)",
        "promo_traffic_multiplier": "NUMERIC(6, 3)",
        "promo_applies_to": "VARCHAR(32)",
        "promo_min_subscription_months": "INTEGER",
        "promo_min_traffic_gb": "NUMERIC(10, 2)",
        "checkout_base_amount": "DOUBLE PRECISION",
        "checkout_discount_amount": "DOUBLE PRECISION",
        "checkout_charged_months": "INTEGER",
        "checkout_charged_gb": "DOUBLE PRECISION",
        "checkout_quoted_at": "TIMESTAMPTZ",
    }
    for column, column_type in payment_additions.items():
        if column not in payment_columns:
            statements.append(f"ALTER TABLE payments ADD COLUMN {column} {column_type}")

    activation_additions = {
        "base_amount": "DOUBLE PRECISION",
        "discount_amount": "DOUBLE PRECISION",
        "charged_months": "INTEGER",
        "charged_gb": "DOUBLE PRECISION",
        "granted_days": "INTEGER",
        "granted_gb": "DOUBLE PRECISION",
    }
    for column, column_type in activation_additions.items():
        if column not in activation_columns:
            statements.append(
                f"ALTER TABLE promo_code_activations ADD COLUMN {column} {column_type}"
            )

    if "archived_at" not in code_columns:
        statements.append("ALTER TABLE promo_codes ADD COLUMN archived_at TIMESTAMPTZ")

    for stmt in statements:
        connection.execute(text(stmt))


def _migration_0041_add_bonus_payment_mode_flag(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("promo_codes")}
    if "bonus_requires_payment" not in columns:
        connection.execute(
            text(
                "ALTER TABLE promo_codes "
                "ADD COLUMN bonus_requires_payment BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        connection.execute(
            text(
                "UPDATE promo_codes "
                "SET bonus_requires_payment = TRUE "
                "WHERE bonus_days > 0 "
                "AND (min_subscription_months IS NOT NULL OR min_traffic_gb IS NOT NULL)"
            )
        )


MIGRATIONS: list[Migration] = [
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
        upgrade=_migration_0013_add_app_setting_overrides,
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
    Migration(
        id="0018_add_premium_admin_overrides",
        description="Per-subscription admin overrides for premium traffic (unlimited toggle + bonus bytes)",  # noqa: E501
        upgrade=_migration_0018_add_premium_admin_overrides,
    ),
    Migration(
        id="0019_clear_subscription_months_for_non_subscription_payments",
        description="Backfill: null out subscription_duration_months for legacy traffic/topup/hwid payments",  # noqa: E501
        upgrade=_migration_0019_clear_subscription_months_for_non_subscription_payments,
    ),
    Migration(
        id="0020_add_regular_bonus_bytes",
        description="Per-subscription admin bonus bytes on regular (main) traffic limit",
        upgrade=_migration_0020_add_regular_bonus_bytes,
    ),
    Migration(
        id="0021_add_regular_unlimited_override",
        description="Admin toggle for effectively unlimited main traffic limit",
        upgrade=_migration_0021_add_regular_unlimited_override,
    ),
    Migration(
        id="0022_add_indexes_for_admin_reports",
        description="Indexes to speed up financial stats and admin log queries",
        upgrade=_migration_0022_add_indexes_for_admin_reports,
    ),
    Migration(
        id="0023_add_email_password_auth_fields",
        description="Store hashed passwords for optional email password login",
        upgrade=_migration_0023_add_email_password_auth_fields,
    ),
    Migration(
        id="0024_add_support_tickets",
        description="Add support ticket inbox and messages",
        upgrade=_migration_0024_add_support_tickets,
    ),
    Migration(
        id="0025_add_support_notification_timestamps",
        description="Track support ticket admin notification cooldown timestamps",
        upgrade=_migration_0025_add_support_notification_timestamps,
    ),
    Migration(
        id="0026_add_lifetime_traffic_synced_at",
        description="Track when lifetime traffic usage was last synced from panel",
        upgrade=_migration_0026_add_lifetime_traffic_synced_at,
    ),
    Migration(
        id="0027_add_subscription_install_share_token",
        description="Add stable public share tokens for install instructions",
        upgrade=_migration_0027_add_subscription_install_share_token,
    ),
    Migration(
        id="0028_add_locale_overrides",
        description="Persist runtime overrides for localization strings",
        upgrade=_migration_0028_add_locale_overrides,
    ),
    Migration(
        id="0029_add_hwid_device_purchase_validity",
        description="Track validity windows for HWID device top-ups",
        upgrade=_migration_0029_add_hwid_device_purchase_validity,
    ),
    Migration(
        id="0030_add_hwid_pricing_metadata",
        description="Persist quoted HWID top-up pricing windows and conversion audit",
        upgrade=_migration_0030_add_hwid_pricing_metadata,
    ),
    Migration(
        id="0031_add_subscription_notifications",
        description="Track sent subscription notification stages",
        upgrade=_migration_0031_add_subscription_notifications,
    ),
    Migration(
        id="0032_add_telegram_notification_status",
        description="Track whether the bot can message Telegram-linked users",
        upgrade=_migration_0032_add_telegram_notification_status,
    ),
    Migration(
        id="0033_add_trial_eligibility_reset_marker",
        description="Track admin resets of per-user trial eligibility without deleting history",
        upgrade=_migration_0033_add_trial_eligibility_reset_marker,
    ),
    Migration(
        id="0034_add_legacy_import_compatibility",
        description="Store legacy import mappings and referral codes for source-bot migrations",
        upgrade=_migration_0034_add_legacy_import_compatibility,
    ),
    Migration(
        id="0035_add_subscription_promo_expiry_flag",
        description="Suppress multi-day expiry reminders for trial and bonus subscriptions",
        upgrade=_migration_0035_add_subscription_promo_expiry_flag,
    ),
    Migration(
        id="0036_add_provider_payment_url",
        description="Persist provider payment links for reusable pending payments",
        upgrade=_migration_0036_add_provider_payment_url,
    ),
    Migration(
        id="0037_add_referral_welcome_bonus_marker",
        description="Track when a user claimed the referral welcome bonus to prevent repeat grants",
        upgrade=_migration_0037_add_referral_welcome_bonus_marker,
    ),
    Migration(
        id="0038_extend_promo_code_effects",
        description="Extend bonus code effects and attribution fields",
        upgrade=_migration_0038_extend_promo_code_effects,
    ),
    Migration(
        id="0039_add_promo_activation_effect_snapshots",
        description="Snapshot code effects on activation records",
        upgrade=_migration_0039_add_promo_activation_effect_snapshots,
    ),
    Migration(
        id="0040_add_code_checkout_snapshots",
        description="Snapshot code checkout terms and archive used codes safely",
        upgrade=_migration_0040_add_code_checkout_snapshots,
    ),
    Migration(
        id="0041_add_bonus_payment_mode_flag",
        description="Choose whether bonus days are granted immediately or after payment",
        upgrade=_migration_0041_add_bonus_payment_mode_flag,
    ),
]


def validate_migration_chains(chains: dict[str, list[Migration]]) -> None:
    """Reject malformed chains before anything touches the database.

    Non-core namespaces must prefix every migration id with ``"<namespace>."``
    so ids from different sources can never collide inside the shared
    ``schema_migrations`` table.
    """
    for namespace, migrations in chains.items():
        if namespace == CORE_MIGRATION_NAMESPACE:
            continue
        prefix = f"{namespace}."
        for migration in migrations:
            if not migration.id.startswith(prefix):
                raise ValueError(
                    f"Migration id {migration.id!r} in namespace {namespace!r} must "
                    f"start with {prefix!r}"
                )


def run_migration_chains(connection: Connection, chains: dict[str, list[Migration]]) -> None:
    """
    Apply pending migrations of every chain sequentially. Already applied
    revisions are skipped; all chains share the ``schema_migrations`` table.
    """
    validate_migration_chains(chains)
    _ensure_migrations_table(connection)

    applied_revisions: set[str] = {
        row[0] for row in connection.execute(text("SELECT id FROM schema_migrations"))
    }

    for namespace, migrations in chains.items():
        for migration in migrations:
            if migration.id in applied_revisions:
                continue

            logger.info(
                "Migrator: applying %s – %s (namespace %s)",
                migration.id,
                migration.description,
                namespace,
            )
            try:
                with connection.begin_nested():
                    migration.upgrade(connection)
                    connection.execute(
                        text("INSERT INTO schema_migrations (id) VALUES (:revision)"),
                        {"revision": migration.id},
                    )
            except Exception as exc:
                logger.exception(
                    "Migrator: failed to apply %s (%s)", migration.id, migration.description
                )
                raise exc
            else:
                logger.info("Migrator: migration %s applied successfully", migration.id)


def run_database_migrations(connection: Connection) -> None:
    """Apply the core migration chain (kept for restore/import code paths)."""
    run_migration_chains(connection, {CORE_MIGRATION_NAMESPACE: MIGRATIONS})


def run_all_migration_chains(connection: Connection, settings: "Settings") -> None:
    """Apply the core chain plus every plugin-contributed chain."""
    # Imported lazily: the plugin loader lives in the bot layer and must not
    # become an import-time dependency of the db layer.
    from bot.plugins import collect_migrations

    chains: dict[str, list[Migration]] = {CORE_MIGRATION_NAMESPACE: MIGRATIONS}
    chains.update(collect_migrations(settings))
    run_migration_chains(connection, chains)
