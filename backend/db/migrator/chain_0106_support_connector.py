"""Versioned support state and conditional, attributed external replies."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from db.activity_models import SupportChangeClock

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    SupportChangeClock.__table__.create(connection, checkfirst=True)
    connection.execute(
        text(
            "INSERT INTO support_change_clock (id, cursor) VALUES (1, 0) "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    additions = (
        ("support_tickets", "revision", "BIGINT NOT NULL DEFAULT 1"),
        ("support_tickets", "change_cursor", "BIGINT NOT NULL DEFAULT 0"),
        ("support_ticket_messages", "connector_source", "VARCHAR(64)"),
        ("support_ticket_messages", "author_label", "VARCHAR(160)"),
        ("support_ticket_messages", "idempotency_key", "VARCHAR(160)"),
    )
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    for table, column, definition in additions:
        if table in tables and column not in {
            item["name"] for item in inspector.get_columns(table)
        }:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
    if "support_tickets" in tables:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_support_tickets_change_cursor "
                "ON support_tickets (change_cursor)"
            )
        )
    if "support_ticket_messages" in tables:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_support_connector_reply "
                "ON support_ticket_messages (ticket_id, connector_source, idempotency_key)"
            )
        )


CHAIN_0106_SUPPORT_CONNECTOR = [
    Migration(
        id="0106_support_connector",
        description="Version support conversations and persist conditional external reply identity",
        upgrade=_upgrade,
    )
]
