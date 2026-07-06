"""Pin the exact ordered migration chain the migrator would apply.

The migration chain is append-only (CONTRIBUTING §3.4): existing ids must never
be edited, reordered or renumbered. This snapshot turns that rule into a CI
failure instead of a review comment. Adding a new migration is the only change
that may touch this list — append its id at the end.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from unittest import TestCase

from sqlalchemy.engine import Connection

from db.migrator import (
    CORE_MIGRATION_NAMESPACE,
    MIGRATIONS,
    Migration,
    run_migration_chains,
)

EXPECTED_CORE_MIGRATION_IDS = [
    "0001_add_channel_subscription_fields",
    "0002_add_referral_code",
    "0003_normalize_referral_codes",
    "0004_add_lifetime_used_traffic",
    "0005_add_email_auth_fields",
    "0006_add_security_throttles",
    "0007_add_telegram_photo_url",
    "0008_add_email_verification_code_status",
    "0009_add_composite_indexes",
    "0010_add_email_magic_token_hash",
    "0011_add_user_telegram_avatars",
    "0012_add_tariffs_schema",
    "0013_add_app_setting_overrides",
    "0014_add_premium_squad_traffic_fields",
    "0015_add_premium_topup_carryover_fields",
    "0016_add_message_logs_admin_fields",
    "0017_reconcile_legacy_admin_api_schema",
    "0018_add_premium_admin_overrides",
    "0019_clear_subscription_months_for_non_subscription_payments",
    "0020_add_regular_bonus_bytes",
    "0021_add_regular_unlimited_override",
    "0022_add_indexes_for_admin_reports",
    "0023_add_email_password_auth_fields",
    "0024_add_support_tickets",
    "0025_add_support_notification_timestamps",
    "0026_add_lifetime_traffic_synced_at",
    "0027_add_subscription_install_share_token",
    "0028_add_locale_overrides",
    "0029_add_hwid_device_purchase_validity",
    "0030_add_hwid_pricing_metadata",
    "0031_add_subscription_notifications",
    "0032_add_telegram_notification_status",
    "0033_add_trial_eligibility_reset_marker",
    "0034_add_legacy_import_compatibility",
    "0035_add_subscription_promo_expiry_flag",
    "0036_add_provider_payment_url",
    "0037_add_referral_welcome_bonus_marker",
    "0038_extend_promo_code_effects",
    "0039_add_promo_activation_effect_snapshots",
    "0040_add_code_checkout_snapshots",
    "0041_add_bonus_payment_mode_flag",
    "0042_release_archived_promo_codes",
]


class _RecordingConnection:
    """Just enough of a Connection for run_migration_chains to run dry."""

    def __init__(self, already_applied: set[str]) -> None:
        self._already_applied = already_applied
        self.recorded_inserts: list[str] = []

    def execute(self, clause: object, params: dict[str, str] | None = None) -> list[tuple[str]]:
        sql = str(clause)
        if "SELECT id FROM schema_migrations" in sql:
            return [(revision,) for revision in sorted(self._already_applied)]
        if "INSERT INTO schema_migrations" in sql and params is not None:
            self.recorded_inserts.append(params["revision"])
        return []

    @contextmanager
    def begin_nested(self) -> Iterator[None]:
        yield


class CoreMigrationChainSnapshotTests(TestCase):
    def test_core_chain_matches_ordered_snapshot(self) -> None:
        actual = [migration.id for migration in MIGRATIONS]
        self.assertEqual(
            EXPECTED_CORE_MIGRATION_IDS,
            actual,
            "The core migration chain diverged from the pinned snapshot. "
            "Migrations are append-only: never edit, reorder or renumber "
            "existing ids — only append a new id at the end of both the "
            "MIGRATIONS list and this snapshot.",
        )

    def test_core_chain_ids_are_unique(self) -> None:
        ids = [migration.id for migration in MIGRATIONS]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate migration ids in the core chain")

    def test_every_core_migration_has_a_description(self) -> None:
        for migration in MIGRATIONS:
            with self.subTest(migration=migration.id):
                self.assertTrue(migration.description.strip())


class MigrationRunnerOrderTests(TestCase):
    """Characterize the runner semantics the 9.2 split must preserve."""

    @staticmethod
    def _chain(namespace: str, ids: list[str]) -> list[Migration]:
        def _noop(_: Connection) -> None:
            return None

        return [Migration(id=item, description=f"test {item}", upgrade=_noop) for item in ids]

    def test_runner_applies_chains_in_declared_order_core_first(self) -> None:
        connection = _RecordingConnection(already_applied=set())
        chains = {
            CORE_MIGRATION_NAMESPACE: self._chain(CORE_MIGRATION_NAMESPACE, ["0001_a", "0002_b"]),
            "demo": self._chain("demo", ["demo.0001_c", "demo.0002_d"]),
        }

        run_migration_chains(cast(Connection, connection), chains)

        self.assertEqual(
            ["0001_a", "0002_b", "demo.0001_c", "demo.0002_d"],
            connection.recorded_inserts,
        )

    def test_runner_skips_already_applied_revisions(self) -> None:
        connection = _RecordingConnection(already_applied={"0001_a", "demo.0001_c"})
        chains = {
            CORE_MIGRATION_NAMESPACE: self._chain(CORE_MIGRATION_NAMESPACE, ["0001_a", "0002_b"]),
            "demo": self._chain("demo", ["demo.0001_c", "demo.0002_d"]),
        }

        run_migration_chains(cast(Connection, connection), chains)

        self.assertEqual(["0002_b", "demo.0002_d"], connection.recorded_inserts)

    def test_runner_rejects_unnamespaced_plugin_ids(self) -> None:
        connection = _RecordingConnection(already_applied=set())
        chains = {"demo": self._chain("demo", ["0001_not_prefixed"])}

        with self.assertRaises(ValueError):
            run_migration_chains(cast(Connection, connection), chains)
