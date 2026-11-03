"""Telegram adapter observations, independent of account identity and entitlements."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_mixin


@declarative_mixin
class UserTelegramStateColumns:
    telegram_birthday_month_day = Column(Integer, nullable=True, index=True)
    telegram_birthday_checked_at = Column(DateTime(timezone=True), nullable=True)
    telegram_birthday_checked_for = Column(BigInteger, nullable=True)
    telegram_birthday_sent_year = Column(Integer, nullable=True)
    telegram_notifications_status = Column(String(32), nullable=False, default="unknown")
    telegram_notifications_checked_at = Column(DateTime(timezone=True), nullable=True)
    telegram_notifications_observation_order = Column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    telegram_notifications_enabled_at = Column(DateTime(timezone=True), nullable=True)
    telegram_notifications_blocked_at = Column(DateTime(timezone=True), nullable=True)
    channel_subscription_verified = Column(Boolean, nullable=True)
    channel_subscription_checked_at = Column(DateTime(timezone=True), nullable=True)
    channel_subscription_observation_order = Column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    channel_subscription_verified_for = Column(BigInteger, nullable=True)
