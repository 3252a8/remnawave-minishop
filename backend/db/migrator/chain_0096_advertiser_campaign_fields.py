"""Add advertiser_id and stats_reset_at to ad_campaigns."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _migration_0096_advertiser_campaign_fields(connection: Connection) -> None:
    inspector = inspect(connection)
    columns: set[str] = {col["name"] for col in inspector.get_columns("ad_campaigns")}

    if "stats_reset_at" not in columns:
        connection.execute(text("ALTER TABLE ad_campaigns ADD COLUMN stats_reset_at TIMESTAMPTZ"))

    if "advertiser_id" not in columns:
        connection.execute(text("ALTER TABLE ad_campaigns ADD COLUMN advertiser_id BIGINT"))
        if connection.dialect.name != "sqlite":
            connection.execute(
                text(
                    "ALTER TABLE ad_campaigns ADD CONSTRAINT fk_ad_campaigns_advertiser "
                    "FOREIGN KEY (advertiser_id) REFERENCES users(user_id) ON DELETE SET NULL"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_ad_campaigns_advertiser_id "
                "ON ad_campaigns(advertiser_id)"
            )
        )


CHAIN_0096_ADVERTISER_CAMPAIGN_FIELDS: list[Migration] = [
    Migration(
        id="0096_advertiser_campaign_fields",
        description="Add advertiser_id and stats_reset_at to ad_campaigns",
        upgrade=_migration_0096_advertiser_campaign_fields,
    )
]
