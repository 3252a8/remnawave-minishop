from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import aiohttp
from pydantic import ValidationError

from bot.infra.redis import cache_get_json, cache_set_json, redis_key, redis_lock
from config.settings import Settings

from .kuma import parse_kuma_status_page
from .models import ProviderStatus, ServerStatus, StatusSource
from .xray_checker import parse_xray_proxies

logger = logging.getLogger(__name__)
MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024


class ProviderFetchError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ServerStatusService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._local_cache: dict[str, tuple[datetime, ServerStatus]] = {}

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _fingerprint(self) -> str:
        settings = self.settings
        provider = settings.SERVER_STATUS_PROVIDER
        provider_config: dict[str, object] = {"provider": provider}
        if provider == "uptime-kuma":
            provider_config.update(
                url=settings.SERVER_STATUS_KUMA_URL,
                slug=settings.SERVER_STATUS_KUMA_SLUG,
            )
        elif provider == "xray-checker":
            provider_config["url"] = settings.SERVER_STATUS_XRAY_CHECKER_URL
        provider_config["enabled"] = settings.SERVER_STATUS_ENABLED
        if provider == "url":
            provider_config["external_url"] = settings.SERVER_STATUS_URL
        serialized = json.dumps(provider_config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()[:24]

    def _cache_key(self, fingerprint: str) -> str:
        return redis_key(self.settings, "webapp", "server-status", "v1", fingerprint)

    def _safe_status(self, *, error: str | None = None) -> ServerStatus:
        provider = self.settings.SERVER_STATUS_PROVIDER
        sources = (
            [StatusSource(provider=provider, status="unknown", error=error)]
            if self.settings.SERVER_STATUS_ENABLED and provider != "url"
            else []
        )
        return ServerStatus(
            enabled=self.settings.SERVER_STATUS_ENABLED,
            status="unknown",
            updated_at=None,
            external_url=(
                self.settings.SERVER_STATUS_URL
                if self.settings.SERVER_STATUS_PROVIDER == "url"
                else None
            ),
            sources=sources,
        )

    async def _read_cache(self, fingerprint: str) -> tuple[datetime, ServerStatus] | None:
        local = self._local_cache.get(fingerprint)
        if local is not None:
            return local
        raw = await cache_get_json(self.settings, self._cache_key(fingerprint))
        if not isinstance(raw, dict):
            return None
        try:
            cached_at = datetime.fromisoformat(str(raw["cached_at"]))
            status = ServerStatus.model_validate(raw["status"])
        except (KeyError, TypeError, ValueError, ValidationError):
            return None
        cached_at = cached_at if cached_at.tzinfo else cached_at.replace(tzinfo=UTC)
        self._local_cache[fingerprint] = (cached_at, status)
        return cached_at, status

    async def _write_cache(
        self,
        fingerprint: str,
        cached_at: datetime,
        status: ServerStatus,
    ) -> None:
        self._local_cache = {fingerprint: (cached_at, status)}
        await cache_set_json(
            self.settings,
            self._cache_key(fingerprint),
            {
                "cached_at": cached_at.isoformat(),
                "status": status.model_dump(mode="json", by_alias=True),
            },
            max(
                1,
                self.settings.SERVER_STATUS_CACHE_TTL_SECONDS,
                self.settings.SERVER_STATUS_STALE_TTL_SECONDS,
            ),
        )

    def _cache_age(self, cached_at: datetime) -> float:
        return max(0.0, (datetime.now(UTC) - cached_at).total_seconds())

    @asynccontextmanager
    async def _refresh_lock(self, fingerprint: str) -> AsyncIterator[bool]:
        try:
            async with redis_lock(
                self.settings,
                f"server-status:{fingerprint}",
                ttl_seconds=max(1, int(self.settings.SERVER_STATUS_TIMEOUT_SECONDS) + 2),
            ) as acquired:
                yield acquired
        except Exception as exc:
            logger.warning(
                "server_status Redis lock unavailable; using local lock: %s",
                type(exc).__name__,
            )
            yield True

    async def get_status(self) -> ServerStatus:
        if not self.settings.SERVER_STATUS_ENABLED or self.settings.SERVER_STATUS_PROVIDER == "url":
            return self._safe_status()

        fingerprint = self._fingerprint()
        cached = await self._read_cache(fingerprint)
        if cached and self._cache_age(cached[0]) <= self.settings.SERVER_STATUS_CACHE_TTL_SECONDS:
            logger.debug("server_status_cache_hit cache=fresh")
            return cached[1].model_copy(update={"stale": False})

        async with self._lock:
            cached = await self._read_cache(fingerprint)
            if (
                cached
                and self._cache_age(cached[0]) <= self.settings.SERVER_STATUS_CACHE_TTL_SECONDS
            ):
                return cached[1].model_copy(update={"stale": False})
            async with self._refresh_lock(fingerprint) as acquired:
                if not acquired:
                    if (
                        cached
                        and self._cache_age(cached[0])
                        <= self.settings.SERVER_STATUS_STALE_TTL_SECONDS
                    ):
                        return cached[1].model_copy(update={"stale": True})
                    return self._safe_status(error="temporarily_unavailable")
                try:
                    result = await self._fetch_provider()
                except ProviderFetchError as exc:
                    if (
                        cached
                        and self._cache_age(cached[0])
                        <= self.settings.SERVER_STATUS_STALE_TTL_SECONDS
                    ):
                        logger.info("server_status_stale_returned error_type=%s", exc.code)
                        return cached[1].model_copy(update={"stale": True})
                    return self._safe_status(error=exc.code)

                now = datetime.now(UTC)
                status = ServerStatus(
                    enabled=True,
                    status=result.status,
                    updated_at=now,
                    stale=False,
                    external_url=None,
                    sources=[StatusSource(provider=result.provider, status=result.status)],
                    groups=result.groups,
                    incidents=result.incidents,
                )
                await self._write_cache(fingerprint, now, status)
                return status

    async def _fetch_json(self, provider: str, url: str) -> object:
        if self._session is None or self._session.closed:
            await self.start()
        assert self._session is not None
        timeout = aiohttp.ClientTimeout(total=self.settings.SERVER_STATUS_TIMEOUT_SECONDS)
        started = time.monotonic()
        try:
            async with self._session.get(url, timeout=timeout) as response:
                if response.status < 200 or response.status >= 300:
                    self._log_failure(provider, url, started, f"http_{response.status}")
                    raise ProviderFetchError("http_error")
                if (
                    response.content_length is not None
                    and response.content_length > MAX_PROVIDER_RESPONSE_BYTES
                ):
                    self._log_failure(provider, url, started, "response_too_large")
                    raise ProviderFetchError("response_too_large")
                body = await response.content.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
                    self._log_failure(provider, url, started, "response_too_large")
                    raise ProviderFetchError("response_too_large")
                payload = json.loads(body)
        except ProviderFetchError:
            raise
        except TimeoutError as exc:
            self._log_failure(provider, url, started, "timeout")
            raise ProviderFetchError("timeout") from exc
        except (aiohttp.ClientError, json.JSONDecodeError, ValueError) as exc:
            self._log_failure(provider, url, started, type(exc).__name__)
            raise ProviderFetchError("invalid_response") from exc
        logger.info(
            "server_status_fetch_success provider=%s host=%s duration_ms=%d",
            provider,
            urlsplit(url).hostname or "",
            int((time.monotonic() - started) * 1000),
        )
        return payload

    def _log_failure(self, provider: str, url: str, started: float, error_type: str) -> None:
        logger.warning(
            "server_status_fetch_failed provider=%s host=%s duration_ms=%d error_type=%s",
            provider,
            urlsplit(url).hostname or "",
            int((time.monotonic() - started) * 1000),
            error_type,
        )

    async def _fetch_provider(self) -> ProviderStatus:
        provider = self.settings.SERVER_STATUS_PROVIDER
        try:
            if provider == "uptime-kuma":
                base_url = str(self.settings.SERVER_STATUS_KUMA_URL or "").rstrip("/")
                slug = str(self.settings.SERVER_STATUS_KUMA_SLUG or "").strip()
                if not base_url or not slug:
                    raise ProviderFetchError("configuration_error")
                safe_slug = quote(slug, safe="")
                page, heartbeats = await asyncio.gather(
                    self._fetch_json(provider, f"{base_url}/api/status-page/{safe_slug}"),
                    self._fetch_json(
                        provider,
                        f"{base_url}/api/status-page/heartbeat/{safe_slug}",
                    ),
                )
                return parse_kuma_status_page(page, heartbeats)
            if provider == "xray-checker":
                base_url = str(self.settings.SERVER_STATUS_XRAY_CHECKER_URL or "").rstrip("/")
                if not base_url:
                    raise ProviderFetchError("configuration_error")
                payload = await self._fetch_json(provider, f"{base_url}/api/v1/public/proxies")
                return parse_xray_proxies(payload)
        except ProviderFetchError:
            raise
        except (TypeError, ValueError, ValidationError) as exc:
            raise ProviderFetchError("invalid_response") from exc
        raise ProviderFetchError("configuration_error")
