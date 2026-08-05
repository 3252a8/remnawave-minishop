import asyncio
import contextlib
import json
import logging
import time
from types import TracebackType
from typing import Any
from urllib.parse import urlencode

import aiohttp

from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from config.settings_models import PanelSettings

logger = logging.getLogger(__name__)

# Static endpoint prefixes used as log/metric labels instead of the raw request
# path. Endpoints embed user identifiers (telegram id, username, email, uuids),
# so logging the path verbatim would leak private data into log files; the
# label keeps only the constant prefix. Longest prefixes first so e.g.

_ENDPOINT_LOG_LABELS = (
    "/users/by-telegram-id",
    "/users/by-username",
    "/users/by-email",
    "/users/stream",
    "/users",
    "/external-squads",
    "/subscriptions/subpage-config",
    "/subscription-page-configs",
    "/hwid/devices/delete",
    "/hwid/devices/stats",
    "/hwid/devices/top-users",
    "/hwid/devices",
    "/system/stats/bandwidth",
    "/system/stats/nodes",
    "/system/stats",
    "/bandwidth-stats/users",
    "/bandwidth-stats/nodes",
    "/internal-squads",
    "/hosts",
    "/nodes",
)


def _endpoint_log_label(endpoint: str) -> str:
    """Map a request endpoint to a constant, identifier-free label for logs."""
    path = "/" + endpoint.split("?", 1)[0].strip("/")
    for label in _ENDPOINT_LOG_LABELS:
        if path == label or path.startswith(label + "/"):
            return label
    return "/other"


class PanelApiCoreMixin:
    # Status codes returned by _request_once for failures we consider transient
    # (connect error, request timeout) and therefore worth retrying on safe methods.
    _TRANSIENT_STATUS_CODES = (-1, -3)
    _SAFE_METHODS = frozenset({"GET", "HEAD"})
    _RETRY_BACKOFF_SECONDS = 0.5
    _MIN_TIMEOUT_SECONDS = 0.1
    _DEFAULT_TOTAL_TIMEOUT_SECONDS = 25.0
    _DEFAULT_CONNECT_TIMEOUT_SECONDS = 8.0
    _DEFAULT_SOCK_CONNECT_TIMEOUT_SECONDS = 8.0
    _DEFAULT_SOCK_READ_TIMEOUT_SECONDS = 15.0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.panel_settings: PanelSettings = settings.panel_settings
        self.base_url = self.panel_settings.api_url
        self.api_key = self.panel_settings.api_key
        self.api_cookie = self.panel_settings.api_cookie
        self._session: aiohttp.ClientSession | None = None
        self.default_client_ip = "127.0.0.1"
        # Cache slow-changing reference data fetched from the panel. Errors and
        # None responses are not cached, so transient failures self-heal.
        self._squads_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=300,
            settings=settings,
            namespace="panel:squads",
        )
        self._hosts_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=300,
            settings=settings,
            namespace="panel:hosts",
        )
        self._users_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=max(0, int(settings.PANEL_USER_CACHE_TTL_SECONDS or 0)),
            settings=settings,
            namespace="panel:users",
        )
        self._devices_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=max(0, int(settings.PANEL_DEVICES_CACHE_TTL_SECONDS or 0)),
            settings=settings,
            namespace="panel:devices",
        )
        self._external_squads_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=max(
                0,
                int(getattr(settings, "PANEL_EXTERNAL_SQUADS_CACHE_TTL_SECONDS", 300) or 0),
            ),
            settings=settings,
            namespace="panel:external_squads",
        )
        self._all_users_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=max(
                0,
                int(settings.PANEL_ALL_USERS_CACHE_TTL_SECONDS or 0),
            ),
            settings=settings,
            namespace="panel:all_users",
        )

    async def __aenter__(self) -> "PanelApiCoreMixin":
        """Context manager entry"""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit - automatically close session"""
        await self.close_session()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._client_timeout())
        return self._session

    @classmethod
    def _timeout_setting(cls, raw_value: Any, default: float) -> float:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return default
        if value <= 0:
            return default
        return max(cls._MIN_TIMEOUT_SECONDS, value)

    def _client_timeout(self) -> aiohttp.ClientTimeout:
        # Separate connect/read timeouts so a slow panel route has more room,
        # while genuinely stuck requests still cannot pin a worker forever.
        panel_settings = self.panel_settings
        return aiohttp.ClientTimeout(
            total=self._timeout_setting(
                panel_settings.api_total_timeout_seconds,
                self._DEFAULT_TOTAL_TIMEOUT_SECONDS,
            ),
            connect=self._timeout_setting(
                panel_settings.api_connect_timeout_seconds,
                self._DEFAULT_CONNECT_TIMEOUT_SECONDS,
            ),
            sock_connect=self._timeout_setting(
                panel_settings.api_sock_connect_timeout_seconds,
                self._DEFAULT_SOCK_CONNECT_TIMEOUT_SECONDS,
            ),
            sock_read=self._timeout_setting(
                panel_settings.api_sock_read_timeout_seconds,
                self._DEFAULT_SOCK_READ_TIMEOUT_SECONDS,
            ),
        )

    async def close_session(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("Panel API service HTTP session closed.")

    async def close(self) -> None:
        """Alias for close_session for API consistency."""
        await self.close_session()

    async def _prepare_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": self.default_client_ip,
            "X-Real-IP": self.default_client_ip,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.api_cookie:
            headers["Cookie"] = str(self.api_cookie).strip()
        return headers

    def _is_transient_error(self, result: dict[str, Any] | None) -> bool:
        if not isinstance(result, dict) or not result.get("error"):
            return False
        code = result.get("status_code")
        if code in self._TRANSIENT_STATUS_CODES:
            return True
        return isinstance(code, int) and 500 <= code < 600

    async def _request(
        self, method: str, endpoint: str, log_full_response: bool = False, **kwargs: Any
    ) -> dict[str, Any] | None:
        # Retry safe (idempotent) methods once on transient failures to absorb
        # network blips and short panel restarts without surfacing errors.
        max_attempts = 2 if method.upper() in self._SAFE_METHODS else 1
        result: dict[str, Any] | None = None
        for attempt in range(max_attempts):
            result = await self._request_once(method, endpoint, log_full_response, **kwargs)
            if attempt + 1 < max_attempts and self._is_transient_error(result):
                logger.warning(
                    "Retrying transient Panel API request method=%s endpoint=%s "
                    "attempt=%s/%s status_code=%s",
                    method.upper(),
                    _endpoint_log_label(endpoint),
                    attempt + 1,
                    max_attempts,
                    result.get("status_code") if isinstance(result, dict) else None,
                )
                await asyncio.sleep(self._RETRY_BACKOFF_SECONDS)
                continue
            return result
        return result

    async def _request_once(
        self, method: str, endpoint: str, log_full_response: bool = False, **kwargs: Any
    ) -> dict[str, Any] | None:
        if not self.base_url:
            logger.error("Panel API URL (PANEL_API_URL) not configured in settings.")
            return {"error": True, "status_code": 0, "message": "Panel API URL not configured."}

        aiohttp_session = await self._get_session()
        headers = await self._prepare_headers()

        url_for_request = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        endpoint_label = _endpoint_log_label(endpoint)

        current_params = kwargs.get("params")
        url_with_params_for_log = url_for_request
        if current_params:
            with contextlib.suppress(Exception):
                url_with_params_for_log += "?" + urlencode(current_params)

        json_payload_for_log = (
            kwargs.get("json") if method.upper() in ["POST", "PATCH", "PUT"] else None
        )
        log_prefix = f"Panel API Req: {method.upper()} {url_with_params_for_log}"
        if json_payload_for_log:
            try:
                payload_str = json.dumps(json_payload_for_log)
                log_prefix += (
                    f" | Payload: {payload_str[:300]}{'...' if len(payload_str) > 300 else ''}"
                )
            except Exception:
                log_prefix += f" | Payload: {str(json_payload_for_log)[:300]}..."
        started = time.monotonic()
        try:
            async with aiohttp_session.request(
                method.upper(), url_for_request, headers=headers, **kwargs
            ) as response:
                response_status = response.status
                response_text = await response.text()
                logger.info(
                    "metric panel_latency_seconds=%.3f method=%s endpoint=%s status=%s",
                    time.monotonic() - started,
                    method.upper(),
                    endpoint_label,
                    response_status,
                )

                log_suffix = f"| Status: {response_status}"

                if log_full_response or not (200 <= response_status < 300):
                    try:
                        parsed_json_for_log = json.loads(response_text)
                        pretty_response_text = json.dumps(
                            parsed_json_for_log, indent=2, ensure_ascii=False
                        )
                        logger.info(
                            "%s %s | Full Response Body:\n%s",
                            log_prefix,
                            log_suffix,
                            pretty_response_text,
                        )
                    except json.JSONDecodeError:
                        logger.info(
                            "%s %s | Full Response Text (not JSON):\n%s%s",
                            log_prefix,
                            log_suffix,
                            response_text[:2000],
                            "..." if len(response_text) > 2000 else "",
                        )
                else:
                    logger.debug(
                        "%s %s | OK. Response Body Preview: %s%s",
                        log_prefix,
                        log_suffix,
                        response_text[:200],
                        "..." if len(response_text) > 200 else "",
                    )

                if 200 <= response_status < 300:
                    content_type = response.headers.get("Content-Type", "").lower()
                    media_type = content_type.split(";", 1)[0].strip()
                    is_json_response = media_type == "application/json" or media_type.endswith(
                        "+json"
                    )
                    if not is_json_response:
                        logger.error(
                            "%s %s | Panel API protocol error: expected JSON, got %s.",
                            log_prefix,
                            log_suffix,
                            content_type or "an unspecified content type",
                        )
                        return {
                            "error": True,
                            "status_code": response_status,
                            "message": "Panel API returned an unexpected non-JSON response.",
                            "details": {"content_type": content_type or None},
                        }
                    try:
                        data = json.loads(response_text)
                        if isinstance(data, dict):
                            return data
                        return {"status": "success", "code": response_status, "data": data}
                    except json.JSONDecodeError as e_json_ok:
                        logger.error(
                            "%s %s | OK but JSON Parse Error. Error: %s. Body was logged above.",
                            log_prefix,
                            log_suffix,
                            e_json_ok,
                        )
                        return {
                            "error": True,
                            "status_code": response_status,
                            "message": "Panel API returned invalid JSON.",
                            "details": {
                                "content_type": content_type,
                                "parse_error": str(e_json_ok),
                            },
                        }
                else:
                    error_details = {
                        "message": f"Request failed with status {response_status}",
                        "raw_response_text": response_text,
                    }
                    try:
                        if "application/json" in response.headers.get("Content-Type", "").lower():
                            error_json_data = json.loads(response_text)
                            if isinstance(error_json_data, dict):
                                error_details.update(error_json_data)
                    except json.JSONDecodeError:
                        pass
                    return {"error": True, "status_code": response_status, "details": error_details}

        except aiohttp.ClientConnectorError as e:
            logger.info(
                "metric panel_latency_seconds=%.3f method=%s endpoint=%s status=connect_error",
                time.monotonic() - started,
                method.upper(),
                endpoint_label,
            )
            logger.error(
                "Panel API ClientConnectorError method=%s endpoint=%s: %s",
                method.upper(),
                endpoint_label,
                e,
            )
            return {"error": True, "status_code": -1, "message": f"Connection error: {e!s}"}
        except aiohttp.ServerTimeoutError as e:
            logger.info(
                "metric panel_latency_seconds=%.3f method=%s endpoint=%s status=timeout",
                time.monotonic() - started,
                method.upper(),
                endpoint_label,
            )
            logger.warning(
                "Panel API timeout method=%s endpoint=%s: %s", method.upper(), endpoint_label, e
            )
            return {"error": True, "status_code": -3, "message": f"Request timed out: {e!s}"}
        except aiohttp.ClientError as e:
            logger.info(
                "metric panel_latency_seconds=%.3f method=%s endpoint=%s status=client_error",
                time.monotonic() - started,
                method.upper(),
                endpoint_label,
            )
            logger.exception(
                "Panel API ClientError method=%s endpoint=%s.", method.upper(), endpoint_label
            )
            return {"error": True, "status_code": -2, "message": f"Client error: {e!s}"}
        except TimeoutError:
            logger.info(
                "metric panel_latency_seconds=%.3f method=%s endpoint=%s status=timeout",
                time.monotonic() - started,
                method.upper(),
                endpoint_label,
            )
            logger.error(
                "Panel API request timed out method=%s endpoint=%s.",
                method.upper(),
                endpoint_label,
            )
            return {"error": True, "status_code": -3, "message": "Request timed out"}
        except Exception as e:
            logger.info(
                "metric panel_latency_seconds=%.3f method=%s endpoint=%s status=unexpected_error",
                time.monotonic() - started,
                method.upper(),
                endpoint_label,
            )
            logger.exception(
                "Unexpected Panel API request error method=%s endpoint=%s: %s",
                method.upper(),
                endpoint_label,
                e,
            )
            return {"error": True, "status_code": -4, "message": f"Unexpected error: {e!s}"}
