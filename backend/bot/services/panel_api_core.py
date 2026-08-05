import asyncio
import json
import logging
import time
from types import TracebackType
from typing import Any

import aiohttp

from bot.services.panel_api_compat import (
    PanelApiCompatibility,
    compatible_panel_user_reference,
    numeric_panel_user_id,
)
from bot.services.panel_api_contracts import (
    PanelApiCapability,
    PanelApiOperation,
    endpoint_log_labels,
    operation_contract,
)
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from config.settings_models import PanelSettings

logger = logging.getLogger(__name__)

_ENDPOINT_LOG_LABELS = endpoint_log_labels()


def _endpoint_log_label(
    endpoint: str,
    operation: PanelApiOperation | None = None,
) -> str:
    """Map a request endpoint to a constant, identifier-free label for logs."""
    if operation is not None:
        return operation_contract(operation).log_label
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
    _PANEL_COMPATIBILITY_TTL_SECONDS = 300.0
    _PANEL_USER_COUNT_HINT_TTL_SECONDS = 300.0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.panel_settings: PanelSettings = settings.panel_settings
        self.base_url = self.panel_settings.api_url
        self.api_key = self.panel_settings.api_key
        self.api_cookie = self.panel_settings.api_cookie
        self._session: aiohttp.ClientSession | None = None
        self._panel_api_compatibility: PanelApiCompatibility | None = None
        self._panel_api_compatibility_detected_at: float | None = None
        self._panel_api_compatibility_lock = asyncio.Lock()
        self._observed_panel_capabilities: dict[PanelApiCapability, bool] = {}
        self._panel_user_count_hint = 0
        self._panel_user_count_observed_at: float | None = None
        self._reported_incompatible_user_references: set[tuple[str, PanelApiOperation]] = set()
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

    async def get_panel_api_compatibility(
        self, *, force_refresh: bool = False
    ) -> PanelApiCompatibility:
        """Detect and cache the panel generation through its stable metadata API.

        ``GET /system/metadata`` exists in Remnawave 2.8.1 and supported 3.x releases.
        Failures are intentionally not cached, so a panel that is still
        starting can be detected on a later request.
        """
        detected_at = self._panel_api_compatibility_detected_at
        cached_is_fresh = bool(
            self._panel_api_compatibility is not None
            and detected_at is not None
            and time.monotonic() - detected_at < self._PANEL_COMPATIBILITY_TTL_SECONDS
        )
        if cached_is_fresh and not force_refresh:
            return self._panel_api_compatibility
        async with self._panel_api_compatibility_lock:
            detected_at = self._panel_api_compatibility_detected_at
            cached_is_fresh = bool(
                self._panel_api_compatibility is not None
                and detected_at is not None
                and time.monotonic() - detected_at < self._PANEL_COMPATIBILITY_TTL_SECONDS
            )
            if cached_is_fresh and not force_refresh:
                return self._panel_api_compatibility
            response = await self._request(
                "GET",
                "/system/metadata",
                operation=PanelApiOperation.SYSTEM_METADATA,
                log_full_response=False,
            )
            compatibility = PanelApiCompatibility.from_metadata(response)
            if compatibility.version is not None:
                previous_version = (
                    self._panel_api_compatibility.version
                    if self._panel_api_compatibility is not None
                    else None
                )
                if previous_version != compatibility.version:
                    self._observed_panel_capabilities.clear()
                self._panel_api_compatibility = compatibility
                self._panel_api_compatibility_detected_at = time.monotonic()
                logger.info(
                    "Detected Remnawave panel version %s generation=%s support=%s "
                    "user_identity=%s.",
                    compatibility.version,
                    compatibility.generation.value,
                    compatibility.support_status,
                    compatibility.user_id_mode.value,
                )
            else:
                logger.warning(
                    "Could not detect Remnawave panel version; API compatibility "
                    "will be selected from identifiers and endpoint responses."
                )
            return self._panel_api_compatibility or compatibility

    def panel_capability_state(
        self,
        capability: PanelApiCapability,
        compatibility: PanelApiCompatibility,
    ) -> bool | None:
        """Return observed capability state before the version-derived default."""
        if capability in self._observed_panel_capabilities:
            return self._observed_panel_capabilities[capability]
        return compatibility.supports(capability)

    def remember_panel_capability(
        self,
        capability: PanelApiCapability,
        supported: bool,
    ) -> None:
        """Cache a route observation for the current panel version."""
        previous = self._observed_panel_capabilities.get(capability)
        self._observed_panel_capabilities[capability] = supported
        if previous != supported:
            logger.info(
                "Observed Remnawave capability %s=%s.",
                capability.value,
                supported,
            )

    def remember_panel_user_count(self, count: int) -> None:
        """Keep a cheap size hint for adaptive stream-versus-point reads."""
        self._panel_user_count_hint = max(0, int(count))
        self._panel_user_count_observed_at = time.monotonic()

    def panel_user_count_hint(self) -> int:
        observed_at = self._panel_user_count_observed_at
        if (
            observed_at is None
            or time.monotonic() - observed_at > self._PANEL_USER_COUNT_HINT_TTL_SECONDS
        ):
            return 0
        return max(0, int(self._panel_user_count_hint))

    async def panel_mutation_allowed(
        self,
        operation: PanelApiOperation,
        *,
        compatibility: PanelApiCompatibility | None = None,
    ) -> bool:
        """Probe compatibility before writes and reject only explicitly blocked releases.

        An unavailable metadata endpoint remains best-effort compatible so a
        temporary panel startup/auth problem does not disable writes. Future
        majors are also allowed in best-effort mode because a major bump does not
        necessarily change these API contracts; health diagnostics still mark
        them unverified until the live matrix certifies them.
        """
        contract = operation_contract(operation)
        if not contract.mutation:
            return True
        compatibility = compatibility or await self.get_panel_api_compatibility()
        if compatibility.explicitly_unsupported:
            logger.error(
                "Blocked Remnawave mutation operation=%s version=%s: this exact "
                "release is listed as incompatible by the support manifest.",
                operation.value,
                compatibility.version,
            )
            return False
        if compatibility.unreviewed_generation:
            logger.warning(
                "Using unverified Remnawave generation in best-effort mode "
                "operation=%s version=%s.",
                operation.value,
                compatibility.version,
            )
        return True

    async def resolve_panel_user_reference(
        self,
        value: object,
        operation: PanelApiOperation,
        *,
        compatibility: PanelApiCompatibility | None = None,
    ) -> str | None:
        """Validate a legacy UUID or numeric id against the detected panel API.

        The raw identifier is deliberately never logged.  A mismatch normally
        means the local database has not yet been relinked after a 2.x -> 3.x
        upgrade (or after a rollback in the opposite direction).
        """
        compatibility = compatibility or await self.get_panel_api_compatibility()
        resolved = compatible_panel_user_reference(value, compatibility)
        if resolved is not None:
            return resolved

        raw_reference = str(value or "").strip()
        if not raw_reference:
            reason = "empty"
        elif compatibility.user_id_mode.value == "numeric_id":
            reason = "legacy_uuid_on_numeric_api"
        elif numeric_panel_user_id(raw_reference) is not None:
            reason = "numeric_id_on_uuid_api"
        else:
            reason = "invalid"
        report_key = (compatibility.version or "unknown", operation)
        if report_key not in self._reported_incompatible_user_references:
            self._reported_incompatible_user_references.add(report_key)
            logger.error(
                "Blocked Panel API operation=%s because the local user reference is "
                "incompatible with Remnawave version=%s generation=%s reason=%s. "
                "Run panel synchronization to relink user identities.",
                operation.value,
                compatibility.version or "unknown",
                compatibility.generation.value,
                reason,
            )
        else:
            logger.debug(
                "Blocked repeated incompatible Panel API user reference operation=%s "
                "version=%s reason=%s.",
                operation.value,
                compatibility.version or "unknown",
                reason,
            )
        return None

    async def panel_compatibility_diagnostics(self) -> dict[str, Any]:
        compatibility = await self.get_panel_api_compatibility()
        capabilities = sorted(capability.value for capability in compatibility.capabilities)
        observed = {
            capability.value: supported
            for capability, supported in sorted(
                self._observed_panel_capabilities.items(),
                key=lambda item: item[0].value,
            )
        }
        return {
            "version": compatibility.version,
            "generation": compatibility.generation.value,
            "support_status": compatibility.support_status,
            "certified_versions": list(compatibility.certified_versions),
            "capabilities": capabilities,
            "observed_capabilities": observed,
        }

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
        self,
        method: str,
        endpoint: str,
        log_full_response: bool = False,
        *,
        operation: PanelApiOperation | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        method_upper = method.upper()
        if operation is not None:
            contract = operation_contract(operation)
            if method_upper != contract.method:
                raise ValueError(
                    f"Panel operation {operation.value} requires {contract.method}, "
                    f"got {method_upper}."
                )
        # Retry safe reads once on transient failures. Some Remnawave analytics
        # endpoints are idempotent POSTs, so method alone is not the safety
        # boundary; the operation contract is.
        contract = operation_contract(operation) if operation is not None else None
        safe_operation = bool(contract and contract.idempotent and not contract.mutation)
        max_attempts = 2 if method_upper in self._SAFE_METHODS or safe_operation else 1
        result: dict[str, Any] | None = None
        for attempt in range(max_attempts):
            result = await self._request_once(
                method,
                endpoint,
                log_full_response,
                operation=operation,
                **kwargs,
            )
            if attempt + 1 < max_attempts and self._is_transient_error(result):
                logger.warning(
                    "Retrying transient Panel API request method=%s endpoint=%s "
                    "attempt=%s/%s status_code=%s",
                    method.upper(),
                    _endpoint_log_label(endpoint, operation),
                    attempt + 1,
                    max_attempts,
                    result.get("status_code") if isinstance(result, dict) else None,
                )
                await asyncio.sleep(self._RETRY_BACKOFF_SECONDS)
                continue
            return result
        return result

    async def _request_once(
        self,
        method: str,
        endpoint: str,
        log_full_response: bool = False,
        *,
        operation: PanelApiOperation | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        if not self.base_url:
            logger.error("Panel API URL (PANEL_API_URL) not configured in settings.")
            return {"error": True, "status_code": 0, "message": "Panel API URL not configured."}

        aiohttp_session = await self._get_session()
        headers = await self._prepare_headers()

        url_for_request = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        endpoint_label = _endpoint_log_label(endpoint, operation)

        json_payload_for_log = (
            kwargs.get("json") if method.upper() in ["POST", "PATCH", "PUT"] else None
        )
        # Never log the raw URL: path/query values can contain Telegram ids,
        # usernames, emails, user ids, or UUIDs. The operation registry label is
        # deliberately identifier-free.
        log_prefix = f"Panel API Req: {method.upper()} {endpoint_label}"
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
                    "metric panel_request_total=1 panel_latency_seconds=%.3f "
                    "panel_response_bytes=%s method=%s endpoint=%s status=%s",
                    time.monotonic() - started,
                    response_length
                    if (response_length := getattr(response, "content_length", None)) is not None
                    else len(response_text),
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
                    if operation is not None:
                        contract = operation_contract(operation)
                        if response_status not in contract.success_statuses:
                            logger.warning(
                                "Remnawave operation=%s returned undocumented success status=%s; "
                                "accepted as 2xx but the API registry needs review.",
                                operation.value,
                                response_status,
                            )
                    # Remnawave 3.x correctly returns an empty body for several
                    # successful DELETE/bulk routes (204 and sometimes 202).
                    # 2.8 normally returned JSON, so preserve JSON handling when
                    # a body exists and synthesize only the no-content success.
                    if not response_text.strip():
                        return {
                            "status": "success",
                            "status_code": response_status,
                            "response": None,
                        }
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
