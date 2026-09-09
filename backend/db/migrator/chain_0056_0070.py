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


def _migration_0058_add_partner_program(connection: Connection) -> None:
    """Add the independent partner attribution and append-only money ledger."""

    inspector = inspect(connection)
    payment_columns = {column["name"] for column in inspector.get_columns("payments")}
    if "funding_source" not in payment_columns:
        connection.execute(
            text(
                "ALTER TABLE payments ADD COLUMN funding_source VARCHAR(48) "
                "NOT NULL DEFAULT 'external'"
            )
        )
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_payments_funding_source ON payments (funding_source)")
    )

    statements = (
        """
        CREATE TABLE IF NOT EXISTS partner_profiles (
            partner_id BIGSERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE REFERENCES users(user_id) ON DELETE SET NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'closed')),
            commission_bps INTEGER NOT NULL DEFAULT 3000
                CHECK (commission_bps >= 0 AND commission_bps <= 10000),
            partner_code VARCHAR(64) NOT NULL UNIQUE,
            display_label_snapshot VARCHAR(255) NOT NULL,
            welcome_message TEXT,
            pause_reason TEXT,
            reapply_allowed_at TIMESTAMPTZ,
            activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            paused_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS partner_applications (
            application_id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
            display_label_snapshot VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'canceled')),
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ,
            decided_by_admin_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
            decision_message TEXT,
            approved_commission_bps INTEGER,
            welcome_message TEXT,
            reapply_allowed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS partner_clients (
            partner_client_id BIGSERIAL PRIMARY KEY,
            partner_id BIGINT NOT NULL REFERENCES partner_profiles(partner_id) ON DELETE RESTRICT,
            client_user_id BIGINT UNIQUE REFERENCES users(user_id) ON DELETE SET NULL,
            public_client_id VARCHAR(32) NOT NULL UNIQUE,
            public_label_snapshot VARCHAR(255) NOT NULL,
            source VARCHAR(32) NOT NULL CHECK (
                source IN ('partner_telegram_link', 'partner_web_link',
                           'referral_import', 'admin_manual')
            ),
            attributed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            eligible_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            attributed_by_admin_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS partner_commissions (
            commission_id BIGSERIAL PRIMARY KEY,
            partner_id BIGINT NOT NULL REFERENCES partner_profiles(partner_id) ON DELETE RESTRICT,
            partner_client_id BIGINT NOT NULL
                REFERENCES partner_clients(partner_client_id) ON DELETE RESTRICT,
            payment_id INTEGER UNIQUE REFERENCES payments(payment_id) ON DELETE SET NULL,
            gross_amount_minor BIGINT NOT NULL CHECK (gross_amount_minor >= 0),
            commission_amount_minor BIGINT NOT NULL CHECK (commission_amount_minor >= 0),
            currency VARCHAR(16) NOT NULL,
            currency_scale INTEGER NOT NULL,
            commission_bps_snapshot INTEGER NOT NULL,
            sale_mode_snapshot VARCHAR(64),
            provider_snapshot VARCHAR(64),
            status VARCHAR(16) NOT NULL
                CHECK (status IN ('pending', 'available', 'reversed', 'excluded')),
            exclusion_reason VARCHAR(64),
            source_paid_at TIMESTAMPTZ NOT NULL,
            available_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reversed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS partner_ledger_entries (
            entry_id BIGSERIAL PRIMARY KEY,
            partner_id BIGINT NOT NULL REFERENCES partner_profiles(partner_id) ON DELETE RESTRICT,
            currency VARCHAR(16) NOT NULL,
            currency_scale INTEGER NOT NULL,
            amount_minor BIGINT NOT NULL,
            kind VARCHAR(32) NOT NULL CHECK (kind IN (
                'commission_credit', 'manual_adjustment', 'withdrawal_reserve',
                'withdrawal_release', 'subscription_spend', 'subscription_spend_release',
                'commission_reversal'
            )),
            state VARCHAR(16) NOT NULL DEFAULT 'posted'
                CHECK (state IN ('pending', 'posted', 'void')),
            reference_type VARCHAR(32) NOT NULL,
            reference_id VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL UNIQUE,
            actor_admin_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
            reason TEXT,
            metadata_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            posted_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS partner_withdrawals (
            withdrawal_id BIGSERIAL PRIMARY KEY,
            partner_id BIGINT NOT NULL REFERENCES partner_profiles(partner_id) ON DELETE RESTRICT,
            method_id_snapshot VARCHAR(64) NOT NULL,
            method_type_snapshot VARCHAR(32) NOT NULL,
            method_snapshot_json TEXT NOT NULL,
            debit_amount_minor BIGINT NOT NULL CHECK (debit_amount_minor > 0),
            debit_currency VARCHAR(16) NOT NULL,
            currency_scale INTEGER NOT NULL,
            settlement_asset VARCHAR(16),
            network VARCHAR(64),
            status VARCHAR(16) NOT NULL DEFAULT 'requested' CHECK (
                status IN ('requested', 'processing', 'paid', 'rejected', 'canceled', 'failed')
            ),
            status_version INTEGER NOT NULL DEFAULT 1,
            status_message TEXT,
            external_reference VARCHAR(255),
            settlement_amount VARCHAR(64),
            requisites_ciphertext BYTEA,
            requisites_key_id VARCHAR(32) NOT NULL,
            masked_requisites VARCHAR(255) NOT NULL,
            client_idempotency_key VARCHAR(128) NOT NULL UNIQUE,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processing_at TIMESTAMPTZ,
            paid_at TIMESTAMPTZ,
            decided_at TIMESTAMPTZ,
            handled_by_admin_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS partner_audit_events (
            audit_event_id BIGSERIAL PRIMARY KEY,
            partner_id BIGINT REFERENCES partner_profiles(partner_id) ON DELETE RESTRICT,
            application_id BIGINT
                REFERENCES partner_applications(application_id) ON DELETE SET NULL,
            withdrawal_id BIGINT REFERENCES partner_withdrawals(withdrawal_id) ON DELETE SET NULL,
            event_type VARCHAR(64) NOT NULL,
            actor_type VARCHAR(16) NOT NULL,
            actor_user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
            old_values_json TEXT,
            new_values_json TEXT,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    )
    for statement in statements:
        connection.execute(text(statement))

    indexes = (
        "CREATE INDEX IF NOT EXISTS ix_partner_profiles_user_id ON partner_profiles (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_partner_profiles_status ON partner_profiles (status)",
        "CREATE INDEX IF NOT EXISTS ix_partner_profiles_status_created "
        "ON partner_profiles (status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_applications_status_submitted "
        "ON partner_applications (status, submitted_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_applications_user_submitted "
        "ON partner_applications (user_id, submitted_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_partner_applications_pending_user "
        "ON partner_applications (user_id) WHERE status = 'pending' AND user_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_partner_clients_partner_attributed "
        "ON partner_clients (partner_id, attributed_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_commissions_partner_created "
        "ON partner_commissions (partner_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_commissions_status_available "
        "ON partner_commissions (status, available_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_ledger_partner_currency "
        "ON partner_ledger_entries (partner_id, currency, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_ledger_reference "
        "ON partner_ledger_entries (reference_type, reference_id)",
        "CREATE INDEX IF NOT EXISTS ix_partner_withdrawals_status_requested "
        "ON partner_withdrawals (status, requested_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_withdrawals_partner_requested "
        "ON partner_withdrawals (partner_id, requested_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_audit_partner_created "
        "ON partner_audit_events (partner_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_partner_audit_event_created "
        "ON partner_audit_events (event_type, created_at)",
    )
    for statement in indexes:
        connection.execute(text(statement))


def _migration_0059_add_partner_client_welcome_eligibility(connection: Connection) -> None:
    """Snapshot welcome-bonus eligibility at first-touch partner registration."""

    inspector = inspect(connection)
    if "partner_clients" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("partner_clients")}
    if "welcome_bonus_eligible_at" not in columns:
        connection.execute(
            text("ALTER TABLE partner_clients ADD COLUMN welcome_bonus_eligible_at TIMESTAMPTZ")
        )


def _migration_0060_add_promo_traffic_grants(connection: Connection) -> None:
    """Persist fixed regular and premium traffic grants and immutable snapshots."""

    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    additions_by_table = {
        "promo_codes": {
            "regular_traffic_gb": "NUMERIC(12, 3)",
            "premium_traffic_gb": "NUMERIC(12, 3)",
        },
        "payments": {
            "promo_regular_traffic_gb": "NUMERIC(12, 3)",
            "promo_premium_traffic_gb": "NUMERIC(12, 3)",
        },
        "promo_code_activations": {
            "regular_traffic_gb": "NUMERIC(12, 3)",
            "premium_traffic_gb": "NUMERIC(12, 3)",
            "granted_regular_traffic_gb": "NUMERIC(12, 3)",
            "granted_premium_traffic_gb": "NUMERIC(12, 3)",
        },
    }
    for table_name, additions in additions_by_table.items():
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column, definition in additions.items():
            if column not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column} {definition}")
                )


def _migration_0061_add_partner_checkout_balance(connection: Connection) -> None:
    """Persist mixed checkout funding and general partner-balance ledger kinds."""

    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "payments" in table_names:
        columns = {column["name"] for column in inspector.get_columns("payments")}
        additions = {
            "checkout_total_amount": "DOUBLE PRECISION",
            "partner_balance_amount_minor": "BIGINT",
            "partner_balance_currency_scale": "INTEGER",
        }
        for column, definition in additions.items():
            if column not in columns:
                connection.execute(text(f"ALTER TABLE payments ADD COLUMN {column} {definition}"))

    if "partner_ledger_entries" not in table_names:
        return
    constraints = {
        str(item.get("name") or ""): str(item.get("sqltext") or "")
        for item in inspector.get_check_constraints("partner_ledger_entries")
    }
    kind_constraint = constraints.get("ck_partner_ledger_kind", "")
    if "checkout_spend" in kind_constraint:
        return
    connection.execute(
        text("ALTER TABLE partner_ledger_entries DROP CONSTRAINT IF EXISTS ck_partner_ledger_kind")
    )
    connection.execute(
        text(
            "ALTER TABLE partner_ledger_entries ADD CONSTRAINT ck_partner_ledger_kind "
            "CHECK (kind IN ('commission_credit', 'manual_adjustment', "
            "'withdrawal_reserve', 'withdrawal_release', 'subscription_spend', "
            "'subscription_spend_release', 'checkout_spend', "
            "'checkout_spend_release', 'commission_reversal'))"
        )
    )


def _migration_0062_add_admin_broadcast_history(connection: Connection) -> None:
    """Persist scheduled broadcasts and their per-channel delivery progress."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS admin_broadcasts (
                broadcast_id SERIAL PRIMARY KEY,
                created_by_admin_id BIGINT,
                status VARCHAR(24) NOT NULL DEFAULT 'queued',
                is_visible BOOLEAN NOT NULL DEFAULT TRUE,
                target VARCHAR(128) NOT NULL DEFAULT 'all',
                channels JSONB NOT NULL DEFAULT '[]'::jsonb,
                texts JSONB NOT NULL DEFAULT '{}'::jsonb,
                email_subjects JSONB NOT NULL DEFAULT '{}'::jsonb,
                buttons JSONB NOT NULL DEFAULT '[]'::jsonb,
                scheduled_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                deleted_at TIMESTAMPTZ,
                recipient_count INTEGER NOT NULL DEFAULT 0,
                total_deliveries INTEGER NOT NULL DEFAULT 0,
                successful_deliveries INTEGER NOT NULL DEFAULT 0,
                failed_deliveries INTEGER NOT NULL DEFAULT 0,
                telegram_sent INTEGER NOT NULL DEFAULT 0,
                telegram_failed INTEGER NOT NULL DEFAULT 0,
                email_sent INTEGER NOT NULL DEFAULT 0,
                email_failed INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS admin_broadcast_deliveries (
                delivery_id SERIAL PRIMARY KEY,
                broadcast_id INTEGER NOT NULL REFERENCES admin_broadcasts(broadcast_id)
                    ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                channel VARCHAR(16) NOT NULL,
                destination TEXT NOT NULL,
                language_code VARCHAR(16),
                status VARCHAR(16) NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                queued_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                CONSTRAINT uq_admin_broadcast_delivery_user_channel
                    UNIQUE (broadcast_id, user_id, channel)
            )
            """
        )
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_created_by_admin_id "
        "ON admin_broadcasts (created_by_admin_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_status ON admin_broadcasts (status)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_is_visible "
        "ON admin_broadcasts (is_visible)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_scheduled_at "
        "ON admin_broadcasts (scheduled_at)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_deleted_at "
        "ON admin_broadcasts (deleted_at)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_status_scheduled "
        "ON admin_broadcasts (status, scheduled_at)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_visible_created "
        "ON admin_broadcasts (deleted_at, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_deliveries_broadcast_id "
        "ON admin_broadcast_deliveries (broadcast_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_deliveries_user_id "
        "ON admin_broadcast_deliveries (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_deliveries_status "
        "ON admin_broadcast_deliveries (status)",
        "CREATE INDEX IF NOT EXISTS ix_admin_broadcast_deliveries_broadcast_status "
        "ON admin_broadcast_deliveries (broadcast_id, status)",
    ):
        connection.execute(text(statement))


def _migration_0063_reconcile_tgshop_promo_codes(connection: Connection) -> None:
    """Normalize legacy tg-shop promo rewards to the current effect columns."""

    inspector = inspect(connection)
    if "promo_codes" not in set(inspector.get_table_names()):
        return

    columns_info = inspector.get_columns("promo_codes")
    columns = {column["name"] for column in columns_info}
    bonus_days = next(
        (column for column in columns_info if column["name"] == "bonus_days"),
        None,
    )
    if bonus_days is not None:
        connection.execute(text("UPDATE promo_codes SET bonus_days = 0 WHERE bonus_days IS NULL"))

    if {"discount_percent", "discount_percentage"}.issubset(columns):
        connection.execute(
            text(
                """
                UPDATE promo_codes
                SET discount_percent = discount_percentage
                WHERE discount_percent IS NULL
                  AND discount_percentage BETWEEN 1 AND 100
                """
            )
        )

    if (
        bonus_days is not None
        and bonus_days.get("nullable") is not False
        and connection.dialect.name == "postgresql"
    ):
        connection.execute(text("ALTER TABLE promo_codes ALTER COLUMN bonus_days SET NOT NULL"))


def _migration_0064_add_checkout_bundle_snapshot(connection: Connection) -> None:
    """Persist immutable subscription checkout add-ons and their reuse identity."""

    inspector = inspect(connection)
    if "payments" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("payments")}
    additions = {
        "checkout_bundle_snapshot": "TEXT",
        "checkout_bundle_hash": "VARCHAR(64)",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(text(f"ALTER TABLE payments ADD COLUMN {column} {definition}"))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_payments_checkout_bundle_hash "
            "ON payments (checkout_bundle_hash)"
        )
    )


def _migration_0065_add_flexible_traffic_limits(connection: Connection) -> None:
    """Store resettable checkout quota overrides separately from top-ups."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS flexible_traffic_limits (
                limit_id SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
                payment_id INTEGER REFERENCES payments(payment_id),
                kind VARCHAR(32) NOT NULL,
                tariff_key VARCHAR NOT NULL,
                limit_bytes BIGINT NOT NULL,
                valid_from TIMESTAMPTZ NOT NULL,
                valid_until TIMESTAMPTZ NOT NULL,
                monthly_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                monthly_stars_amount INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_flexible_traffic_limit_payment_window
                    UNIQUE (payment_id, kind, valid_from, valid_until)
            )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_flexible_traffic_limits_subscription_window "
            "ON flexible_traffic_limits (subscription_id, kind, valid_from, valid_until)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_flexible_traffic_limits_payment_id "
            "ON flexible_traffic_limits (payment_id)"
        )
    )


def _migration_0066_add_payment_fulfillment_audit(connection: Connection) -> None:
    """Persist reversible payment fulfillment and explicit promo overrides."""

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "payments" in tables:
        payment_columns = {column["name"] for column in inspector.get_columns("payments")}
        additions = {
            "fulfillment_source": "VARCHAR(16)",
            "fulfilled_at": "TIMESTAMPTZ",
            "fulfilled_by_admin_id": "BIGINT",
            "fulfillment_note": "VARCHAR(500)",
            "fulfillment_before_snapshot": "TEXT",
            "fulfillment_after_snapshot": "TEXT",
            "promo_conflict_override": "BOOLEAN NOT NULL DEFAULT FALSE",
            "reversed_at": "TIMESTAMPTZ",
            "reversed_by_admin_id": "BIGINT",
            "reversal_note": "VARCHAR(500)",
            "promo_usage_restored": "BOOLEAN NOT NULL DEFAULT FALSE",
        }
        for column, definition in additions.items():
            if column not in payment_columns:
                connection.execute(text(f"ALTER TABLE payments ADD COLUMN {column} {definition}"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_payments_fulfillment_source "
                "ON payments (fulfillment_source)"
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_payments_fulfilled_at ON payments (fulfilled_at)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_payments_reversed_at ON payments (reversed_at)")
        )

    if "promo_code_activations" not in tables:
        return
    activation_columns = {
        column["name"] for column in inspector.get_columns("promo_code_activations")
    }
    if "is_manual_override" not in activation_columns:
        connection.execute(
            text(
                "ALTER TABLE promo_code_activations "
                "ADD COLUMN is_manual_override BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
    unique_constraints = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("promo_code_activations")
    }
    if "uq_promo_user_activation" in unique_constraints:
        connection.execute(
            text("ALTER TABLE promo_code_activations DROP CONSTRAINT uq_promo_user_activation")
        )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_promo_user_activation_standard "
            "ON promo_code_activations (promo_code_id, user_id) "
            "WHERE is_manual_override = FALSE"
        )
    )


def _migration_0067_add_message_images(connection: Connection) -> None:
    """Persist normalized images once and reference them from authored messages."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS message_images (
                image_id VARCHAR(32) PRIMARY KEY,
                digest VARCHAR(64) NOT NULL,
                filename VARCHAR(96) NOT NULL,
                content_type VARCHAR(32) NOT NULL DEFAULT 'image/webp',
                size_bytes BIGINT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_message_images_digest ON message_images (digest)")
    )

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    for table_name in ("support_ticket_messages", "admin_broadcasts"):
        if table_name not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "image_id" not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} ADD COLUMN image_id VARCHAR(32) "
                    "REFERENCES message_images(image_id) ON DELETE SET NULL"
                )
            )
        connection.execute(
            text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_image_id ON {table_name} (image_id)")
        )


def _migration_0068_add_broadcast_blocked_filter(connection: Connection) -> None:
    """Persist whether a broadcast excludes known blocked Telegram chats."""

    inspector = inspect(connection)
    if "admin_broadcasts" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("admin_broadcasts")}
    if "exclude_blocked_telegram" not in columns:
        connection.execute(
            text(
                "ALTER TABLE admin_broadcasts ADD COLUMN "
                "exclude_blocked_telegram BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )


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
    Migration(
        id="0058_add_partner_program",
        description="Add partner profiles, attribution, commission decisions and money ledger",
        upgrade=_migration_0058_add_partner_program,
    ),
    Migration(
        id="0059_add_partner_client_welcome_eligibility",
        description="Snapshot partner-link registration eligibility for one-time welcome grants",
        upgrade=_migration_0059_add_partner_client_welcome_eligibility,
    ),
    Migration(
        id="0060_add_promo_traffic_grants",
        description="Persist fixed regular and premium traffic promo grants and snapshots",
        upgrade=_migration_0060_add_promo_traffic_grants,
    ),
    Migration(
        id="0061_add_partner_checkout_balance",
        description="Persist mixed partner-balance checkout funding and ledger entries",
        upgrade=_migration_0061_add_partner_checkout_balance,
    ),
    Migration(
        id="0062_add_admin_broadcast_history",
        description="Persist scheduled broadcasts and per-channel delivery progress",
        upgrade=_migration_0062_add_admin_broadcast_history,
    ),
    Migration(
        id="0063_reconcile_tgshop_promo_codes",
        description="Normalize legacy tg-shop promo rewards for current effect handling",
        upgrade=_migration_0063_reconcile_tgshop_promo_codes,
    ),
    Migration(
        id="0064_add_checkout_bundle_snapshot",
        description="Persist immutable subscription checkout add-on bundles",
        upgrade=_migration_0064_add_checkout_bundle_snapshot,
    ),
    Migration(
        id="0065_add_flexible_traffic_limits",
        description="Store resettable subscription traffic limit windows",
        upgrade=_migration_0065_add_flexible_traffic_limits,
    ),
    Migration(
        id="0066_add_payment_fulfillment_audit",
        description="Persist reversible payment fulfillment and promo override audit",
        upgrade=_migration_0066_add_payment_fulfillment_audit,
    ),
    Migration(
        id="0067_add_message_images",
        description="Persist normalized images for support and outbound messages",
        upgrade=_migration_0067_add_message_images,
    ),
    Migration(
        id="0068_add_broadcast_blocked_filter",
        description="Store the blocked Telegram recipient filter for broadcasts",
        upgrade=_migration_0068_add_broadcast_blocked_filter,
    ),
]
