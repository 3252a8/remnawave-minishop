"""Issue new internal user keys independently of login identities."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0092_user_id_sequence(connection: Connection) -> None:
    connection.execute(text("CREATE SEQUENCE IF NOT EXISTS minishop_user_id_seq AS BIGINT"))
    connection.execute(
        text("""
        SELECT setval(
            'minishop_user_id_seq',
            GREATEST(999999999999, COALESCE((SELECT MAX(user_id) FROM users), 0)),
            true
        )
    """)
    )
    connection.execute(
        text("""
        ALTER TABLE users ALTER COLUMN user_id
        SET DEFAULT nextval('minishop_user_id_seq'::regclass)
    """)
    )


CHAIN_0092_USER_ID_SEQUENCE: list[Migration] = [
    Migration(
        id="0092_user_id_sequence",
        description="Assign internal user IDs from a database sequence, independent of Telegram",
        upgrade=_migration_0092_user_id_sequence,
    )
]
