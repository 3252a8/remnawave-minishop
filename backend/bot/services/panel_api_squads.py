import asyncio
import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# Static endpoint prefixes used as log/metric labels instead of the raw request
# path. Endpoints embed user identifiers (telegram id, username, email, uuids),
# so logging the path verbatim would leak private data into log files; the
# label keeps only the constant prefix. Longest prefixes first so e.g.


def _json_dict(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


_HAPP_ENCRYPT_UNAVAILABLE = False


class PanelApiSquadMutationMixin:
    if TYPE_CHECKING:

        async def _request(
            self, method: str, endpoint: str, log_full_response: bool = False, **kwargs: Any
        ) -> dict[str, Any] | None: ...
        async def _invalidate_squad_caches(self) -> None: ...
        async def _invalidate_user_cache(self, user_uuid: str | None) -> None: ...
        async def _invalidate_all_users_cache(self) -> None: ...

    async def add_users_to_internal_squad(self, squad_uuid: str, user_uuids: list[str]) -> bool:
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
        logger.error("Failed to add users to squad %s. Response: %s", squad_uuid, response_data)
        return False

    async def remove_users_from_internal_squad(
        self, squad_uuid: str, user_uuids: list[str]
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
        logger.error(
            "Failed to remove users from squad %s. Response: %s", squad_uuid, response_data
        )
        return False

    async def get_nodes_online_lookups(self) -> dict[str, dict[str, int]]:
        """Live ``usersOnline`` per node from ``GET /nodes`` (node directory).

        Newer panels expose Prometheus-style metrics under ``/system/stats/nodes``
        (``nodes: [{ usersOnline, ... }]``). Older/alternate builds only return
        historical rows (e.g. ``lastSevenDays``) without live counts. The node
        directory response always includes ``usersOnline`` and ``uuid``.

        Returns:
            ``{"byUuid": {uuid_lower: int}, "byName": {name_lower: int}}``
        """
        by_uuid: dict[str, int] = {}
        by_name: dict[str, int] = {}
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
            batch: list[dict[str, Any]] = []
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

    async def get_nodes_statistics(self) -> dict[str, Any] | None:
        """Get nodes statistics"""
        response_data = await self._request("GET", "/system/stats/nodes", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return _json_dict(response_data.get("response"))
        return None

    async def encrypt_happ_link(self, link_to_encrypt: str) -> str | None:
        """Encrypt a subscription link using the panel's happ crypt4 API.

        Returns the encrypted link string or None if encryption failed.
        """
        global _HAPP_ENCRYPT_UNAVAILABLE

        if _HAPP_ENCRYPT_UNAVAILABLE:
            logger.info("Skipping happ crypt4 encryption: panel endpoint is unavailable.")
            return None
        payload = {"linkToEncrypt": link_to_encrypt}
        response_data = await self._request(
            "POST", "/system/tools/happ/encrypt", json=payload, log_full_response=False
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            response = _json_dict(response_data.get("response"))
            encrypted_link = response.get("encryptedLink") if response is not None else None
            return encrypted_link if isinstance(encrypted_link, str) else None
        status_code = response_data.get("status_code") if isinstance(response_data, dict) else None
        if status_code in {404, 410}:
            _HAPP_ENCRYPT_UNAVAILABLE = True
            logger.warning(
                "Panel happ crypt4 encryption endpoint is unavailable; raw subscription "
                "links will be used as fallback."
            )
            return None
        logger.error("Failed to encrypt happ link. Response: %s", response_data)
        return None
