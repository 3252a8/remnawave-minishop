"""Preserve legacy advertising and add durable evidence and reporting tables."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from db.advertising_models import (
    AdAudit,
    AdAuthContext,
    AdExternalMetric,
    AdImportBatch,
    AdLink,
    AdMatchCandidate,
    AdOfferActivation,
    AdPromoBinding,
    AdPurchaseAttribution,
    AdSpendEntry,
    AdTouchpoint,
    AdUtmRule,
    AdVisit,
)

from .engine import Migration


def _migration_0097_advertising_evidence(connection: Connection) -> None:
    columns = {column["name"] for column in inspect(connection).get_columns("ad_campaigns")}
    additions = {
        "name": "VARCHAR(160)",
        "description": "TEXT",
        "archived_at": "TIMESTAMPTZ",
        "report_currency": "VARCHAR(8) NOT NULL DEFAULT 'RUB'",
        "attribution_window_days": "INTEGER NOT NULL DEFAULT 30",
        "spend_source": "VARCHAR(16) NOT NULL DEFAULT 'legacy'",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(text(f"ALTER TABLE ad_campaigns ADD COLUMN {name} {definition}"))
    for model in (
        AdLink,
        AdVisit,
        AdTouchpoint,
        AdPromoBinding,
        AdPurchaseAttribution,
        AdSpendEntry,
        AdImportBatch,
        AdExternalMetric,
        AdMatchCandidate,
        AdUtmRule,
        AdAudit,
        AdAuthContext,
        AdOfferActivation,
    ):
        model.__table__.create(connection, checkfirst=True)


CHAIN_0097_ADVERTISING_EVIDENCE = [
    Migration(
        id="0097_advertising_evidence",
        description="Durable advertising contacts and reporting",
        upgrade=_migration_0097_advertising_evidence,
    )
]
