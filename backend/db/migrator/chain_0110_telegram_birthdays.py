"""Store only month and day for Telegram birthday delivery."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS telegram_birthday_month_day INTEGER, "
            "ADD COLUMN IF NOT EXISTS telegram_birthday_checked_at TIMESTAMPTZ, "
            "ADD COLUMN IF NOT EXISTS telegram_birthday_checked_for BIGINT, "
            "ADD COLUMN IF NOT EXISTS telegram_birthday_sent_year INTEGER"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_users_telegram_birthday_month_day "
            "ON users (telegram_birthday_month_day)"
        )
    )


CHAIN_0110_TELEGRAM_BIRTHDAYS = [
    Migration("0110_telegram_birthdays", "Track Telegram birthday code delivery", _upgrade)
]
