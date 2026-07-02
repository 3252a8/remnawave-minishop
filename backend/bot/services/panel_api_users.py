import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

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


class PanelApiUsersMixin:
    settings: Settings
    _all_users_cache: AsyncTTLCache
    _users_cache: AsyncTTLCache

    if TYPE_CHECKING:

        async def _request(
            self, method: str, endpoint: str, log_full_response: bool = False, **kwargs: Any
        ) -> dict[str, Any] | None: ...
        async def _invalidate_user_cache(self, user_uuid: str) -> None: ...
        async def _invalidate_devices_cache(self, user_uuid: str) -> None: ...
        async def _invalidate_all_users_cache(self) -> None: ...

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

    async def get_all_panel_users(
        self, page_size: int | None = None, log_responses: bool = False
    ) -> list[dict[str, Any]] | None:
        resolved_page_size = self._resolve_all_users_page_size(page_size)
        if log_responses or self._all_users_cache.ttl_seconds <= 0:
            return await self._get_all_panel_users_uncached(
                page_size=resolved_page_size, log_responses=log_responses
            )
        cached = await self._all_users_cache.get_or_load(
            f"page_size:{resolved_page_size}",
            lambda: self._get_all_panel_users_uncached(
                page_size=resolved_page_size, log_responses=False
            ),
        )
        return _json_dict_list(cached)

    async def _get_all_panel_users_uncached(
        self, page_size: int | None = None, log_responses: bool = False
    ) -> list[dict[str, Any]] | None:
        resolved_page_size = self._resolve_all_users_page_size(page_size)
        users = await self._fetch_all_panel_users_stream_pages(
            page_size=resolved_page_size,
            log_responses=log_responses,
        )
        if users is None:
            users = await self._fetch_all_panel_users_pages(
                page_size=resolved_page_size,
                log_responses=log_responses,
            )
        if users is None and resolved_page_size != 100:
            logger.warning(
                "Panel API users fetch failed with page size %s; retrying with page size 100.",
                resolved_page_size,
            )
            users = await self._fetch_all_panel_users_stream_pages(
                page_size=100,
                log_responses=log_responses,
            )
            if users is None:
                users = await self._fetch_all_panel_users_pages(
                    page_size=100,
                    log_responses=log_responses,
                )
        return users

    async def _fetch_all_panel_users_stream_pages(
        self, page_size: int, log_responses: bool = False
    ) -> list[dict[str, Any]] | None:
        all_users: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        page_delay = self._resolve_all_users_page_delay()
        while True:
            params: dict[str, Any] = {"size": page_size}
            if cursor:
                params["cursor"] = cursor
            response_data = await self._request(
                "GET", "/users/stream", params=params, log_full_response=log_responses
            )

            if not response_data or response_data.get("error"):
                logger.info(
                    "Panel API users stream fetch is unavailable; falling back to legacy "
                    "/users pagination. Response: %s",
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
                return None
            if not users_batch:
                break
            all_users.extend(users_batch)
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
                "GET", "/users", params=params, log_full_response=log_responses
            )

            if not response_data or response_data.get("error"):
                logger.error(
                    "Failed to fetch panel users batch (start: %s). Response: %s",
                    start_offset,
                    response_data,
                )
                return None
            response = response_data.get("response")
            users_batch = _panel_users_batch(response) or []
            if not users_batch:
                break
            all_users.extend(users_batch)
            if len(users_batch) < page_size:
                break
            start_offset += page_size
            if page_delay:
                await asyncio.sleep(page_delay)
        logger.info("Fetched %s users from panel API.", len(all_users))
        return all_users

    async def get_user_by_uuid(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any] | None:
        if log_response or self._users_cache.ttl_seconds <= 0:
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

    @staticmethod
    def _panel_response_details(response_data: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(response_data, dict):
            return {}
        details = response_data.get("details")
        return details if isinstance(details, dict) else {}

    @classmethod
    def _panel_response_error_code(cls, response_data: dict[str, Any] | None) -> str | None:
        if not isinstance(response_data, dict):
            return None
        details = cls._panel_response_details(response_data)
        error_code = (
            response_data.get("errorCode")
            or response_data.get("code")
            or details.get("errorCode")
            or details.get("code")
        )
        return str(error_code) if error_code else None

    @classmethod
    def _panel_response_message(cls, response_data: dict[str, Any] | None) -> str | None:
        if not isinstance(response_data, dict):
            return None
        details = cls._panel_response_details(response_data)
        message = (
            response_data.get("message")
            or details.get("message")
            or details.get("error")
            or details.get("raw_response_text")
        )
        if message is None:
            return None
        message = str(message).replace("\n", " ").strip()
        return message[:500] if message else None

    @classmethod
    def _is_user_not_found_response(cls, response_data: dict[str, Any] | None) -> bool:
        if not isinstance(response_data, dict):
            return False
        status_code = response_data.get("status_code")
        error_code = cls._panel_response_error_code(response_data)
        if error_code in {"A040", "A062", "USER_NOT_FOUND", "NOT_FOUND"}:
            return True
        return status_code == 404

    @classmethod
    def _describe_user_lookup_failure(
        cls,
        response_data: dict[str, Any] | None,
        *,
        not_found: bool,
    ) -> str:
        if not isinstance(response_data, dict):
            return "classification=panel_lookup_failed response=empty"

        classification = "confirmed_not_found" if not_found else "panel_lookup_failed"
        parts = [f"classification={classification}"]
        status_code = response_data.get("status_code")
        if status_code is not None:
            parts.append(f"status_code={status_code}")
        error_code = cls._panel_response_error_code(response_data)
        if error_code:
            parts.append(f"error_code={error_code}")
        message = cls._panel_response_message(response_data)
        if message:
            parts.append(f"message={message}")
        return " ".join(parts)

    async def get_user_by_uuid_lookup(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any]:
        """Fetch a panel user and preserve whether a miss was confirmed.

        ``get_user_by_uuid`` historically returned ``None`` both for a real
        404/not-found and for transient panel/API failures. Callers that may
        mutate local state need this richer result to avoid treating an outage
        as a deleted panel user.
        """
        endpoint = f"/users/{user_uuid}"
        full_response = await self._request("GET", endpoint, log_full_response=log_response)
        if full_response and not full_response.get("error") and "response" in full_response:
            return {
                "ok": True,
                "user": _json_dict(full_response.get("response")),
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
            endpoint = f"/users/by-telegram-id/{telegram_id}"
            response_data = await self._request("GET", endpoint, log_full_response=log_response)

            if (
                response_data
                and not response_data.get("error")
                and "response" in response_data
                and isinstance(response_data["response"], list)
            ):
                return response_data["response"]
            elif response_data and response_data.get("errorCode") == "A062":
                logger.info("Panel API: Users not found for %s", filter_used_log)
                return []

        elif username is not None:
            filter_used_log = "username (redacted)"
            endpoint = f"/users/by-username/{username}"
            response_data = await self._request("GET", endpoint, log_full_response=log_response)

            if (
                response_data
                and not response_data.get("error")
                and "response" in response_data
                and isinstance(response_data["response"], dict)
            ):
                return [response_data["response"]]
            elif response_data and response_data.get("errorCode") == "A062":
                logger.info("Panel API: User not found for %s", filter_used_log)
                return []

        elif email is not None:
            filter_used_log = "email (redacted)"
            endpoint = f"/users/by-email/{email}"
            response_data = await self._request("GET", endpoint, log_full_response=log_response)

            if (
                response_data
                and not response_data.get("error")
                and "response" in response_data
                and isinstance(response_data["response"], list)
            ):
                return response_data["response"]
            elif response_data and response_data.get("errorCode") == "A062":
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
        expire_at_dt = now + timedelta(days=default_expire_days)
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
            "POST", "/users", json=payload, log_full_response=log_response
        )
        if response and not response.get("error") and "response" in response:
            await self._invalidate_all_users_cache()
            logger.info(
                "Panel user '%s' created successfully (UUID: %s).",
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
        if "uuid" not in update_payload:
            update_payload["uuid"] = user_uuid
        if "trafficLimitStrategy" in update_payload:
            update_payload["trafficLimitStrategy"] = normalize_traffic_limit_strategy(
                update_payload.get("trafficLimitStrategy")
            )

        full_response = await self._request(
            "PATCH", "/users", json=update_payload, log_full_response=log_response
        )
        if full_response and not full_response.get("error") and "response" in full_response:
            logger.debug("User %s details updated on panel.", user_uuid)
            await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            return _json_dict(full_response.get("response"))

        logger.error(
            "Failed to update user %s details on panel. Payload: %s, Response: %s",
            user_uuid,
            update_payload,
            full_response if not log_response else "(logged above)",
        )
        return None

    async def update_user_status_on_panel(
        self, user_uuid: str, enable: bool, log_response: bool = False
    ) -> bool:
        action = "enable" if enable else "disable"
        endpoint = f"/users/{user_uuid}/actions/{action}"
        response_data = await self._request("POST", endpoint, log_full_response=log_response)

        if response_data and not response_data.get("error") and "response" in response_data:
            await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            actual_status = response_data.get("response", {}).get("status")
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
        endpoint = f"/users/{user_uuid}"
        response_data = await self._request("DELETE", endpoint, log_full_response=log_response)

        if not response_data:
            logger.error(
                "Panel API delete_user_from_panel returned no data for user %s.", user_uuid
            )
            return False

        if response_data.get("error"):
            details = response_data.get("details") or {}
            error_code = details.get("errorCode") or response_data.get("errorCode")
            if error_code in {"A062", "A040"}:
                logger.info(
                    "Panel user %s already absent (errorCode %s). Treating as deleted.",
                    user_uuid,
                    error_code,
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
