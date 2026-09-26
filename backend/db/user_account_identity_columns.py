"""Stable account identifiers and the panel username recorded for each user."""

import uuid

from sqlalchemy import Column, Computed, String, Uuid, text


class UserAccountIdentityColumns:
    account_id = Column(
        Uuid(as_uuid=True),
        nullable=False,
        unique=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    minishop_id = Column(
        String(35),
        Computed("'ms_' || replace(CAST(account_id AS VARCHAR), '-', '')", persisted=True),
        nullable=False,
        unique=True,
    )
    panel_username = Column(String(255), nullable=True)
    panel_origin = Column(String(64), nullable=True)
    panel_username_state = Column(
        String(32), nullable=False, default="unverified", server_default="unverified"
    )
