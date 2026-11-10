"""Persist subscription eligibility on codes and checkout snapshots."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE promo_codes "
            "ADD COLUMN IF NOT EXISTS subscription_tariff_key VARCHAR, "
            "ADD COLUMN IF NOT EXISTS exact_subscription_days INTEGER"
        )
    )
    connection.execute(
        text(
            "ALTER TABLE payments "
            "ADD COLUMN IF NOT EXISTS promo_subscription_tariff_key VARCHAR, "
            "ADD COLUMN IF NOT EXISTS promo_exact_subscription_days INTEGER"
        )
    )


CHAIN_0113_PROMO_SUBSCRIPTION_RESTRICTIONS = [
    Migration("0113_promo_subscription_restrictions", "Restrict codes by subscription", _upgrade)
]
