"""Subscription consent and the paid terms chosen for renewing a grant."""

from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import declarative_mixin


@declarative_mixin
class SubscriptionRenewalColumns:
    auto_renew_enabled = Column(Boolean, default=True, index=True)
    auto_renew_consent_version = Column(Integer, nullable=False, default=0)
    balance_renewal_provider = Column(String(32), nullable=True)
    balance_renewal_tariff_key = Column(String, nullable=True)
    balance_renewal_duration_days = Column(Integer, nullable=True)
