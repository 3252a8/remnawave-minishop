from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from db.migrator import chain_0022_0041
from db.models import Payment


class _RecordingConnection:
    dialect = postgresql.dialect()

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object) -> None:
        self.statements.append(str(statement))


def test_payment_model_scopes_external_id_uniqueness_to_provider() -> None:
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in Payment.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("provider", "provider_payment_id") in unique_columns
    assert ("provider_payment_id",) not in unique_columns


def test_migration_replaces_global_constraint_with_scoped_constraint() -> None:
    connection = _RecordingConnection()
    inspector = SimpleNamespace(
        get_unique_constraints=lambda _table: [
            {
                "name": "payments_provider_payment_id_key",
                "column_names": ["provider_payment_id"],
            }
        ],
        get_indexes=lambda _table: [],
    )

    with patch.object(chain_0022_0041, "inspect", return_value=inspector):
        chain_0022_0041._migration_0045_scope_provider_payment_ids(connection)

    assert connection.statements == [
        "ALTER TABLE payments DROP CONSTRAINT payments_provider_payment_id_key",
        "ALTER TABLE payments ADD CONSTRAINT uq_payments_provider_payment_id "
        "UNIQUE (provider, provider_payment_id)",
    ]


def test_migration_keeps_existing_scoped_constraint() -> None:
    connection = _RecordingConnection()
    inspector = SimpleNamespace(
        get_unique_constraints=lambda _table: [
            {
                "name": "uq_payments_provider_payment_id",
                "column_names": ["provider", "provider_payment_id"],
            }
        ],
        get_indexes=lambda _table: [],
    )

    with patch.object(chain_0022_0041, "inspect", return_value=inspector):
        chain_0022_0041._migration_0045_scope_provider_payment_ids(connection)

    assert connection.statements == []
