"""Add durable transferable subscription gifts."""

from sqlalchemy.engine import Connection

from db.gift_models import SubscriptionGift

from .engine import Migration


def _migration_0077_subscription_gifts(connection: Connection) -> None:
    SubscriptionGift.__table__.create(connection, checkfirst=True)


CHAIN_0077_SUBSCRIPTION_GIFTS = [
    Migration(
        id="0077_subscription_gifts",
        description="Add paid transferable subscription gifts",
        upgrade=_migration_0077_subscription_gifts,
    )
]
