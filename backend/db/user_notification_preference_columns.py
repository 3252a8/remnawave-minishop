"""SQLAlchemy columns for per-user notification delivery preferences."""

from sqlalchemy import Boolean, Column, text
from sqlalchemy.orm import declarative_mixin


@declarative_mixin
class UserNotificationPreferenceColumns:
    marketing_notifications_email_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    marketing_notifications_telegram_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    system_notifications_email_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    system_notifications_telegram_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
