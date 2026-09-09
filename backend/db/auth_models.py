"""External login and WebAuthn persistence models."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


class UserExternalIdentity(Base):
    """Stable identity received from an external OAuth/OIDC provider."""

    __tablename__ = "user_external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_external_identity_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_external_identity_user_provider"),
    )

    identity_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    email = Column(String(254), nullable=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    display_name = Column(String(255), nullable=True)
    picture_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")


class UserEmailAddress(Base):
    """A verified address attached to an account independently of its login provider."""

    __tablename__ = "user_email_addresses"
    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email_address_email"),
        Index(
            "uq_user_email_addresses_primary",
            "user_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary = 1"),
        ),
        Index(
            "uq_user_email_addresses_notification",
            "user_id",
            unique=True,
            postgresql_where=text("is_notification"),
            sqlite_where=text("is_notification = 1"),
        ),
    )

    email_address_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    email = Column(String(254), nullable=False)
    source = Column(String(32), nullable=False, default="email")
    verified_at = Column(DateTime(timezone=True), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    is_notification = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User")


class UserPasskeyCredential(Base):
    """A WebAuthn public-key credential."""

    __tablename__ = "user_passkey_credentials"

    credential_pk = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    credential_id = Column(String(1024), nullable=False, unique=True, index=True)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(BigInteger, nullable=False, default=0)
    transports = Column(String(255), nullable=True)
    device_type = Column(String(32), nullable=True)
    backed_up = Column(Boolean, nullable=False, default=False)
    name = Column(String(80), nullable=False, default="Passkey")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")


class WebAuthnChallenge(Base):
    """Single-use WebAuthn challenge stored as a digest to prevent replay."""

    __tablename__ = "webauthn_challenges"

    challenge_hash = Column(String(64), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    ceremony = Column(String(16), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
