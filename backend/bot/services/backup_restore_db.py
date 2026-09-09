from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Connection

from config.settings import Settings
from db.migrator import MIGRATIONS, run_all_migration_chains, run_database_migrations
from db.models import Base


def applied_migration_ids(connection: Connection) -> set[str]:
    inspector = inspect(connection)
    if "schema_migrations" not in inspector.get_table_names():
        return set()
    return {str(row[0]) for row in connection.execute(text("SELECT id FROM schema_migrations"))}


def create_missing_tables_and_migrate(
    connection: Connection, settings: Settings | None = None
) -> list[str]:
    before = applied_migration_ids(connection)
    known = {migration.id for migration in MIGRATIONS}
    if settings is not None:
        from bot.plugins import collect_migrations

        known.update(m.id for chain in collect_migrations(settings).values() for m in chain)
    unknown = before - known
    if unknown:
        raise ValueError(f"Backup contains unsupported migrations: {sorted(unknown)}")
    Base.metadata.create_all(connection)
    if settings is None:
        run_database_migrations(connection)
    else:
        run_all_migration_chains(connection, settings)
    after = applied_migration_ids(connection)
    if not known <= after:
        raise ValueError("Database migration chain is incomplete")
    newly_applied = after - before
    return sorted(newly_applied)


def assert_empty_database(connection: Connection) -> None:
    objects = connection.scalar(
        text("""
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND n.nspname NOT LIKE 'pg_toast%'
          AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
    """)
    )
    if objects:
        raise ValueError("Database restore requires a new, empty database")


def validate_restored_database(connection: Connection) -> None:
    # Resolve every mapped table and column without loading application data.
    for table in Base.metadata.sorted_tables:
        connection.execute(select(table).limit(0))
    invalid = connection.scalar(
        text("""
        SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND (NOT i.indisvalid OR NOT i.indisready)
    """)
    )
    if invalid:
        raise ValueError("Restored database contains invalid indexes")
    constraints = connection.execute(
        text("""
        SELECT n.nspname, c.relname, con.conname FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND NOT con.convalidated AND con.contype IN ('f', 'c')
    """)
    )
    quote = connection.dialect.identifier_preparer.quote
    for schema, table_name, constraint in constraints:
        connection.exec_driver_sql(
            f"ALTER TABLE {quote(schema)}.{quote(table_name)} "
            f"VALIDATE CONSTRAINT {quote(constraint)}"
        )


def normalize_serial_sequences(connection: Connection) -> list[str]:
    rows = connection.execute(
        text(
            """
            SELECT
                table_schema,
                table_name,
                column_name,
                pg_get_serial_sequence(
                    format('%I.%I', table_schema, table_name),
                    column_name
                ) AS sequence_name
            FROM information_schema.columns
            WHERE table_schema = ANY(current_schemas(FALSE))
              AND column_default LIKE 'nextval(%'
            ORDER BY table_schema, table_name, ordinal_position
            """
        )
    ).mappings()
    preparer = connection.dialect.identifier_preparer
    normalized: list[str] = []
    for row in rows:
        sequence_name = str(row["sequence_name"] or "").strip()
        if not sequence_name:
            continue
        schema_name = str(row["table_schema"])
        table_name = str(row["table_name"])
        column_name = str(row["column_name"])
        qualified_table = f"{preparer.quote_schema(schema_name)}.{preparer.quote(table_name)}"
        quoted_column = preparer.quote(column_name)
        max_value = connection.scalar(text(f"SELECT MAX({quoted_column}) FROM {qualified_table}"))
        connection.execute(
            text("SELECT setval(to_regclass(:sequence_name), :target_value, :is_called)"),
            {
                "sequence_name": sequence_name,
                "target_value": int(max_value) if max_value is not None else 1,
                "is_called": max_value is not None,
            },
        )
        normalized.append(f"{schema_name}.{table_name}.{column_name}")
    return normalized
