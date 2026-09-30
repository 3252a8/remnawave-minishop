"""Queue new period accruals without replaying historical successful payments."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from db.referral_accrual_models import ReferralPeriodAccrual

from .engine import Migration


def _migration_0094_referral_accruals(connection: Connection) -> None:
    payment_columns = {column["name"] for column in inspect(connection).get_columns("payments")}
    if "referral_accrual_processed" not in payment_columns:
        connection.execute(
            text(
                "ALTER TABLE payments ADD COLUMN referral_accrual_processed "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        connection.execute(text("UPDATE payments SET referral_accrual_processed = TRUE"))
    user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
    if "period_accrual_reserved_until" not in user_columns:
        connection.execute(
            text(
                "ALTER TABLE users ADD COLUMN period_accrual_reserved_until "
                "TIMESTAMP WITH TIME ZONE"
            )
        )
    ReferralPeriodAccrual.__table__.create(connection, checkfirst=True)


CHAIN_0094_REFERRAL_ACCRUALS = [
    Migration(
        id="0094_referral_accruals",
        description="Persist invitation period accrual and retry state",
        upgrade=_migration_0094_referral_accruals,
    )
]
