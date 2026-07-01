import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from db.dal import panel_sync_dal
from db.models import PanelSyncStatus

# Static endpoint prefixes used as log/metric labels instead of the raw request
# path. Endpoints embed user identifiers (telegram id, username, email, uuids),
# so logging the path verbatim would leak private data into log files; the
# label keeps only the constant prefix. Longest prefixes first so e.g.


def _json_dict(value: object) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _json_dict_list(value: object) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, dict)]


def _panel_devices_list(value: object) -> Optional[List[Dict[str, Any]]]:
    if isinstance(value, dict):
        for key in ("devices", "items", "data"):
            devices = _json_dict_list(value.get(key))
            if devices is not None:
                return devices
        return None
    return _json_dict_list(value)


def _panel_dict_response(response_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not response_data or response_data.get("error"):
        return None
    return _json_dict(response_data.get("response", response_data))


class PanelApiResourcesMixin:
    settings: Settings
    _all_users_cache: AsyncTTLCache
    _devices_cache: AsyncTTLCache
    _external_squads_cache: AsyncTTLCache
    _hosts_cache: AsyncTTLCache
    _squads_cache: AsyncTTLCache
    _users_cache: AsyncTTLCache

    if TYPE_CHECKING:

        async def _request(
            self, method: str, endpoint: str, log_full_response: bool = False, **kwargs: Any
        ) -> Optional[Dict[str, Any]]: ...

    async def get_subscription_link(
        self, short_uuid_or_sub_uuid: str, client_type: Optional[str] = None
    ) -> Optional[str]:
        panel_api_url = self.settings.panel_settings.api_url
        if not panel_api_url:
            logging.error("PANEL_API_URL not set, cannot generate subscription link.")
            return None
        base_sub_url = f"{panel_api_url.rstrip('/')}/sub/{short_uuid_or_sub_uuid}"
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
        response = _panel_dict_response(response_data)
        if response is not None:
            return response
        logging.error(
            f"Failed to get subscription page config for short UUID {short_uuid}. Response: {response_data}"  # noqa: E501
        )
        return None

    async def get_subscription_page_config_list(self) -> Optional[Dict[str, Any]]:
        endpoint = "/subscription-page-configs"
        response_data = await self._request("GET", endpoint, log_full_response=False)
        response = _panel_dict_response(response_data)
        if response is not None:
            return response
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
        response = _panel_dict_response(response_data)
        if response is not None:
            return response
        logging.error(
            f"Failed to get subscription page config {config_uuid} from panel. Response: {response_data}"  # noqa: E501
        )
        return None

    async def get_external_squad(self, squad_uuid: str) -> Optional[Dict[str, Any]]:
        squad_uuid = str(squad_uuid or "").strip()
        if not squad_uuid:
            return None
        if self._external_squads_cache.ttl_seconds <= 0:
            return await self._get_external_squad_uncached(squad_uuid)
        cached = await self._external_squads_cache.get_or_load(
            f"detail:{squad_uuid}",
            lambda: self._get_external_squad_uncached(squad_uuid),
        )
        return _json_dict(cached)

    async def _get_external_squad_uncached(self, squad_uuid: str) -> Optional[Dict[str, Any]]:
        response_data = await self._request(
            "GET",
            f"/external-squads/{squad_uuid}",
            log_full_response=False,
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            response = response_data.get("response")
            if isinstance(response, dict):
                return response
        logging.error("Failed to get external squad %s. Response: %s", squad_uuid, response_data)
        return None

    async def get_user_devices(self, user_uuid: str) -> Optional[List[Dict[str, Any]]]:
        if self._devices_cache.ttl_seconds <= 0:
            return await self._get_user_devices_uncached(user_uuid)
        cached = await self._devices_cache.get_or_load(
            f"user:{user_uuid}",
            lambda: self._get_user_devices_uncached(user_uuid),
        )
        return _panel_devices_list(cached)

    async def _get_user_devices_uncached(self, user_uuid: str) -> Optional[List[Dict[str, Any]]]:
        endpoint = f"/hwid/devices/{user_uuid}"
        response_data = await self._request("GET", endpoint, log_full_response=False)
        if response_data and not response_data.get("error"):
            for key in ("response", "data"):
                if key not in response_data:
                    continue
                devices = _panel_devices_list(response_data.get(key))
                if devices is not None:
                    return devices
        logging.error(
            "Failed to get user devices for user %s (panel response redacted).", user_uuid
        )
        return None

    async def disconnect_device(self, user_uuid: str, hwid: str) -> bool:
        endpoint = "/hwid/devices/delete"
        payload = {"userUuid": user_uuid, "hwid": hwid}
        response_data = await self._request("POST", endpoint, json=payload, log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            await self._invalidate_devices_cache(user_uuid)
            return True
        logging.error(
            "Failed to disconnect device for user %s (device id and panel response redacted).",
            user_uuid,
        )
        return False

    async def get_hwid_devices_stats(self) -> Optional[Dict[str, Any]]:
        """Return HWID aggregate stats, including Remnawave 2.8 byPlatform[].byApp."""
        response_data = await self._request("GET", "/hwid/devices/stats", log_full_response=False)
        response = _panel_dict_response(response_data)
        if response is not None:
            return response
        logging.error("Failed to get HWID device stats. Response: %s", response_data)
        return None

    async def get_hwid_devices_top_users(
        self,
        *,
        start: int = 0,
        size: int = 10,
    ) -> Optional[Dict[str, Any]]:
        params = {"start": max(0, int(start)), "size": max(1, int(size))}
        response_data = await self._request(
            "GET",
            "/hwid/devices/top-users",
            params=params,
            log_full_response=False,
        )
        response = _panel_dict_response(response_data)
        if response is not None:
            return response
        logging.error("Failed to get HWID top users. Response: %s", response_data)
        return None

    async def restart_node(self, node_uuid: str, *, force_restart: bool = False) -> bool:
        endpoint = f"/nodes/{node_uuid}/actions/restart"
        response_data = await self._request(
            "POST",
            endpoint,
            json={"forceRestart": bool(force_restart)},
            log_full_response=False,
        )
        if response_data and not response_data.get("error"):
            return True
        logging.error("Failed to restart node %s. Response: %s", node_uuid, response_data)
        return False

    async def restart_all_nodes(self, *, force_restart: bool = False) -> bool:
        response_data = await self._request(
            "POST",
            "/nodes/actions/restart-all",
            json={"forceRestart": bool(force_restart)},
            log_full_response=False,
        )
        if response_data and not response_data.get("error"):
            return True
        logging.error("Failed to restart all nodes. Response: %s", response_data)
        return False

    async def update_bot_db_sync_status(
        self,
        session: AsyncSession,
        status: str,
        details: str,
        users_processed: int = 0,
        subs_synced: int = 0,
    ) -> None:
        await panel_sync_dal.update_panel_sync_status(
            session, status, details, users_processed, subs_synced
        )

    async def get_bot_db_last_sync_status(self, session: AsyncSession) -> Optional[PanelSyncStatus]:
        return await panel_sync_dal.get_panel_sync_status(session)

    async def get_system_stats(self) -> Optional[Dict[str, Any]]:
        """Get system statistics (CPU, memory, users counts)"""
        response_data = await self._request("GET", "/system/stats", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return _json_dict(response_data.get("response"))
        return None

    async def get_bandwidth_stats(self) -> Optional[Dict[str, Any]]:
        """Get bandwidth statistics"""
        response_data = await self._request(
            "GET", "/system/stats/bandwidth", log_full_response=False
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            return _json_dict(response_data.get("response"))
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
            return _json_dict(response_data.get("response"))
        return None

    async def get_user_bandwidth_stats(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        endpoint = f"/bandwidth-stats/users/{user_uuid}"
        response_data = await self._request("GET", endpoint, log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return _json_dict(response_data.get("response"))
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
        squads = _json_dict_list(
            await self._squads_cache.get_or_load("list", self._get_internal_squads_uncached)
        )
        if squads is not None:
            return squads
        stale_squads = _json_dict_list(self._squads_cache.get_stale("list"))
        if stale_squads is not None:
            logging.warning("Using stale internal squads cache after panel fetch failed.")
            return stale_squads
        return None

    async def _get_internal_squads_uncached(self) -> Optional[List[Dict[str, Any]]]:
        response_data = await self._request("GET", "/internal-squads", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            response = response_data.get("response")
            if isinstance(response, list):
                return _json_dict_list(response)
            if isinstance(response, dict):
                for key in ("internalSquads", "squads", "items", "data"):
                    value = response.get(key)
                    if isinstance(value, list):
                        return _json_dict_list(value)
        logging.error("Failed to get internal squads. Response: %s", response_data)
        return None

    async def get_internal_squad(self, squad_uuid: str) -> Optional[Dict[str, Any]]:
        cached = await self._squads_cache.get_or_load(
            f"detail:{squad_uuid}",
            lambda: self._get_internal_squad_uncached(squad_uuid),
        )
        return _json_dict(cached)

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
        cached = await self._squads_cache.get_or_load(
            f"nodes:{squad_uuid}",
            lambda: self._get_internal_squad_accessible_nodes_uncached(squad_uuid),
        )
        return _json_dict_list(cached)

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
                    return _json_dict_list(response)
                if isinstance(response, dict):
                    for key in ("nodes", "accessibleNodes", "items", "data"):
                        value = response.get(key)
                        if isinstance(value, list):
                            return _json_dict_list(value)
        logging.error(
            "Failed to get accessible nodes for internal squad %s. Response: %s",
            squad_uuid,
            last_response,
        )
        return None

    async def get_hosts(self) -> Optional[List[Dict[str, Any]]]:
        cached = await self._hosts_cache.get_or_load("list", self._get_hosts_uncached)
        return _json_dict_list(cached)

    async def _get_hosts_uncached(self) -> Optional[List[Dict[str, Any]]]:
        response_data = await self._request("GET", "/hosts", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            response = response_data.get("response")
            if isinstance(response, list):
                return _json_dict_list(response)
            if isinstance(response, dict):
                for key in ("hosts", "items", "data"):
                    value = response.get(key)
                    if isinstance(value, list):
                        return _json_dict_list(value)
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
