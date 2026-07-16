"""Core migrations 0022-0041.

Append-only (CONTRIBUTING §3.4): never edit, reorder or renumber existing
bodies or ids. New migrations are appended to the newest chain module.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


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


def _migration_0042_release_archived_promo_codes(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("promo_codes")}
    if "archived_code" not in columns:
        connection.execute(text("ALTER TABLE promo_codes ADD COLUMN archived_code VARCHAR"))

    connection.execute(
        text(
            """
            UPDATE promo_codes
            SET archived_code = code
            WHERE archived_at IS NOT NULL
              AND (archived_code IS NULL OR archived_code = '')
            """
        )
    )

    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                """
                UPDATE promo_codes
                SET code = CONCAT('__ARCHIVED_PROMO__', promo_code_id::text, '__', code)
                WHERE archived_at IS NOT NULL
                  AND code NOT LIKE '__ARCHIVED_PROMO__%'
                """
            )
        )
        return

    connection.execute(
        text(
            """
            UPDATE promo_codes
            SET code = '__ARCHIVED_PROMO__' || promo_code_id || '__' || code
            WHERE archived_at IS NOT NULL
              AND code NOT LIKE '__ARCHIVED_PROMO__%'
            """
        )
    )


def _migration_0043_add_user_panel_squad_overrides(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS user_panel_squad_overrides (
                override_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                panel_user_uuid VARCHAR NOT NULL,
                kind VARCHAR(16) NOT NULL,
                override_key VARCHAR NOT NULL,
                squad_uuid VARCHAR NULL,
                mode VARCHAR(16) NOT NULL DEFAULT 'set',
                source VARCHAR(16) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by_admin_id BIGINT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NULL,
                last_seen_at TIMESTAMPTZ NULL,
                deactivated_at TIMESTAMPTZ NULL,
                note TEXT NULL,
                CONSTRAINT uq_user_panel_squad_override_key
                    UNIQUE (user_id, panel_user_uuid, kind, override_key)
            )
            """
        )
    )
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_user_panel_squad_overrides_user_active "
        "ON user_panel_squad_overrides (user_id, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_user_panel_squad_overrides_panel_active "
        "ON user_panel_squad_overrides (panel_user_uuid, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_user_panel_squad_overrides_kind_squad "
        "ON user_panel_squad_overrides (kind, squad_uuid)",
    ]
    for stmt in index_statements:
        connection.execute(text(stmt))


def _migration_0044_add_subscription_last_connected_at(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("subscriptions")}
    if "last_connected_at" not in columns:
        connection.execute(
            text("ALTER TABLE subscriptions ADD COLUMN last_connected_at TIMESTAMPTZ")
        )


def _migration_0045_scope_provider_payment_ids(connection: Connection) -> None:
    inspector = inspect(connection)
    quote = connection.dialect.identifier_preparer.quote
    provider_column = ("provider_payment_id",)
    scoped_columns = {"provider", "provider_payment_id"}
    scoped_unique_exists = False

    for constraint in inspector.get_unique_constraints("payments"):
        columns = tuple(str(column) for column in constraint.get("column_names") or () if column)
        if set(columns) == scoped_columns and len(columns) == 2:
            scoped_unique_exists = True
        if columns != provider_column:
            continue
        name = constraint.get("name")
        if not name:
            raise RuntimeError("Cannot drop unnamed provider payment id constraint.")
        connection.execute(text(f"ALTER TABLE payments DROP CONSTRAINT {quote(str(name))}"))

    for index in inspector.get_indexes("payments"):
        if not index.get("unique") or index.get("duplicates_constraint"):
            continue
        columns = tuple(str(column) for column in index.get("column_names") or () if column)
        if set(columns) == scoped_columns and len(columns) == 2:
            scoped_unique_exists = True
        if columns != provider_column:
            continue
        name = index.get("name")
        if not name:
            raise RuntimeError("Cannot drop unnamed provider payment id index.")
        connection.execute(text(f"DROP INDEX {quote(str(name))}"))

    if not scoped_unique_exists:
        connection.execute(
            text(
                "ALTER TABLE payments "
                "ADD CONSTRAINT uq_payments_provider_payment_id "
                "UNIQUE (provider, provider_payment_id)"
            )
        )


CHAIN_0022_0041: list[Migration] = [
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
    Migration(
        id="0042_release_archived_promo_codes",
        description="Release archived code names while preserving their display value",
        upgrade=_migration_0042_release_archived_promo_codes,
    ),
    Migration(
        id="0043_add_user_panel_squad_overrides",
        description="Persist manual Remnawave squad overrides per panel user",
        upgrade=_migration_0043_add_user_panel_squad_overrides,
    ),
    Migration(
        id="0044_add_subscription_last_connected_at",
        description="Snapshot the latest panel connection time on subscriptions",
        upgrade=_migration_0044_add_subscription_last_connected_at,
    ),
    Migration(
        id="0045_scope_provider_payment_ids",
        description="Scope external payment identifiers to their provider",
        upgrade=_migration_0045_scope_provider_payment_ids,
    ),
]
