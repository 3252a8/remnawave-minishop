from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.dialects import postgresql

from db.migrator import chain_0069_0083
from db.models import Subscription


class _RecordingConnection:
    dialect = postgresql.dialect()

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object) -> None:
        self.statements.append(str(statement))


def test_subscription_model_tracks_explicit_hwid_limit_override() -> None:
    column = Subscription.__table__.columns["hwid_device_limit_is_override"]

    assert not column.nullable


def test_migration_adds_override_source_and_backfills_latest_admin_choice() -> None:
    connection = _RecordingConnection()
    inspector = SimpleNamespace(
        get_table_names=lambda: ["subscriptions", "message_logs"],
        get_columns=lambda table: [{"name": "subscription_id"}] if table == "subscriptions" else [],
    )

    with patch.object(chain_0069_0083, "inspect", return_value=inspector):
        chain_0069_0083._migration_0071_add_hwid_device_limit_override(connection)

    sql = "\n".join(connection.statements)
    assert "ADD COLUMN hwid_device_limit_is_override BOOLEAN NOT NULL DEFAULT FALSE" in sql
    assert "SELECT DISTINCT ON (target_user_id)" in sql
    assert "admin:hwid_device_limit" in sql
    assert "admin_hwid_device_limit_webapp" in sql
    assert "content NOT LIKE 'hwid_device_limit=None%'" in sql


def test_migration_is_idempotent_when_override_source_exists() -> None:
    connection = _RecordingConnection()
    inspector = SimpleNamespace(
        get_table_names=lambda: ["subscriptions", "message_logs"],
        get_columns=lambda table: (
            [{"name": "hwid_device_limit_is_override"}] if table == "subscriptions" else []
        ),
    )

    with patch.object(chain_0069_0083, "inspect", return_value=inspector):
        chain_0069_0083._migration_0071_add_hwid_device_limit_override(connection)

    assert connection.statements == []
