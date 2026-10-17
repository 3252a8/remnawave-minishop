"""Retain trial-use history without retaining a deleted user account."""

from sqlalchemy.engine import Connection

from db.cleaned_trial_models import AccountCleanupIntent, CleanedTrialIdentity

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    CleanedTrialIdentity.__table__.create(connection, checkfirst=True)
    AccountCleanupIntent.__table__.create(connection, checkfirst=True)


CHAIN_0107_CLEANED_TRIAL_HISTORY = [
    Migration(
        id="0107_cleaned_trial_history",
        description="Retain trial use after automatic account cleanup",
        upgrade=_upgrade,
    )
]
