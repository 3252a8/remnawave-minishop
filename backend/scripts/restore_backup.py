"""Offline restore entry point; invoked by scripts/restore-backup.sh."""

import argparse
import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from bot.services.backup_restore_service import BackupRestoreService
from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)
RESTORE_LOCK = 817512404897421340


async def assert_disconnected(connection: AsyncConnection, database: str) -> None:
    count = await connection.scalar(
        text("SELECT count(*) FROM pg_stat_activity WHERE datname = :database"),
        {"database": database},
    )
    if count:
        raise RuntimeError("Stop backend, worker, migrate and all other database clients first")


async def restore(settings: Settings, archive_name: str) -> dict[str, object]:
    service = BackupRestoreService(settings)
    archive = service.archive_path_for_name(archive_name)
    service._validate_archive_for_restore(archive)
    if not service.inspect_archive(archive).has_database:
        raise ValueError("Archive does not contain a database dump")
    original = settings.POSTGRES_DB
    if original in {"postgres", "template0", "template1"}:
        raise ValueError("System databases cannot be restore targets")
    suffix = uuid.uuid4().hex[:16]
    candidate = f"minishop_restore_{suffix}"
    previous = f"minishop_previous_{suffix}"
    admin_settings = settings.model_copy(update={"POSTGRES_DB": "postgres"})
    engine = create_async_engine(admin_settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    backup_dir = service.backup_dir()
    journal_path = backup_dir / f"restore-{suffix}.json"
    tariffs = await asyncio.to_thread(
        lambda: Path(settings.TARIFFS_CONFIG_PATH).expanduser().resolve()
    )
    old_tariffs = backup_dir / f"restore-{suffix}-tariffs.json"
    had_tariffs = tariffs.is_file()
    replaced_tariffs = False
    switched = False
    fenced = False
    journal: dict[str, object] = {
        "archive": archive_name,
        "database": original,
        "candidate_database": candidate,
        "previous_database": previous,
        "tariffs_path": str(tariffs),
        "previous_tariffs": str(old_tariffs) if had_tariffs else None,
        "state": "preparing",
    }

    def save_state(state: str) -> None:
        journal["state"] = state
        temporary = journal_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(journal, indent=2), encoding="utf-8")
        temporary.replace(journal_path)

    try:
        async with engine.connect() as connection:
            quote = connection.dialect.identifier_preparer.quote
            locked = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": RESTORE_LOCK}
            )
            if not locked:
                raise RuntimeError("Another offline restore is running")
            source_oid = await connection.scalar(
                text("SELECT oid FROM pg_database WHERE datname = :name"), {"name": original}
            )
            try:
                if source_oid is None:
                    raise ValueError("Configured database does not exist")
                journal["source_database_oid"] = source_oid
                await assert_disconnected(connection, original)
                if had_tariffs:
                    shutil.copy2(tariffs, old_tariffs)
                save_state("preparing")
                await connection.exec_driver_sql(
                    f"ALTER DATABASE {quote(original)} ALLOW_CONNECTIONS false"
                )
                fenced = True
                await assert_disconnected(connection, original)
                await connection.exec_driver_sql(
                    f"CREATE DATABASE {quote(candidate)} TEMPLATE template0"
                )
                save_state("restoring")
                with tempfile.TemporaryDirectory(prefix="restore-config-", dir=backup_dir) as tmp:
                    staged_tariffs = Path(tmp) / "tariffs.json"
                    if had_tariffs:
                        shutil.copy2(tariffs, staged_tariffs)
                    target = settings.model_copy(
                        update={
                            "POSTGRES_DB": candidate,
                            "TARIFFS_CONFIG_PATH": str(staged_tariffs),
                        }
                    )
                    result = await BackupRestoreService(target).restore_archive(
                        archive_name, restore_database=True, restore_compose=False
                    )
                    journal["migrations_applied"] = result.database_migrations_applied
                    save_state("validated")
                    # Prepare the file on its destination filesystem for an atomic replace.
                    if staged_tariffs.is_file():
                        tariffs.parent.mkdir(parents=True, exist_ok=True)
                        staged_destination = tariffs.with_name(f".{tariffs.name}.{suffix}")
                        shutil.copy2(staged_tariffs, staged_destination)
                        staged_destination.replace(tariffs)
                        replaced_tariffs = True
                    await connection.exec_driver_sql(
                        f"ALTER DATABASE {quote(candidate)} ALLOW_CONNECTIONS false"
                    )
                    await assert_disconnected(connection, candidate)
                    await connection.commit()
                    await connection.execution_options(isolation_level="READ COMMITTED")
                    save_state("switching")
                    # Both renames commit together; there is no half-switched database name.
                    async with connection.begin():
                        await connection.exec_driver_sql(
                            f"ALTER DATABASE {quote(original)} RENAME TO {quote(previous)}"
                        )
                        await connection.exec_driver_sql(
                            f"ALTER DATABASE {quote(candidate)} RENAME TO {quote(original)}"
                        )
                        await connection.exec_driver_sql(
                            f"ALTER DATABASE {quote(original)} ALLOW_CONNECTIONS true"
                        )
                    switched = True
                    save_state("completed")
            except BaseException:
                if not switched:
                    await connection.rollback()
                    await connection.execution_options(isolation_level="AUTOCOMMIT")
                    current_oid = await connection.scalar(
                        text("SELECT oid FROM pg_database WHERE datname = :name"),
                        {"name": original},
                    )
                    if current_oid != source_oid:
                        # COMMIT may have succeeded even when its acknowledgement was lost.
                        # Never put the old tariff file over the newly promoted database.
                        save_state("recovery_required")
                        raise
                    if replaced_tariffs:
                        if had_tariffs:
                            shutil.copy2(old_tariffs, tariffs)
                        else:
                            tariffs.unlink(missing_ok=True)
                    if fenced:
                        await connection.exec_driver_sql(
                            f"ALTER DATABASE {quote(original)} ALLOW_CONNECTIONS true"
                        )
                    save_state("failed")
                raise
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": RESTORE_LOCK}
                )
    finally:
        await engine.dispose()
    return {**journal, "journal": str(journal_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help="Archive filename in BACKUP_DIR")
    parser.add_argument("--check", action="store_true", help="Validate archive without changes")
    args = parser.parse_args()
    settings = get_settings()
    if args.check:
        service = BackupRestoreService(settings)
        path = service.archive_path_for_name(args.archive)
        service._validate_archive_for_restore(path)
        if not service.inspect_archive(path).has_database:
            raise ValueError("Archive does not contain a database dump")
        print("Archive integrity verified")
    else:
        print(json.dumps(asyncio.run(restore(settings, args.archive)), indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
