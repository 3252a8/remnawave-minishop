"""Hosted mandate ownership and per-charge fulfillment; append-only schema."""

from sqlalchemy.engine import Connection

from db.provider_mandate_models import ProviderMandate

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    ProviderMandate.__table__.create(connection, checkfirst=True)


CHAIN_0105_PROVIDER_MANDATES = [
    Migration(
        id="0105_provider_mandates",
        description="Persist provider-managed mandate ownership and first charge identity",
        upgrade=_upgrade,
    )
]
