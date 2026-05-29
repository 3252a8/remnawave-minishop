import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from db.dal import panel_sync_dal
from db.models import PanelSyncStatus


class PanelApiService:
    # Status codes returned by _request_once for failures we consider transient
    # (connect error, request timeout) and therefore worth retrying on safe methods.
    _TRANSIENT_STATUS_CODES = (-1, -3)
    _SAFE_METHODS = frozenset({"GET", "HEAD"})
    _RETRY_BACKOFF_SECONDS = 0.5

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.PANEL_API_URL
        self.api_key = settings.PANEL_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None
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
            ttl_seconds=max(0, int(getattr(settings, "PANEL_USER_CACHE_TTL_SECONDS", 5) or 0)),
            settings=settings,
            namespace="panel:users",
        )
        self._devices_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=max(0, int(getattr(settings, "PANEL_DEVICES_CACHE_TTL_SECONDS", 5) or 0)),
            settings=settings,
            namespace="panel:devices",
        )
        self._all_users_cache: AsyncTTLCache = AsyncTTLCache(
            ttl_seconds=max(
                0,
                int(getattr(settings, "PANEL_ALL_USERS_CACHE_TTL_SECONDS", 5) or 0),
            ),
            settings=settings,
            namespace="panel:all_users",
        )

    async def __aenter__(self):
        """Context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically close session"""
        await self.close_session()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Separate connect/read timeouts so a stuck panel does not hold a
            # bot worker for the full window; total caps worst-case latency.
            timeout = aiohttp.ClientTimeout(
                total=15,
                connect=3,
                sock_connect=3,
                sock_read=10,
            )
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logging.debug("Panel API service HTTP session closed.")

    async def close(self):
        """Alias for close_session for API consistency."""
        await self.close_session()

    async def _prepare_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": self.default_client_ip,
            "X-Real-IP": self.default_client_ip,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _is_transient_error(self, result: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(result, dict) or not result.get("error"):
            return False
        code = result.get("status_code")
        if code in self._TRANSIENT_STATUS_CODES:
            return True
        return isinstance(code, int) and 500 <= code < 600

    async def _request(
        self, method: str, endpoint: str, log_full_response: bool = False, **kwargs
    ) -> Optional[Dict[str, Any]]:
        # Retry safe (idempotent) methods once on transient failures to absorb
        # network blips and short panel restarts without surfacing errors.
        max_attempts = 2 if method.upper() in self._SAFE_METHODS else 1
        result: Optional[Dict[str, Any]] = None
        for attempt in range(max_attempts):
            result = await self._request_once(method, endpoint, log_full_response, **kwargs)
            if attempt + 1 < max_attempts and self._is_transient_error(result):
                await asyncio.sleep(self._RETRY_BACKOFF_SECONDS)
                continue
            return result
        return result

    async def _request_once(
        self, method: str, endpoint: str, log_full_response: bool = False, **kwargs
    ) -> Optional[Dict[str, Any]]:
        if not self.base_url:
            logging.error("Panel API URL (PANEL_API_URL) not configured in settings.")
            return {"error": True, "status_code": 0, "message": "Panel API URL not configured."}

        aiohttp_session = await self._get_session()
        headers = await self._prepare_headers()

        url_for_request = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        current_params = kwargs.get("params")
        url_with_params_for_log = url_for_request
        if current_params:
            try:
                url_with_params_for_log += "?" + urlencode(current_params)
            except Exception:
                pass

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
        try:
            started = time.monotonic()
            async with aiohttp_session.request(
                method.upper(), url_for_request, headers=headers, **kwargs
            ) as response:
                response_status = response.status
                response_text = await response.text()
                logging.info(
                    "metric panel_latency_seconds=%.3f method=%s endpoint=%s status=%s",
                    time.monotonic() - started,
                    method.upper(),
                    endpoint,
                    response_status,
                )

                log_suffix = f"| Status: {response_status}"

                if log_full_response or not (200 <= response_status < 300):
                    try:
                        parsed_json_for_log = json.loads(response_text)
                        pretty_response_text = json.dumps(
                            parsed_json_for_log, indent=2, ensure_ascii=False
                        )
                        logging.info(
                            f"{log_prefix} {log_suffix} | Full Response Body:\n{pretty_response_text}"  # noqa: E501
                        )
                    except json.JSONDecodeError:
                        logging.info(
                            f"{log_prefix} {log_suffix} | Full Response Text (not JSON):\n{response_text[:2000]}{'...' if len(response_text) > 2000 else ''}"  # noqa: E501
                        )
                else:
                    logging.debug(
                        f"{log_prefix} {log_suffix} | OK. Response Body Preview: {response_text[:200]}{'...' if len(response_text) > 200 else ''}"  # noqa: E501
                    )

                if 200 <= response_status < 300:
                    try:
                        if "application/json" in response.headers.get("Content-Type", "").lower():
                            data = json.loads(response_text)
                            return data
                        else:
                            return {
                                "status": "success",
                                "code": response_status,
                                "data_text": response_text,
                            }
                    except json.JSONDecodeError as e_json_ok:
                        logging.error(
                            f"{log_prefix} {log_suffix} | OK but JSON Parse Error. Error: {e_json_ok}. Body was logged above."  # noqa: E501
                        )
                        return {
                            "status": "success_parse_error",
                            "code": response_status,
                            "data_text": response_text,
                            "parse_error": str(e_json_ok),
                        }
                else:
                    error_details = {
                        "message": f"Request failed with status {response_status}",
                        "raw_response_text": response_text,
                    }
                    try:
                        if "application/json" in response.headers.get("Content-Type", "").lower():
                            error_json_data = json.loads(response_text)
                            error_details.update(error_json_data)
                    except json.JSONDecodeError:
                        pass
                    return {"error": True, "status_code": response_status, "details": error_details}

        except aiohttp.ClientConnectorError as e:
            logging.error(f"Panel API ClientConnectorError to {url_for_request}: {e}")
            return {"error": True, "status_code": -1, "message": f"Connection error: {str(e)}"}
        except aiohttp.ClientError as e:
            logging.exception("Panel API ClientError to %s.", url_for_request)
            return {"error": True, "status_code": -2, "message": f"Client error: {str(e)}"}
        except asyncio.TimeoutError:
            logging.error(f"Panel API request to {url_for_request} timed out.")
            return {"error": True, "status_code": -3, "message": "Request timed out"}
        except Exception as e:
            logging.error(
                f"Unexpected Panel API request error to {url_for_request}: {e}", exc_info=True
            )
            return {"error": True, "status_code": -4, "message": f"Unexpected error: {str(e)}"}

    def _resolve_all_users_page_size(self, page_size: Optional[int] = None) -> int:
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

    async def get_all_panel_users(
        self, page_size: Optional[int] = None, log_responses: bool = False
    ) -> Optional[List[Dict[str, Any]]]:
        resolved_page_size = self._resolve_all_users_page_size(page_size)
        if log_responses or self._all_users_cache.ttl_seconds <= 0:
            return await self._get_all_panel_users_uncached(
                page_size=resolved_page_size, log_responses=log_responses
            )
        return await self._all_users_cache.get_or_load(
            f"page_size:{resolved_page_size}",
            lambda: self._get_all_panel_users_uncached(
                page_size=resolved_page_size, log_responses=False
            ),
        )

    async def _get_all_panel_users_uncached(
        self, page_size: Optional[int] = None, log_responses: bool = False
    ) -> Optional[List[Dict[str, Any]]]:
        resolved_page_size = self._resolve_all_users_page_size(page_size)
        users = await self._fetch_all_panel_users_pages(
            page_size=resolved_page_size,
            log_responses=log_responses,
        )
        if users is None and resolved_page_size != 100:
            logging.warning(
                "Panel API users fetch failed with page size %s; retrying with page size 100.",
                resolved_page_size,
            )
            users = await self._fetch_all_panel_users_pages(
                page_size=100,
                log_responses=log_responses,
            )
        return users

    async def _fetch_all_panel_users_pages(
        self, page_size: int, log_responses: bool = False
    ) -> Optional[List[Dict[str, Any]]]:
        all_users = []
        start_offset = 0
        while True:
            params = {"size": page_size, "start": start_offset}
            response_data = await self._request(
                "GET", "/users", params=params, log_full_response=log_responses
            )

            if not response_data or response_data.get("error"):
                logging.error(
                    f"Failed to fetch panel users batch (start: {start_offset}). Response: {response_data}"  # noqa: E501
                )
                return None
            users_batch = response_data.get("response", {}).get("users", [])
            if not users_batch:
                break
            all_users.extend(users_batch)
            if len(users_batch) < page_size:
                break
            start_offset += page_size
            await asyncio.sleep(0.1)
        logging.info(f"Fetched {len(all_users)} users from panel API.")
        return all_users

    async def get_user_by_uuid(
        self, user_uuid: str, log_response: bool = False
    ) -> Optional[Dict[str, Any]]:
        if log_response or self._users_cache.ttl_seconds <= 0:
            return await self._get_user_by_uuid_uncached(user_uuid, log_response=log_response)
        return await self._users_cache.get_or_load(
            f"uuid:{user_uuid}",
            lambda: self._get_user_by_uuid_uncached(user_uuid, log_response=False),
        )

    async def _get_user_by_uuid_uncached(
        self, user_uuid: str, log_response: bool = False
    ) -> Optional[Dict[str, Any]]:
        lookup = await self.get_user_by_uuid_lookup(user_uuid, log_response=log_response)
        if lookup.get("ok") and isinstance(lookup.get("user"), dict):
            return lookup["user"]
        return None

    @staticmethod
    def _panel_response_details(response_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(response_data, dict):
            return {}
        details = response_data.get("details")
        return details if isinstance(details, dict) else {}

    @classmethod
    def _panel_response_error_code(cls, response_data: Optional[Dict[str, Any]]) -> Optional[str]:
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
    def _panel_response_message(cls, response_data: Optional[Dict[str, Any]]) -> Optional[str]:
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
    def _is_user_not_found_response(cls, response_data: Optional[Dict[str, Any]]) -> bool:
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
        response_data: Optional[Dict[str, Any]],
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
    ) -> Dict[str, Any]:
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
                "user": full_response.get("response"),
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
        uuid: Optional[str] = None,
        telegram_id: Optional[int] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        log_response: bool = False,
    ) -> Optional[Dict[str, Any]]:
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
        telegram_id: Optional[int] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        log_response: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:

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
                logging.info(f"Panel API: Users not found for {filter_used_log}")
                return []

        elif username is not None:
            filter_used_log = f"username={username}"
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
                logging.info(f"Panel API: User not found for {filter_used_log}")
                return []

        elif email is not None:
            filter_used_log = f"email={email}"
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
                logging.info(f"Panel API: Users not found for {filter_used_log}")
                return []

        if not telegram_id and not username and not email:
            logging.warning("get_users_by_filter called without any specific filter criteria.")
            return []

        logging.error(
            f"Failed to fetch panel users with filter ({filter_used_log}). Last API response: {response_data if not log_response else '(logged above)'}"  # noqa: E501
        )
        return None

    async def create_panel_user(
        self,
        username_on_panel: str,
        telegram_id: Optional[int] = None,
        email: Optional[str] = None,
        default_expire_days: int = 1,
        default_traffic_limit_bytes: int = 0,
        default_traffic_limit_strategy: str = "NO_RESET",
        hwid_device_limit: Optional[int] = None,
        specific_squad_uuids: Optional[List[str]] = None,
        external_squad_uuid: Optional[str] = None,
        description: Optional[str] = None,
        tag: Optional[str] = None,
        status: str = "ACTIVE",
        log_response: bool = False,
    ) -> Optional[Dict[str, Any]]:

        username_is_valid = (
            3 <= len(username_on_panel) <= 36
            and re.match(r"^[A-Za-z0-9_-]+$", username_on_panel) is not None
        )
        if not username_is_valid:
            msg = f"Panel username '{username_on_panel}' does not meet panel requirements."
            logging.error(msg)
            return {
                "error": True,
                "status_code": 400,
                "message": msg,
                "errorCode": "VALIDATION_ERROR_USERNAME",
            }

        now = datetime.now(timezone.utc)
        expire_at_dt = now + timedelta(days=default_expire_days)
        expire_at_iso = expire_at_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        payload: Dict[str, Any] = {
            "username": username_on_panel,
            "status": status.upper(),
            "expireAt": expire_at_iso,
            "trafficLimitStrategy": default_traffic_limit_strategy.upper(),
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
                logging.warning(
                    f"Ignoring invalid HWID device limit '{hwid_limit_value}' while creating panel user '{username_on_panel}'."  # noqa: E501
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
            logging.info(
                f"Panel user '{username_on_panel}' created successfully (UUID: {response.get('response', {}).get('uuid')})."  # noqa: E501
            )
            return response

        logging.error(
            f"Failed to create panel user '{username_on_panel}'. Payload: {payload}, Response: {response if not log_response else '(full response logged above)'}"  # noqa: E501
        )
        return response

    async def update_user_details_on_panel(
        self, user_uuid: str, update_payload: Dict[str, Any], log_response: bool = False
    ) -> Optional[Dict[str, Any]]:
        if "uuid" not in update_payload:
            update_payload["uuid"] = user_uuid

        full_response = await self._request(
            "PATCH", "/users", json=update_payload, log_full_response=log_response
        )
        if full_response and not full_response.get("error") and "response" in full_response:
            logging.debug("User %s details updated on panel.", user_uuid)
            await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            return full_response.get("response")

        logging.error(
            f"Failed to update user {user_uuid} details on panel. Payload: {update_payload}, Response: {full_response if not log_response else '(logged above)'}"  # noqa: E501
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
                logging.info(
                    f"User {user_uuid} status on panel successfully set to {action} (Actual: {actual_status})."  # noqa: E501
                )
                return True
            else:
                logging.warning(
                    f"User {user_uuid} status on panel action '{action}' called, but final status is '{actual_status}'."  # noqa: E501
                )
                return False

        logging.error(
            f"Failed to {action} user {user_uuid} on panel. Response: {response_data if not log_response else '(logged above)'}"  # noqa: E501
        )
        return False

    async def delete_user_from_panel(self, user_uuid: str, log_response: bool = False) -> bool:
        """Delete a user from the panel. Treat not-found as already deleted."""
        endpoint = f"/users/{user_uuid}"
        response_data = await self._request("DELETE", endpoint, log_full_response=log_response)

        if not response_data:
            logging.error(
                f"Panel API delete_user_from_panel returned no data for user {user_uuid}."
            )
            return False

        if response_data.get("error"):
            details = response_data.get("details") or {}
            error_code = details.get("errorCode") or response_data.get("errorCode")
            if error_code in {"A062", "A040"}:
                logging.info(
                    f"Panel user {user_uuid} already absent (errorCode {error_code}). Treating as deleted."  # noqa: E501
                )
                await self._invalidate_user_cache(user_uuid)
                await self._invalidate_devices_cache(user_uuid)
                await self._invalidate_all_users_cache()
                return True
            logging.error(f"Failed to delete user {user_uuid} on panel. Response: {response_data}")
            return False

        logging.info(f"Panel user {user_uuid} deleted successfully.")
        await self._invalidate_user_cache(user_uuid)
        await self._invalidate_devices_cache(user_uuid)
        await self._invalidate_all_users_cache()
        return True

    async def get_subscription_link(
        self, short_uuid_or_sub_uuid: str, client_type: Optional[str] = None
    ) -> Optional[str]:
        if not self.settings.PANEL_API_URL:
            logging.error("PANEL_API_URL not set, cannot generate subscription link.")
            return None
        base_sub_url = f"{self.settings.PANEL_API_URL.rstrip('/')}/sub/{short_uuid_or_sub_uuid}"
        if client_type:
            return f"{base_sub_url}/{client_type.lower()}"
        return base_sub_url

    async def get_subscription_page_config_by_short_uuid(
        self,
        short_uuid: str,
        request_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not short_uuid:
            return None
        endpoint = f"/subscriptions/subpage-config/{short_uuid}"
        payload = {"requestHeaders": request_headers or {}}
        response_data = await self._request(
            "GET",
            endpoint,
            json=payload,
            log_full_response=False,
        )
        if response_data and not response_data.get("error"):
            return response_data.get("response", response_data)
        logging.error(
            f"Failed to get subscription page config for short UUID {short_uuid}. Response: {response_data}"  # noqa: E501
        )
        return None

    async def get_subscription_page_config_list(self) -> Optional[Dict[str, Any]]:
        endpoint = "/subscription-page-configs"
        response_data = await self._request("GET", endpoint, log_full_response=False)
        if response_data and not response_data.get("error"):
            return response_data.get("response", response_data)
        logging.error(
            f"Failed to get subscription page config list from panel. Response: {response_data}"
        )
        return None

    async def get_subscription_page_config_by_uuid(
        self,
        config_uuid: str,
    ) -> Optional[Dict[str, Any]]:
        config_uuid = str(config_uuid or "").strip()
        if not config_uuid:
            return None
        endpoint = f"/subscription-page-configs/{config_uuid}"
        response_data = await self._request("GET", endpoint, log_full_response=False)
        if response_data and not response_data.get("error"):
            return response_data.get("response", response_data)
        logging.error(
            f"Failed to get subscription page config {config_uuid} from panel. Response: {response_data}"  # noqa: E501
        )
        return None

    async def get_user_devices(self, user_uuid: str) -> Optional[List[Dict[str, Any]]]:
        if self._devices_cache.ttl_seconds <= 0:
            return await self._get_user_devices_uncached(user_uuid)
        return await self._devices_cache.get_or_load(
            f"user:{user_uuid}",
            lambda: self._get_user_devices_uncached(user_uuid),
        )

    async def _get_user_devices_uncached(self, user_uuid: str) -> Optional[List[Dict[str, Any]]]:
        endpoint = f"/hwid/devices/{user_uuid}"
        response_data = await self._request("GET", endpoint, log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        logging.error(f"Failed to get user devices for user {user_uuid}. Response: {response_data}")
        return None

    async def disconnect_device(self, user_uuid: str, hwid: str) -> bool:
        endpoint = "/hwid/devices/delete"
        payload = {"userUuid": user_uuid, "hwid": hwid}
        response_data = await self._request("POST", endpoint, json=payload, log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            await self._invalidate_devices_cache(user_uuid)
            return True
        logging.error(
            f"Failed to disconnect device {hwid} for user {user_uuid}. Payload: {payload}, Response: {response_data}"  # noqa: E501
        )
        return False

    async def update_bot_db_sync_status(
        self,
        session: AsyncSession,
        status: str,
        details: str,
        users_processed: int = 0,
        subs_synced: int = 0,
    ):
        await panel_sync_dal.update_panel_sync_status(
            session, status, details, users_processed, subs_synced
        )

    async def get_bot_db_last_sync_status(self, session: AsyncSession) -> Optional[PanelSyncStatus]:
        return await panel_sync_dal.get_panel_sync_status(session)

    async def get_system_stats(self) -> Optional[Dict[str, Any]]:
        """Get system statistics (CPU, memory, users counts)"""
        response_data = await self._request("GET", "/system/stats", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        return None

    async def get_bandwidth_stats(self) -> Optional[Dict[str, Any]]:
        """Get bandwidth statistics"""
        response_data = await self._request(
            "GET", "/system/stats/bandwidth", log_full_response=False
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        return None

    async def get_nodes_bandwidth_usage(
        self,
        *,
        start: str,
        end: str,
        top_nodes_limit: int = 64,
    ) -> Optional[Dict[str, Any]]:
        """Per-node usage for a date range (Remnawave GET /bandwidth-stats/nodes).

        Query dates are calendar dates (YYYY-MM-DD), same as the panel UI analytics.
        Response includes topNodes[{ uuid, name, countryCode, total }, ...] where total is bytes.
        """
        response_data = await self._request(
            "GET",
            "/bandwidth-stats/nodes",
            params={
                "start": start,
                "end": end,
                "topNodesLimit": top_nodes_limit,
            },
            log_full_response=False,
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        return None

    async def get_user_bandwidth_stats(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        endpoint = f"/bandwidth-stats/users/{user_uuid}"
        response_data = await self._request("GET", endpoint, log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        logging.error(
            "Failed to get bandwidth stats for user %s. Response: %s", user_uuid, response_data
        )
        return None

    async def get_node_users_bandwidth_stats(
        self,
        node_uuid: str,
        *,
        start: str,
        end: str,
        top_users_limit: int = 10000,
    ) -> Optional[Dict[str, Any]]:
        endpoint = f"/bandwidth-stats/nodes/{node_uuid}/users"
        response_data = await self._request(
            "GET",
            endpoint,
            params={"start": start, "end": end, "topUsersLimit": top_users_limit},
            log_full_response=False,
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            response = response_data.get("response")
            if isinstance(response, dict):
                return response
            if isinstance(response, list):
                return {"topUsers": response}
        logging.error(
            "Failed to get node bandwidth stats for node %s. Response: %s",
            node_uuid,
            response_data,
        )
        return None

    async def _invalidate_squad_caches(self) -> None:
        await self._squads_cache.invalidate_remote()

    async def _invalidate_user_cache(self, user_uuid: Optional[str]) -> None:
        if not user_uuid:
            return
        await self._users_cache.invalidate_remote(f"uuid:{user_uuid}")

    async def _invalidate_all_users_cache(self) -> None:
        await self._all_users_cache.invalidate_remote()

    async def _invalidate_devices_cache(self, user_uuid: Optional[str]) -> None:
        if not user_uuid:
            return
        await self._devices_cache.invalidate_remote(f"user:{user_uuid}")

    async def get_internal_squads(self) -> Optional[List[Dict[str, Any]]]:
        return await self._squads_cache.get_or_load("list", self._get_internal_squads_uncached)

    async def _get_internal_squads_uncached(self) -> Optional[List[Dict[str, Any]]]:
        response_data = await self._request("GET", "/internal-squads", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            response = response_data.get("response")
            if isinstance(response, list):
                return response
            if isinstance(response, dict):
                for key in ("internalSquads", "squads", "items", "data"):
                    value = response.get(key)
                    if isinstance(value, list):
                        return value
        logging.error("Failed to get internal squads. Response: %s", response_data)
        return None

    async def get_internal_squad(self, squad_uuid: str) -> Optional[Dict[str, Any]]:
        return await self._squads_cache.get_or_load(
            f"detail:{squad_uuid}",
            lambda: self._get_internal_squad_uncached(squad_uuid),
        )

    async def _get_internal_squad_uncached(self, squad_uuid: str) -> Optional[Dict[str, Any]]:
        response_data = await self._request(
            "GET", f"/internal-squads/{squad_uuid}", log_full_response=False
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            response = response_data.get("response")
            if isinstance(response, dict):
                inner = response.get("internalSquad") or response.get("squad")
                if isinstance(inner, dict):
                    return inner
                return response
        logging.error(
            "Failed to get internal squad %s. Response: %s",
            squad_uuid,
            response_data,
        )
        return None

    async def get_internal_squad_accessible_nodes(
        self,
        squad_uuid: str,
    ) -> Optional[List[Dict[str, Any]]]:
        return await self._squads_cache.get_or_load(
            f"nodes:{squad_uuid}",
            lambda: self._get_internal_squad_accessible_nodes_uncached(squad_uuid),
        )

    async def _get_internal_squad_accessible_nodes_uncached(
        self,
        squad_uuid: str,
    ) -> Optional[List[Dict[str, Any]]]:
        endpoints = (
            f"/internal-squads/{squad_uuid}/accessible-nodes",
            f"/internal-squads/{squad_uuid}/nodes",
        )
        last_response = None
        for endpoint in endpoints:
            response_data = await self._request("GET", endpoint, log_full_response=False)
            last_response = response_data
            if response_data and not response_data.get("error") and "response" in response_data:
                response = response_data.get("response")
                if isinstance(response, list):
                    return response
                if isinstance(response, dict):
                    for key in ("nodes", "accessibleNodes", "items", "data"):
                        value = response.get(key)
                        if isinstance(value, list):
                            return value
        logging.error(
            "Failed to get accessible nodes for internal squad %s. Response: %s",
            squad_uuid,
            last_response,
        )
        return None

    async def get_hosts(self) -> Optional[List[Dict[str, Any]]]:
        return await self._hosts_cache.get_or_load("list", self._get_hosts_uncached)

    async def _get_hosts_uncached(self) -> Optional[List[Dict[str, Any]]]:
        response_data = await self._request("GET", "/hosts", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            response = response_data.get("response")
            if isinstance(response, list):
                return response
            if isinstance(response, dict):
                for key in ("hosts", "items", "data"):
                    value = response.get(key)
                    if isinstance(value, list):
                        return value
        logging.error("Failed to get hosts. Response: %s", response_data)
        return None

    async def reset_user_traffic(self, user_uuid: str) -> bool:
        endpoint = f"/users/{user_uuid}/actions/reset-traffic"
        response_data = await self._request("POST", endpoint, log_full_response=False)
        if response_data and not response_data.get("error"):
            await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            return True
        logging.error("Failed to reset traffic for user %s. Response: %s", user_uuid, response_data)
        return False

    async def add_users_to_internal_squad(self, squad_uuid: str, user_uuids: List[str]) -> bool:
        endpoint = f"/internal-squads/{squad_uuid}/bulk-actions/add-users"
        response_data = await self._request(
            "POST",
            endpoint,
            json={"users": user_uuids, "userUuids": user_uuids},
            log_full_response=False,
        )
        if response_data and not response_data.get("error"):
            await self._invalidate_squad_caches()
            for user_uuid in user_uuids:
                await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            return True
        logging.error("Failed to add users to squad %s. Response: %s", squad_uuid, response_data)
        return False

    async def remove_users_from_internal_squad(
        self, squad_uuid: str, user_uuids: List[str]
    ) -> bool:
        endpoint = f"/internal-squads/{squad_uuid}/bulk-actions/remove-users"
        response_data = await self._request(
            "DELETE",
            endpoint,
            json={"users": user_uuids, "userUuids": user_uuids},
            log_full_response=False,
        )
        if response_data and not response_data.get("error"):
            await self._invalidate_squad_caches()
            for user_uuid in user_uuids:
                await self._invalidate_user_cache(user_uuid)
            await self._invalidate_all_users_cache()
            return True
        logging.error(
            "Failed to remove users from squad %s. Response: %s", squad_uuid, response_data
        )
        return False

    async def get_nodes_online_lookups(self) -> Dict[str, Dict[str, int]]:
        """Live ``usersOnline`` per node from ``GET /nodes`` (node directory).

        Newer panels expose Prometheus-style metrics under ``/system/stats/nodes``
        (``nodes: [{ usersOnline, ... }]``). Older/alternate builds only return
        historical rows (e.g. ``lastSevenDays``) without live counts. The node
        directory response always includes ``usersOnline`` and ``uuid``.

        Returns:
            ``{"byUuid": {uuid_lower: int}, "byName": {name_lower: int}}``
        """
        by_uuid: Dict[str, int] = {}
        by_name: Dict[str, int] = {}
        page_size = 100
        start = 0
        while True:
            response_data = await self._request(
                "GET",
                "/nodes",
                params={"size": page_size, "start": start},
                log_full_response=False,
            )
            if not response_data or response_data.get("error"):
                break
            resp = response_data.get("response")
            batch: List[Dict[str, Any]] = []
            if isinstance(resp, list):
                batch = [x for x in resp if isinstance(x, dict)]
            elif isinstance(resp, dict):
                inner = resp.get("nodes") or resp.get("items") or []
                batch = [x for x in inner if isinstance(x, dict)]
            if not batch:
                break
            for n in batch:
                uid = n.get("uuid") or n.get("nodeUuid") or n.get("node_uuid")
                uo = n.get("usersOnline")
                if uo is None:
                    uo = n.get("users_online")
                if uo is None:
                    continue
                try:
                    val = int(uo)
                except (TypeError, ValueError):
                    continue
                if uid:
                    by_uuid[str(uid).strip().lower()] = val
                name = n.get("name")
                if name and isinstance(name, str) and name.strip():
                    by_name[name.strip().lower()] = val
            if len(batch) < page_size:
                break
            start += page_size
            await asyncio.sleep(0.05)
        return {"byUuid": by_uuid, "byName": by_name}

    async def get_nodes_statistics(self) -> Optional[Dict[str, Any]]:
        """Get nodes statistics"""
        response_data = await self._request("GET", "/system/stats/nodes", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        return None

    async def encrypt_happ_link(self, link_to_encrypt: str) -> Optional[str]:
        """Encrypt a subscription link using the panel's happ crypt4 API.

        Returns the encrypted link string or None if encryption failed.
        """
        payload = {"linkToEncrypt": link_to_encrypt}
        response_data = await self._request(
            "POST", "/system/tools/happ/encrypt", json=payload, log_full_response=False
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response", {}).get("encryptedLink")
        logging.error(f"Failed to encrypt happ link. Response: {response_data}")
        return None
