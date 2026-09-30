"""Imported identifiers and native invitation aliases."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


class LegacyReferralCode(Base):
    __tablename__ = "legacy_referral_codes"

    legacy_code_id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, default="remnashop", index=True)
    code = Column(String(128), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User")

    __table_args__ = (UniqueConstraint("source", "code", name="uq_legacy_referral_source_code"),)


class LegacyImportMapping(Base):
    __tablename__ = "legacy_import_mappings"

    source = Column(String(64), primary_key=True)
    entity_type = Column(String(64), primary_key=True)
    source_id = Column(String(128), primary_key=True)
    target_table = Column(String(128), nullable=False)
    target_id = Column(String(128), nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
