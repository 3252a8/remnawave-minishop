"""Anonymous install telemetry beacon (self-hosted friendly, opt-out).

Once per ``TELEMETRY_INTERVAL_HOURS`` the worker sends a single obfuscation-free
but fully anonymous "heartbeat" to a PostHog ingestion endpoint so the project
maintainer can see how many installs are active and which versions/OSes are in
use. No personal data, bot tokens, domains or user identities are sent — only
an opaque per-install UUID plus coarse environment facts.

Operators can opt out in three independent ways, any of which stops the beacon:
  * ``TELEMETRY_ENABLED=false`` in ``.env``
  * the *System → Anonymous install analytics* toggle in the web admin (stored
    as a DB override and re-read every tick, so no restart is required)
  * leaving ``TELEMETRY_ENDPOINT`` / ``TELEMETRY_API_KEY`` empty in the image

Delivery is strictly fire-and-forget: every failure is swallowed so telemetry
can never delay, block or crash the worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import platform
import uuid
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.infra.redis import redis_lock
from bot.utils.app_version import (
    resolve_app_version,
    resolve_app_version_tag,
    resolve_build_provenance,
    resolve_image_modified,
)
from config.settings import Settings
from db.dal import app_settings_dal, user_dal

logger = logging.getLogger(__name__)

INSTALLATION_ID_KEY = "TELEMETRY_INSTALLATION_ID"
TELEMETRY_ENABLED_KEY = "TELEMETRY_ENABLED"
HEARTBEAT_EVENT = "installation_heartbeat"
INITIAL_DELAY_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 10

# Report the user count as a coarse range so individual installs stay anonymous
# and the property keeps a low cardinality for breakdowns.
_USER_BUCKETS = (
    (0, "0"),
    (10, "1-10"),
    (50, "11-50"),
    (200, "51-200"),
    (1000, "201-1000"),
    (5000, "1001-5000"),
)


def _bucket_users(count: int) -> str:
    for upper, label in _USER_BUCKETS:
        if count <= upper:
            return label
    return "5000+"


class TelemetryWorker:
    def __init__(self, settings: Settings, session_factory: sessionmaker):
        self.settings = settings
        self.session_factory = session_factory
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    def _delivery_configured(self) -> bool:
        return bool(
            str(self.settings.TELEMETRY_ENDPOINT or "").strip()
            and str(self.settings.TELEMETRY_API_KEY or "").strip()
        )

    async def run(self) -> None:
        if not self._delivery_configured():
            logger.info("Telemetry endpoint/key not configured; anonymous beacon disabled")
            return
        logger.info(
            "Anonymous install telemetry is ON (endpoint=%s, every %sh). "
            "It sends an opaque install id, version, OS and a user-count range — "
            "no personal data. Opt out via TELEMETRY_ENABLED=false or "
            "Admin -> System -> Anonymous install analytics. "
            "See docs/configuration/telemetry.md.",
            self.settings.TELEMETRY_ENDPOINT,
            self.settings.TELEMETRY_INTERVAL_HOURS,
        )
        await self._sleep(INITIAL_DELAY_SECONDS)
        while not self._stopped.is_set():
            try:
                await self._beacon_tick()
            except Exception:
                logger.exception("Telemetry beacon tick failed")
            await self._sleep(self._interval_seconds())

    def _interval_seconds(self) -> int:
        return max(1, int(self.settings.TELEMETRY_INTERVAL_HOURS or 24)) * 3600

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stopped.wait(), timeout=seconds)

    async def _beacon_tick(self) -> None:
        # A short-lived lock keeps a single beacon per interval even when the
        # worker is scaled to several replicas. Without Redis the lock yields
        # True, which is correct for the common single-worker deployment.
        async with redis_lock(
            self.settings,
            "telemetry-beacon",
            ttl_seconds=max(60, self._interval_seconds() // 2),
        ) as acquired:
            if not acquired:
                return
            async with self.session_factory() as session:
                if not await self._is_enabled(session):
                    return
                installation_id = await self._get_or_create_installation_id(session)
                payload = await self._build_payload(session, installation_id)
                await session.commit()
            await self._send(payload)

    async def _is_enabled(self, session: AsyncSession) -> bool:
        # The web admin writes the toggle as a DB override. The worker process
        # does not apply overrides onto its in-memory Settings, so read it
        # straight from the table; the env default applies when unset.
        present, value = await app_settings_dal.get_override_value(session, TELEMETRY_ENABLED_KEY)
        if present:
            return bool(value)
        return bool(self.settings.TELEMETRY_ENABLED)

    async def _get_or_create_installation_id(self, session: AsyncSession) -> str:
        present, value = await app_settings_dal.get_override_value(session, INSTALLATION_ID_KEY)
        if present and value:
            return str(value)
        installation_id = str(uuid.uuid4())
        await app_settings_dal.upsert_override(
            session,
            key=INSTALLATION_ID_KEY,
            value=installation_id,
            updated_by=None,
        )
        return installation_id

    def _enabled_payment_providers(self) -> list[str]:
        try:
            from bot.payment_providers import iter_provider_specs

            providers = [
                str(spec.id)
                for spec in iter_provider_specs()
                if spec.is_effectively_enabled(self.settings)
            ]
            return sorted(set(providers))
        except Exception:
            logger.debug("Telemetry: failed to enumerate payment providers", exc_info=True)
            return []

    async def _build_payload(self, session: AsyncSession, installation_id: str) -> dict[str, Any]:
        try:
            user_count = await user_dal.count_all_users(session)
        except Exception:
            logger.debug("Telemetry: failed to count users", exc_info=True)
            user_count = 0

        version = resolve_app_version()
        version_tag = resolve_app_version_tag()
        build_provenance = resolve_build_provenance()
        image_modified = resolve_image_modified()
        # Person properties (``$set``) snapshot the latest state per install, so
        # "version breakdown" in PostHog is a person-property breakdown.
        person_props = {
            "app_version": version,
            "app_version_tag": version_tag,
            "build_provenance": build_provenance,
            "image_modified": image_modified,
            "os": platform.system().lower() or "unknown",
            "arch": platform.machine().lower() or "unknown",
            "python_version": platform.python_version(),
            "locale": str(self.settings.DEFAULT_LANGUAGE or ""),
            "users_bucket": _bucket_users(int(user_count or 0)),
            "webapp_enabled": bool(self.settings.WEBAPP_ENABLED),
            "panel_configured": bool(str(self.settings.PANEL_API_URL or "").strip()),
            "payment_providers": self._enabled_payment_providers(),
        }
        properties = {
            **person_props,
            "$lib": "remnawave-minishop",
            "$lib_version": version,
            "$set": person_props,
        }
        return {
            "api_key": str(self.settings.TELEMETRY_API_KEY or "").strip(),
            "event": HEARTBEAT_EVENT,
            "distinct_id": installation_id,
            "properties": properties,
        }

    async def _send(self, payload: dict[str, Any]) -> None:
        url = str(self.settings.TELEMETRY_ENDPOINT or "").strip().rstrip("/") + "/capture/"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as http,
                http.post(url, json=payload) as resp,
            ):
                if resp.status >= 400:
                    body = (await resp.text())[:200]
                    logger.warning("Telemetry beacon rejected: HTTP %s %s", resp.status, body)
                else:
                    logger.debug("Telemetry beacon delivered (HTTP %s)", resp.status)
        except Exception:
            # Never let telemetry surface as an error to operators.
            logger.debug("Telemetry beacon delivery failed", exc_info=True)
