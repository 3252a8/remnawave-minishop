"""User-chosen labels for panel HWID devices."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.sql import func

from db.base import Base


class UserDeviceName(Base):
    """A label keyed by the opaque device token the API exposes, never the raw HWID."""

    __tablename__ = "user_device_names"

    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    device_token = Column(String(32), primary_key=True)
    name = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
