import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import Settings
from db.advisory_locks import SUBSCRIPTION_BACKGROUND_SYNC_LOCK_ID
from db.restore_guard import (
    DB_RESTORE_ADVISORY_LOCK_ID,
    _acquire_restore_shared_lock,
    database_restore_fence,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
    )


def test_restore_aware_session_takes_shared_postgres_lock():
    connection = MagicMock()
    connection.dialect.name = "postgresql"

    _acquire_restore_shared_lock(MagicMock(), object(), connection)

    connection.exec_driver_sql.assert_called_once_with(
        f"SELECT pg_advisory_xact_lock_shared({DB_RESTORE_ADVISORY_LOCK_ID})"
    )


def test_restore_lock_does_not_collide_with_background_sync_lock():
    assert DB_RESTORE_ADVISORY_LOCK_ID != SUBSCRIPTION_BACKGROUND_SYNC_LOCK_ID


def test_restore_aware_session_skips_non_postgres_engines():
    connection = MagicMock()
    connection.dialect.name = "sqlite"

    _acquire_restore_shared_lock(MagicMock(), object(), connection)

    connection.exec_driver_sql.assert_not_called()


def test_database_restore_fence_holds_exclusive_lock_around_restore():
    connection = SimpleNamespace(execute=AsyncMock())

    class ConnectionContext:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    engine = SimpleNamespace(
        connect=lambda: ConnectionContext(),
        dispose=AsyncMock(),
    )
    checkpoints: list[str] = []

    async def run() -> None:
        with patch("db.restore_guard.create_async_engine", return_value=engine):
            async with database_restore_fence(_settings()):
                checkpoints.append("inside")

    asyncio.run(run())

    statements = [str(call.args[0]) for call in connection.execute.await_args_list]
    assert statements == [
        "SELECT pg_advisory_lock(:lock_id)",
        "SELECT pg_advisory_unlock(:lock_id)",
    ]
    assert checkpoints == ["inside"]
    engine.dispose.assert_awaited_once()
