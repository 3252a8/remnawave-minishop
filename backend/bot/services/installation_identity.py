"""Stable local installation identity for neutral extension contracts.

The identity is a randomly generated UUID persisted in application settings.
It is intentionally independent of telemetry configuration or delivery.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import app_settings_dal

logger = logging.getLogger(__name__)

INSTALLATION_ID_KEY = "INSTALLATION_ID"


def _normalize_identity(value: Any) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        return None


async def _read_identity(session: AsyncSession, key: str) -> tuple[bool, str | None]:
    present, value = await app_settings_dal.get_override_value(session, key)
    if not present:
        return False, None
    identity = _normalize_identity(value)
    if identity is None:
        logger.warning("Ignoring malformed installation identity stored under %s", key)
    return True, identity


async def get_or_create_installation_identity(session: AsyncSession) -> str:
    """Return the installation UUID, creating it atomically when absent.

    Callers own transaction commit.
    """

    present, identity = await _read_identity(session, INSTALLATION_ID_KEY)
    if identity is not None:
        return identity

    candidate = str(uuid.uuid4())

    if present:
        # A malformed local value cannot represent this contract, so repair it.
        await app_settings_dal.upsert_override(
            session,
            key=INSTALLATION_ID_KEY,
            value=candidate,
            updated_by=None,
        )
    else:
        await app_settings_dal.insert_override_if_missing(
            session,
            key=INSTALLATION_ID_KEY,
            value=candidate,
            updated_by=None,
        )

    _stored, identity = await _read_identity(session, INSTALLATION_ID_KEY)
    if identity is None:
        raise RuntimeError("Failed to persist a stable installation identity")
    return identity
