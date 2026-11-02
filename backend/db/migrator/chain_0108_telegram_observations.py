"""Tie breakers for ordered Telegram delivery and membership observations."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    for column in (
        "telegram_notifications_observation_order",
        "channel_subscription_observation_order",
    ):
        connection.execute(
            text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} BIGINT NOT NULL DEFAULT 0")
        )


CHAIN_0108_TELEGRAM_OBSERVATIONS = [
    Migration(
        id="0108_telegram_observations",
        description="Order Telegram delivery and channel membership observations",
        upgrade=_upgrade,
    )
]
