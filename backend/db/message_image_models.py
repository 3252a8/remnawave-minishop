"""Immutable image metadata shared by support and outbound messages."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from db.base import Base


class MessageImage(Base):
    __tablename__ = "message_images"
    __table_args__ = (Index("ix_message_images_digest", "digest"),)

    image_id = Column(String(32), primary_key=True)
    digest = Column(String(64), nullable=False)
    filename = Column(String(96), nullable=False)
    content_type = Column(String(32), nullable=False, default="image/webp")
    size_bytes = Column(BigInteger, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
