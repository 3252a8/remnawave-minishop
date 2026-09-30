"""Persist a rotation intent before revoking public access."""

from sqlalchemy.engine import Connection

from db.subscription_access_rotation_models import SubscriptionAccessRotation

from .engine import Migration


def _migration_0095_access_rotations(connection: Connection) -> None:
    SubscriptionAccessRotation.__table__.create(connection, checkfirst=True)


CHAIN_0095_ACCESS_ROTATIONS = [
    Migration(
        id="0095_access_rotations",
        description="Serialize and recover subscription access rotations",
        upgrade=_migration_0095_access_rotations,
    )
]
