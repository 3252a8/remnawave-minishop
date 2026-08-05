import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from bot.services.panel_api_compat import (
    PanelApiCompatibility,
    normalize_panel_user,
    normalize_panel_users,
    numeric_panel_user_id,
)
from bot.services.panel_api_contracts import (
    PanelApiCapability,
    PanelApiGeneration,
    PanelApiOperation,
)
from bot.services.panel_api_responses import PanelApiResponseMixin
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from config.traffic_strategy import normalize_traffic_limit_strategy

logger = logging.getLogger(__name__)

# Static endpoint prefixes used as log/metric labels instead of the raw request
# path. Endpoints embed user identifiers (telegram id, username, email, uuids),
# so logging the path verbatim would leak private data into log files; the
# label keeps only the constant prefix. Longest prefixes first so e.g.


def _json_dict(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _json_dict_list(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, dict)]


def _panel_users_batch(value: object) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        return _json_dict_list(value)
    if isinstance(value, dict):
        for key in ("users", "items", "data"):
            batch = _json_dict_list(value.get(key))
            if batch is not None:
                return batch
    return None


def _panel_users_next_cursor(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("nextCursor", "next_cursor"):
        cursor = value.get(key)
        if cursor:
            return str(cursor)
    pagination = value.get("pagination")
    if isinstance(pagination, dict):
        for key in ("nextCursor", "next_cursor"):
            cursor = pagination.get(key)
            if cursor:
                return str(cursor)
    return None


class PanelApiUsersMixin(PanelApiResponseMixin):
    settings: Settings
    _all_users_cache: AsyncTTLCache
    _users_cache: AsyncTTLCache

    if TYPE_CHECKING:

        async def _request(
            self,
            method: str,
            endpoint: str,
            log_full_response: bool = False,
            *,
            operation: PanelApiOperation | None = None,
            **kwargs: Any,
        ) -> dict[str, Any] | None: ...
        async def _invalidate_user_cache(self, user_uuid: str | None) -> None: ...
        async def _invalidate_devices_cache(self, user_uuid: str | None) -> None: ...
        async def _invalidate_all_users_cache(self) -> None: ...
        async def get_user_devices(self, user_uuid: str) -> list[dict[str, Any]] | None: ...
        async def disconnect_device(self, user_uuid: str, hwid: str) -> bool: ...
        async def get_panel_api_compatibility(
            self, *, force_refresh: bool = False
        ) -> PanelApiCompatibility: ...
        def panel_capability_state(
            self,
            capability: PanelApiCapability,
            compatibility: PanelApiCompatibility,
        ) -> bool | None: ...
        def remember_panel_capability(
            self,
            capability: PanelApiCapability,
            supported: bool,
        ) -> None: ...
        def remember_panel_user_count(self, count: int) -> None: ...
        async def panel_mutation_allowed(
            self,
            operation: PanelApiOperation,
            *,
            compatibility: PanelApiCompatibility | None = None,
        ) -> bool: ...
        async def resolve_panel_user_reference(
            self,
            value: object,
            operation: PanelApiOperation,
            *,
            compatibility: PanelApiCompatibility | None = None,
        ) -> str | None: ...

    def _resolve_all_users_page_size(self, page_size: int | None = None) -> int:
        raw_value = (
            page_size
            if page_size is not None
            else getattr(self.settings, "PANEL_ALL_USERS_PAGE_SIZE", 1000)
        )
        try:
            value = int(raw_value or 1000)
        except (TypeError, ValueError):
            value = 1000
        return min(1000, max(1, value))

    def _resolve_all_users_page_delay(self) -> float:
        raw_value = getattr(self.settings, "PANEL_ALL_USERS_PAGE_DELAY_SECONDS", 0.1)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return 0.1
        return value if value > 0 else 0.0

    @staticmethod
    def _panel_user_matches_stream_filters(
        user: dict[str, Any], filters: dict[str, Any] | None
    ) -> bool:
        """Defensively filter results if a 2.8 stream ignores 3.x query fields."""
        if not filters:
            return True
        if "telegramId" in filters:
            return str(user.get("telegramId") or "") == str(filters["telegramId"])
        if "email" in filters:
            return (
                str(user.get("email") or "").strip().casefold()
                == str(filters["email"] or "").strip().casefold()
            )
        return True

    async def get_all_panel_users(
        self, page_size: int | None = None, log_responses: bool = False
    ) -> list[dict[str, Any]] | None:
        resolved_page_size = self._resolve_all_users_page_size(page_size)
        if log_responses or self._all_users_cache.ttl_seconds <= 0:
            users = await self._get_all_panel_users_uncached(
                page_size=resolved_page_size, log_responses=log_responses
            )
        else:
            cached = await self._all_users_cache.get_or_load(
                f"page_size:{resolved_page_size}",
                lambda: self._get_all_panel_users_uncached(
                    page_size=resolved_page_size, log_responses=False
                ),
            )
            users = _json_dict_list(cached)
        if users is not None:
            self.remember_panel_user_count(len(users))
        return users

    async def _get_all_panel_users_uncached(
        self, page_size: int | None = None, log_responses: bool = False
    ) -> list[dict[str, Any]] | None:
        resolved_page_size = self._resolve_all_users_page_size(page_size)
        compatibility = await self.get_panel_api_compatibility()
        stream_supported = self.panel_capability_state(
            PanelApiCapability.USER_STREAM,
            compatibility,
        )
        legacy_users_api_allowed = compatibility.generation is not PanelApiGeneration.RW3_NUMERIC
        users = None
        if stream_supported is not False:
            users = await self._fetch_all_panel_users_stream_pages(
                page_size=resolved_page_size,
                log_responses=log_responses,
                compatibility=compatibility,
            )
        if users is None and legacy_users_api_allowed:
            users = await self._fetch_all_panel_users_pages(
                page_size=resolved_page_size,
                log_responses=log_responses,
            )
        if users is None and resolved_page_size != 100:
            logger.warning(
                "Panel API users fetch failed with page size %s; retrying with page size 100.",
                resolved_page_size,
            )
            users = None
            if stream_supported is not False:
                users = await self._fetch_all_panel_users_stream_pages(
                    page_size=100,
                    log_responses=log_responses,
                    compatibility=compatibility,
                )
            if users is None and legacy_users_api_allowed:
                users = await self._fetch_all_panel_users_pages(
                    page_size=100,
                    log_responses=log_responses,
                )
        return users

    async def _fetch_all_panel_users_stream_pages(
        self,
        page_size: int,
        log_responses: bool = False,
        *,
        compatibility: PanelApiCompatibility,
    ) -> list[dict[str, Any]] | None:
        return await self._fetch_panel_users_stream_pages(
            page_size=page_size,
            log_responses=log_responses,
            compatibility=compatibility,
        )

    async def _fetch_panel_users_stream_pages(
        self,
        page_size: int,
        log_responses: bool = False,
        *,
        filters: dict[str, Any] | None = None,
        compatibility: PanelApiCompatibility,
    ) -> list[dict[str, Any]] | None:
        all_users: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        page_delay = self._resolve_all_users_page_delay()
        while True:
            params: dict[str, Any] = {"size": page_size, **(filters or {})}
            if cursor:
                params["cursor"] = cursor
            response_data = await self._request(
                "GET",
                "/users/stream",
                operation=PanelApiOperation.USERS_STREAM,
                params=params,
                log_full_response=log_responses,
            )

            if not response_data or response_data.get("error"):
                legacy_stream_probe = compatibility.generation is not PanelApiGeneration.RW3_NUMERIC
                if legacy_stream_probe and (
                    self._is_missing_endpoint_response(response_data)
                    or (isinstance(response_data, dict) and response_data.get("status_code") == 400)
                ):
                    self.remember_panel_capability(PanelApiCapability.USER_STREAM, False)
                    if filters:
                        self.remember_panel_capability(
                            PanelApiCapability.USER_STREAM_FILTERS,
                            False,
                        )
                if legacy_stream_probe:
                    logger.info(
                        "Panel API users stream fetch is unavailable; a legacy lookup may be "
                        "used. Response: %s",
                        response_data,
                    )
                else:
                    logger.error(
                        "Panel API users stream failed for a known 3.x panel; refusing the "
                        "legacy /users fallback. Response: %s",
                        response_data,
                    )
                return None
            response = response_data.get("response")
            users_batch = _panel_users_batch(response)
            if users_batch is None:
                logger.warning(
                    "Panel API users stream returned an unsupported response shape: %s",
                    response_data,
                )
                self.remember_panel_capability(PanelApiCapability.USER_STREAM, False)
                return None
            if not users_batch:
                break
            all_users.extend(
                user
                for user in normalize_panel_users(users_batch)
                if self._panel_user_matches_stream_filters(user, filters)
            )
            next_cursor = _panel_users_next_cursor(response)
            if not next_cursor:
                break
            if next_cursor in seen_cursors:
                logger.warning("Panel API users stream returned a repeated cursor; stopping.")
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            if page_delay:
                await asyncio.sleep(page_delay)
        logger.info("Fetched %s users from panel API stream.", len(all_users))
        self.remember_panel_capability(PanelApiCapability.USER_STREAM, True)
        if filters:
            self.remember_panel_capability(PanelApiCapability.USER_STREAM_FILTERS, True)
        return all_users

    async def _fetch_all_panel_users_pages(
        self, page_size: int, log_responses: bool = False
    ) -> list[dict[str, Any]] | None:
        all_users: list[dict[str, Any]] = []
        start_offset = 0
        page_delay = self._resolve_all_users_page_delay()
        while True:
            params = {"size": page_size, "start": start_offset}
            response_data = await self._request(
                "GET",
                "/users",
                operation=PanelApiOperation.USERS_LIST,
                params=params,
                log_full_response=log_responses,
            )

            if not response_data or response_data.get("error"):
                logger.error(
                    "Failed to fetch panel users batch (start: %s). Response: %s",
                    start_offset,
                    response_data,
                )
                return None
            response = response_data.get("response")
            users_batch = _panel_users_batch(response)
            if users_batch is None:
                logger.error(
                    "Panel API users endpoint returned an unsupported response shape "
                    "(start: %s). Response: %s",
                    start_offset,
                    response_data,
                )
                return None
            if not users_batch:
                break
            all_users.extend(normalize_panel_users(users_batch))
            if len(users_batch) < page_size:
                break
            start_offset += page_size
            if page_delay:
                await asyncio.sleep(page_delay)
        logger.info("Fetched %s users from panel API.", len(all_users))
        return all_users

    async def get_user_by_uuid(
        self,
        user_uuid: str,
        log_response: bool = False,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any] | None:
        if not use_cache or log_response or self._users_cache.ttl_seconds <= 0:
            return await self._get_user_by_uuid_uncached(user_uuid, log_response=log_response)
        cached = await self._users_cache.get_or_load(
            f"uuid:{user_uuid}",
            lambda: self._get_user_by_uuid_uncached(user_uuid, log_response=False),
        )
        return _json_dict(cached)

    async def _get_user_by_uuid_uncached(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any] | None:
        lookup = await self.get_user_by_uuid_lookup(user_uuid, log_response=log_response)
        user = lookup.get("user")
        if lookup.get("ok") and isinstance(user, dict):
            return user
        return None

    async def get_user_by_uuid_lookup(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any]:
        """Fetch a panel user and preserve whether a miss was confirmed.

        ``get_user_by_uuid`` historically returned ``None`` both for a real
        404/not-found and for transient panel/API failures. Callers that may
        mutate local state need this richer result to avoid treating an outage
        as a deleted panel user.
        """
        compatibility = await self.get_panel_api_compatibility()
        user_reference = await self.resolve_panel_user_reference(
            user_uuid,
            PanelApiOperation.USER_GET,
            compatibility=compatibility,
        )
        if user_reference is None:
            return {
                "ok": False,
                "user": None,
                "not_found": False,
                "failure_reason": (
                    "classification=incompatible_user_reference "
                    f"generation={compatibility.generation.value} "
                    "action=panel_sync_required"
                ),
                "response": None,
            }
        endpoint = f"/users/{user_reference}"
        full_response = await self._request(
            "GET",
            endpoint,
            operation=PanelApiOperation.USER_GET,
            log_full_response=log_response,
        )
        if full_response and not full_response.get("error") and "response" in full_response:
            user = normalize_panel_user(full_response.get("response"))
            return {
                "ok": True,
                "user": user,
                "not_found": False,
                "failure_reason": None,
                "response": full_response,
            }

        not_found = self._is_user_not_found_response(full_response)
        return {
            "ok": False,
            "user": None,
            "not_found": not_found,
            "failure_reason": self._describe_user_lookup_failure(
                full_response,
                not_found=not_found,
            ),
            "response": full_response,
        }

    async def get_user(
        self,
        *,
        uuid: str | None = None,
        telegram_id: int | None = None,
        username: str | None = None,
        email: str | None = None,
        log_response: bool = False,
    ) -> dict[str, Any] | None:
        if uuid:
            return await self.get_user_by_uuid(uuid, log_response=log_response)

        users = await self.get_users_by_filter(
            telegram_id=telegram_id,
            username=username,
            email=email,
            log_response=log_response,
        )
        if users:
            return users[0]
        return None

    async def get_users_by_filter(
        self,
        telegram_id: int | None = None,
        username: str | None = None,
        email: str | None = None,
        log_response: bool = False,
    ) -> list[dict[str, Any]] | None:
        response_data = None
        filter_used_log = "No filter specified"

        if telegram_id is not None:
            filter_used_log = f"telegramId={telegram_id}"
            compatibility = await self.get_panel_api_compatibility()
            stream_filters = self.panel_capability_state(
                PanelApiCapability.USER_STREAM_FILTERS,
                compatibility,
            )
            if stream_filters is True or compatibility.unreviewed_generation:
                return await self._fetch_panel_users_stream_pages(
                    page_size=1000,
                    log_responses=log_response,
                    filters={"telegramId": telegram_id},
                    compatibility=compatibility,
                )
            endpoint = f"/users/by-telegram-id/{telegram_id}"
            response_data = await self._request(
                "GET",
                endpoint,
                operation=PanelApiOperation.USER_LOOKUP_TELEGRAM,
                log_full_response=log_response,
            )

            if (
                response_data
                and not response_data.get("error")
                and "response" in response_data
                and isinstance(response_data["response"], list)
            ):
                self.remember_panel_capability(PanelApiCapability.USER_STREAM_FILTERS, False)
                return normalize_panel_users(response_data["response"])
            if self._is_missing_endpoint_response(response_data):
                # React immediately when the panel was upgraded without
                # restarting Mini Shop; the regular metadata cache also
                # expires periodically for upgrade/downgrade detection.
                refreshed = await self.get_panel_api_compatibility(force_refresh=True)
                return await self._fetch_panel_users_stream_pages(
                    page_size=1000,
                    log_responses=log_response,
                    filters={"telegramId": telegram_id},
                    compatibility=refreshed,
                )
            if self._is_user_not_found_response(response_data):
                logger.info("Panel API: Users not found for %s", filter_used_log)
                return []

        elif username is not None:
            filter_used_log = "username (redacted)"
            endpoint = f"/users/by-username/{username}"
            response_data = await self._request(
                "GET",
                endpoint,
                operation=PanelApiOperation.USER_LOOKUP_USERNAME,
                log_full_response=log_response,
            )

            if (
                response_data
                and not response_data.get("error")
                and "response" in response_data
                and isinstance(response_data["response"], dict)
            ):
                user = normalize_panel_user(response_data["response"])
                return [user] if user else []
            elif self._is_user_not_found_response(response_data):
                logger.info("Panel API: User not found for %s", filter_used_log)
                return []

        elif email is not None:
            filter_used_log = "email (redacted)"
            compatibility = await self.get_panel_api_compatibility()
            stream_filters = self.panel_capability_state(
                PanelApiCapability.USER_STREAM_FILTERS,
                compatibility,
            )
            if stream_filters is True or compatibility.unreviewed_generation:
                return await self._fetch_panel_users_stream_pages(
                    page_size=1000,
                    log_responses=log_response,
                    filters={"email": email},
                    compatibility=compatibility,
                )
            endpoint = f"/users/by-email/{email}"
            response_data = await self._request(
                "GET",
                endpoint,
                operation=PanelApiOperation.USER_LOOKUP_EMAIL,
                log_full_response=log_response,
            )

            if (
                response_data
                and not response_data.get("error")
                and "response" in response_data
                and isinstance(response_data["response"], list)
            ):
                self.remember_panel_capability(PanelApiCapability.USER_STREAM_FILTERS, False)
                return normalize_panel_users(response_data["response"])
            if self._is_missing_endpoint_response(response_data):
                refreshed = await self.get_panel_api_compatibility(force_refresh=True)
                return await self._fetch_panel_users_stream_pages(
                    page_size=1000,
                    log_responses=log_response,
                    filters={"email": email},
                    compatibility=refreshed,
                )
            if self._is_user_not_found_response(response_data):
                logger.info("Panel API: Users not found for %s", filter_used_log)
                return []

        if not telegram_id and not username and not email:
            logger.warning("get_users_by_filter called without any specific filter criteria.")
            return []

        logger.error(
            "Failed to fetch panel users with filter (%s); panel response redacted.",
            filter_used_log,
        )
        return None

    async def create_panel_user(
        self,
        username_on_panel: str,
        telegram_id: int | None = None,
        email: str | None = None,
        default_expire_days: int = 1,
        expire_at: datetime | None = None,
        default_traffic_limit_bytes: int = 0,
        default_traffic_limit_strategy: str = "NO_RESET",
        hwid_device_limit: int | None = None,
        specific_squad_uuids: list[str] | None = None,
        external_squad_uuid: str | None = None,
        description: str | None = None,
        tag: str | None = None,
        status: str = "ACTIVE",
        log_response: bool = False,
    ) -> dict[str, Any] | None:

        if not await self.panel_mutation_allowed(PanelApiOperation.USER_CREATE):
            return None

        username_is_valid = (
            3 <= len(username_on_panel) <= 36
            and re.match(r"^[A-Za-z0-9_-]+$", username_on_panel) is not None
        )
        if not username_is_valid:
            msg = f"Panel username '{username_on_panel}' does not meet panel requirements."
            logger.error(msg)
            return {
                "error": True,
                "status_code": 400,
                "message": msg,
                "errorCode": "VALIDATION_ERROR_USERNAME",
            }

        now = datetime.now(UTC)
        expire_at_dt = expire_at or now + timedelta(days=default_expire_days)
        if expire_at_dt.tzinfo is None:
            expire_at_dt = expire_at_dt.replace(tzinfo=UTC)
        else:
            expire_at_dt = expire_at_dt.astimezone(UTC)
        expire_at_iso = expire_at_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        payload: dict[str, Any] = {
            "username": username_on_panel,
            "status": status.upper(),
            "expireAt": expire_at_iso,
            "trafficLimitStrategy": normalize_traffic_limit_strategy(
                default_traffic_limit_strategy
            ),
            "trafficLimitBytes": default_traffic_limit_bytes,
        }
        hwid_limit_value = hwid_device_limit
        if hwid_limit_value is None:
            hwid_limit_value = self.settings.USER_HWID_DEVICE_LIMIT
        if hwid_limit_value is not None:
            try:
                hwid_limit_int = int(hwid_limit_value)
                if hwid_limit_int >= 0:
                    payload["hwidDeviceLimit"] = hwid_limit_int
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring invalid HWID device limit '%s' while creating panel user '%s'.",
                    hwid_limit_value,
                    username_on_panel,
                )
        if specific_squad_uuids:
            payload["activeInternalSquads"] = specific_squad_uuids
        if external_squad_uuid:
            payload["externalSquadUuid"] = external_squad_uuid
        if telegram_id is not None:
            payload["telegramId"] = telegram_id
        if email:
            payload["email"] = email
        if description:
            payload["description"] = description
        if tag:
            payload["tag"] = tag

        response = await self._request(
            "POST",
            "/users",
            operation=PanelApiOperation.USER_CREATE,
            json=payload,
            log_full_response=log_response,
        )
        if response and not response.get("error") and "response" in response:
            panel_user = normalize_panel_user(response.get("response"))
            if panel_user is not None:
                response = {**response, "response": panel_user}
            await self._invalidate_all_users_cache()
            logger.info(
                "Panel user '%s' created successfully (identifier: %s).",
                username_on_panel,
                response.get("response", {}).get("uuid"),
            )
            return response

        logger.error(
            "Failed to create panel user '%s'. Payload: %s, Response: %s",
            username_on_panel,
            payload,
            response if not log_response else "(full response logged above)",
        )
        return response

    async def update_user_details_on_panel(
        self, user_uuid: str, update_payload: dict[str, Any], log_response: bool = False
    ) -> dict[str, Any] | None:
        compatibility = await self.get_panel_api_compatibility()
        if not await self.panel_mutation_allowed(
            PanelApiOperation.USER_UPDATE,
            compatibility=compatibility,
        ):
            return None
        user_reference = await self.resolve_panel_user_reference(
            user_uuid,
            PanelApiOperation.USER_UPDATE,
            compatibility=compatibility,
        )
        if user_reference is None:
            return None
        # The service argument and local DB field keep their historical name,
        # but contain a decimal user id after a Remnawave 3.x sync.
        payload = dict(update_payload)
        numeric_id = numeric_panel_user_id(user_reference)
        if numeric_id is not None:
            payload.pop("uuid", None)
            payload["id"] = numeric_id
        else:
            payload.pop("id", None)
            payload["uuid"] = user_reference
        if "trafficLimitStrategy" in payload:
            payload["trafficLimitStrategy"] = normalize_traffic_limit_strategy(
                payload.get("trafficLimitStrategy")
            )

        full_response = await self._request(
            "PATCH",
            "/users",
            operation=PanelApiOperation.USER_UPDATE,
            json=payload,
            log_full_response=log_response,
        )
        if full_response and not full_response.get("error"):
            await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            updated = normalize_panel_user(full_response.get("response"))
            if updated is None and full_response.get("status_code") in {202, 204}:
                # Remnawave 3.x may acknowledge PATCH with no response body.
                # Re-read the user so callers retain the historical return contract.
                updated = await self.get_user_by_uuid(
                    user_uuid,
                    log_response=log_response,
                    use_cache=False,
                )
            if updated is not None:
                logger.debug("User %s details updated on panel.", user_uuid)
                return updated

        logger.error(
            "Failed to update user %s details on panel. Payload: %s, Response: %s",
            user_uuid,
            payload,
            full_response if not log_response else "(logged above)",
        )
        return None

    async def update_user_status_on_panel(
        self, user_uuid: str, enable: bool, log_response: bool = False
    ) -> bool:
        compatibility = await self.get_panel_api_compatibility()
        if not await self.panel_mutation_allowed(
            PanelApiOperation.USER_STATUS,
            compatibility=compatibility,
        ):
            return False
        user_reference = await self.resolve_panel_user_reference(
            user_uuid,
            PanelApiOperation.USER_STATUS,
            compatibility=compatibility,
        )
        if user_reference is None:
            return False
        action = "enable" if enable else "disable"
        endpoint = f"/users/{user_reference}/actions/{action}"
        response_data = await self._request(
            "POST",
            endpoint,
            operation=PanelApiOperation.USER_STATUS,
            log_full_response=log_response,
        )

        if response_data and not response_data.get("error"):
            await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            response_user = normalize_panel_user(response_data.get("response"))
            if response_user is None and response_data.get("status_code") in {202, 204}:
                response_user = await self.get_user_by_uuid(
                    user_uuid,
                    log_response=log_response,
                    use_cache=False,
                )
            actual_status = response_user.get("status") if response_user else None
            expected_status = "ACTIVE" if enable else "DISABLED"
            if actual_status == expected_status:
                logger.info(
                    "User %s status on panel successfully set to %s (Actual: %s).",
                    user_uuid,
                    action,
                    actual_status,
                )
                return True
            else:
                logger.warning(
                    "User %s status on panel action '%s' called, but final status is '%s'.",
                    user_uuid,
                    action,
                    actual_status,
                )
                return False

        logger.error(
            "Failed to %s user %s on panel. Response: %s",
            action,
            user_uuid,
            response_data if not log_response else "(logged above)",
        )
        return False

    async def delete_user_from_panel(self, user_uuid: str, log_response: bool = False) -> bool:
        """Delete a user from the panel. Treat not-found as already deleted."""
        compatibility = await self.get_panel_api_compatibility()
        if not await self.panel_mutation_allowed(
            PanelApiOperation.USER_DELETE,
            compatibility=compatibility,
        ):
            return False
        user_reference = await self.resolve_panel_user_reference(
            user_uuid,
            PanelApiOperation.USER_DELETE,
            compatibility=compatibility,
        )
        if user_reference is None:
            return False
        endpoint = f"/users/{user_reference}"
        response_data = await self._request(
            "DELETE",
            endpoint,
            operation=PanelApiOperation.USER_DELETE,
            log_full_response=log_response,
        )

        if not response_data:
            logger.error(
                "Panel API delete_user_from_panel returned no data for user %s.", user_uuid
            )
            return False

        if response_data.get("error"):
            error_code = self._panel_response_error_code(response_data)
            if self._is_user_not_found_response(response_data):
                logger.info(
                    "Panel user %s already absent (errorCode %s). Treating as deleted.",
                    user_uuid,
                    error_code or "status_404",
                )
                await self._invalidate_user_cache(user_uuid)
                await self._invalidate_devices_cache(user_uuid)
                await self._invalidate_all_users_cache()
                return True
            logger.error(
                "Failed to delete user %s on panel. Response: %s", user_uuid, response_data
            )
            return False

        logger.info("Panel user %s deleted successfully.", user_uuid)
        await self._invalidate_user_cache(user_uuid)
        await self._invalidate_devices_cache(user_uuid)
        await self._invalidate_all_users_cache()
        return True

    async def revoke_user_subscription(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any] | None:
        """Revoke the user's subscription on the panel.

        Registered HWID devices are removed first, then the panel regenerates
        the user's short UUID. This keeps the new link usable even when the
        previous link had already filled the device limit. Returns the updated
        panel user (including the new ``subscriptionUrl``) or ``None`` on
        failure.
        """
        compatibility = await self.get_panel_api_compatibility()
        if not await self.panel_mutation_allowed(
            PanelApiOperation.USER_REVOKE,
            compatibility=compatibility,
        ):
            return None
        user_reference = await self.resolve_panel_user_reference(
            user_uuid,
            PanelApiOperation.USER_REVOKE,
            compatibility=compatibility,
        )
        if user_reference is None:
            return None
        if not await self._disconnect_all_hwid_devices(user_uuid):
            return None
        endpoint = f"/users/{user_reference}/actions/revoke"
        full_response = await self._request(
            "POST",
            endpoint,
            operation=PanelApiOperation.USER_REVOKE,
            log_full_response=log_response,
        )

        if full_response and not full_response.get("error"):
            await self._invalidate_user_cache(user_uuid)
            await self._invalidate_devices_cache(user_uuid)
            await self._invalidate_all_users_cache()
            updated = normalize_panel_user(full_response.get("response"))
            if updated is None and full_response.get("status_code") in {202, 204}:
                updated = await self.get_user_by_uuid(
                    user_uuid,
                    log_response=log_response,
                    use_cache=False,
                )
            if updated is not None:
                logger.info("User %s subscription revoked on panel.", user_uuid)
                return updated

        logger.error(
            "Failed to revoke subscription for user %s on panel. Response: %s",
            user_uuid,
            full_response if not log_response else "(logged above)",
        )
        return None

    async def _disconnect_all_hwid_devices(self, user_uuid: str) -> bool:
        await self._invalidate_devices_cache(user_uuid)
        devices = await self.get_user_devices(user_uuid)
        if devices is None:
            logger.error(
                "Cannot revoke subscription for user %s: failed to read registered devices.",
                user_uuid,
            )
            return False

        hwids: list[str] = []
        seen: set[str] = set()
        for device in devices:
            hwid = str(device.get("hwid") or "").strip()
            if not hwid:
                logger.error(
                    "Cannot revoke subscription for user %s: panel returned a device "
                    "without an HWID.",
                    user_uuid,
                )
                return False
            if hwid not in seen:
                seen.add(hwid)
                hwids.append(hwid)

        for hwid in hwids:
            if not await self.disconnect_device(user_uuid, hwid):
                logger.error(
                    "Cannot revoke subscription for user %s: failed to clear all "
                    "registered devices.",
                    user_uuid,
                )
                return False

        return True
