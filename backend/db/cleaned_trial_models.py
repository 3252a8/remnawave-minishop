"""Minimal trial-use history survives automatic deletion of the account."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class CleanedTrialIdentity(Base):
    __tablename__ = "cleaned_trial_identities"

    identity_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    cleaned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountCleanupIntent(Base):
    __tablename__ = "account_cleanup_intents"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    panel_uuids: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
