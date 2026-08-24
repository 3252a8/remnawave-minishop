from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.dialects import postgresql

from db.migrator import chain_0046_0060, chain_0069_0083
from db.models import AutoRenewCycle, Payment, Subscription

AUTO_RENEW_ATTEMPT_INDEX = "uq_payments_auto_renew_cycle_attempt"


class _RecordingConnection:
    dialect = postgresql.dialect()

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object) -> None:
        self.statements.append(str(statement))


def test_models_persist_retry_limits_consent_and_failure_attribution() -> None:
    assert not Subscription.__table__.columns["auto_renew_consent_version"].nullable
    assert not AutoRenewCycle.__table__.columns["request_snapshot"].nullable
    assert not AutoRenewCycle.__table__.columns["base_idempotence_key"].nullable
    assert Payment.__table__.columns["provider_request_snapshot"].nullable
    assert Payment.__table__.columns["provider_cancellation_reason"].nullable
    constraints = {constraint.name for constraint in Payment.__table__.constraints}
    assert AUTO_RENEW_ATTEMPT_INDEX not in constraints
    indexes = {index.name: index for index in Payment.__table__.indexes}
    attempt_index = indexes[AUTO_RENEW_ATTEMPT_INDEX]
    assert attempt_index.unique is True
    assert str(attempt_index.dialect_options["postgresql"]["where"]) == (
        "auto_renew_cycle_id IS NOT NULL AND renewal_attempt_number IS NOT NULL"
    )


def test_migration_creates_cycle_state_and_payment_attribution_idempotently() -> None:
    connection = _RecordingConnection()
    columns = {
        "subscriptions": [{"name": "subscription_id"}],
        "payments": [{"name": "payment_id"}],
    }
    inspector = SimpleNamespace(
        get_table_names=lambda: [
            "users",
            "subscriptions",
            "user_payment_methods",
            "payments",
        ],
        get_columns=lambda table: columns.get(table, []),
    )

    with patch.object(chain_0046_0060, "inspect", return_value=inspector):
        chain_0046_0060._migration_0055_add_auto_renew_retry_state(connection)

    sql = "\n".join(connection.statements)
    assert "ADD COLUMN auto_renew_consent_version INTEGER NOT NULL DEFAULT 0" in sql
    assert "CREATE TABLE IF NOT EXISTS auto_renew_cycles" in sql
    assert "financial_attempts INTEGER NOT NULL DEFAULT 0" in sql
    assert "ADD COLUMN provider_request_snapshot TEXT" in sql
    assert "uq_payments_auto_renew_cycle_attempt" in sql

    connection = _RecordingConnection()
    all_subscription_columns = [{"name": column.name} for column in Subscription.__table__.columns]
    all_payment_columns = [{"name": column.name} for column in Payment.__table__.columns]
    idempotent_inspector = SimpleNamespace(
        get_table_names=lambda: [
            "users",
            "subscriptions",
            "user_payment_methods",
            "auto_renew_cycles",
            "payments",
        ],
        get_columns=lambda table: (
            all_subscription_columns
            if table == "subscriptions"
            else all_payment_columns
            if table == "payments"
            else []
        ),
    )
    with patch.object(
        chain_0046_0060,
        "inspect",
        return_value=idempotent_inspector,
    ):
        chain_0046_0060._migration_0055_add_auto_renew_retry_state(connection)

    idempotent_sql = "\n".join(connection.statements)
    assert "ALTER TABLE subscriptions ADD COLUMN" not in idempotent_sql
    assert "ALTER TABLE payments ADD COLUMN" not in idempotent_sql


def test_migration_normalizes_auto_renew_attempt_constraint_to_partial_index() -> None:
    connection = _RecordingConnection()
    inspector = SimpleNamespace(get_table_names=lambda: ["payments"])

    with patch.object(chain_0069_0083, "inspect", return_value=inspector):
        chain_0069_0083._migration_0069_normalize_auto_renew_attempt_index(connection)

    assert connection.statements == [
        "ALTER TABLE payments DROP CONSTRAINT IF EXISTS " + AUTO_RENEW_ATTEMPT_INDEX,
        "CREATE UNIQUE INDEX IF NOT EXISTS " + AUTO_RENEW_ATTEMPT_INDEX + " "
        "ON payments (auto_renew_cycle_id, renewal_attempt_number) "
        "WHERE auto_renew_cycle_id IS NOT NULL AND renewal_attempt_number IS NOT NULL",
    ]


def test_migration_skips_auto_renew_attempt_index_without_payments_table() -> None:
    connection = _RecordingConnection()
    inspector = SimpleNamespace(get_table_names=list)

    with patch.object(chain_0069_0083, "inspect", return_value=inspector):
        chain_0069_0083._migration_0069_normalize_auto_renew_attempt_index(connection)

    assert connection.statements == []
