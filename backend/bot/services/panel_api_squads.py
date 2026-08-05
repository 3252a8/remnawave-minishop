import asyncio
import logging
from typing import TYPE_CHECKING, Any

from bot.services.panel_api_compat import PanelApiCompatibility, numeric_panel_user_id
from bot.services.panel_api_contracts import PanelApiCapability, PanelApiOperation
from bot.utils.happ_crypto import create_happ_crypt4_link

logger = logging.getLogger(__name__)

# Static endpoint prefixes used as log/metric labels instead of the raw request
# path. Endpoints embed user identifiers (telegram id, username, email, uuids),
# so logging the path verbatim would leak private data into log files; the
# label keeps only the constant prefix. Longest prefixes first so e.g.


def _json_dict(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


class PanelApiSquadMutationMixin:
    _V3_SQUAD_BULK_LIMIT = 1000
    _USER_SQUAD_EXACT_BULK_LIMIT = 500

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
        async def _invalidate_squad_caches(self) -> None: ...
        async def _invalidate_user_cache(self, user_uuid: str | None) -> None: ...
        async def _invalidate_all_users_cache(self) -> None: ...
        async def get_user_by_uuid(
            self, user_uuid: str, log_response: bool = False, *, use_cache: bool = True
        ) -> dict[str, Any] | None: ...
        async def update_user_details_on_panel(
            self,
            user_uuid: str,
            update_payload: dict[str, Any],
            log_response: bool = False,
        ) -> dict[str, Any] | None: ...
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
        @classmethod
        def _is_missing_endpoint_response(cls, response_data: dict[str, Any] | None) -> bool: ...

    @staticmethod
    def _user_internal_squad_uuids(user: dict[str, Any]) -> list[str]:
        values = user.get("activeInternalSquads")
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            raw_uuid = value.get("uuid") if isinstance(value, dict) else value
            squad_uuid = str(raw_uuid or "").strip()
            if squad_uuid and squad_uuid not in result:
                result.append(squad_uuid)
        return result

    async def _update_legacy_user_squad_membership(
        self, squad_uuid: str, user_uuid: str, *, add: bool
    ) -> bool:
        """Target one 2.8 user without calling its misleading all-users route."""
        user = await self.get_user_by_uuid(user_uuid, use_cache=False)
        if user is None:
            return False
        squads = self._user_internal_squad_uuids(user)
        if add and squad_uuid not in squads:
            squads.append(squad_uuid)
        elif not add:
            squads = [value for value in squads if value != squad_uuid]
        else:
            return True
        return (
            await self.update_user_details_on_panel(
                user_uuid,
                {"activeInternalSquads": squads},
            )
            is not None
        )

    async def update_users_internal_squads_exact(
        self,
        user_uuids: list[str],
        active_internal_squad_uuids: list[str],
    ) -> bool:
        """Set one complete squad state for many users on both supported generations.

        The route exists in 2.8.1 and 3.x, but its identity selector and success
        response changed. Keeping this exact-state operation separate from the
        3.x squad-specific 202 routes preserves manual overrides and avoids
        ordering races between independent add/remove jobs.
        """
        references = list(
            dict.fromkeys(str(value).strip() for value in user_uuids if str(value).strip())
        )
        if not references:
            return True
        compatibility = await self.get_panel_api_compatibility()
        capability = PanelApiCapability.BULK_SQUAD_UPDATE
        if self.panel_capability_state(capability, compatibility) is False:
            return False
        operation = PanelApiOperation.USERS_BULK_UPDATE_SQUADS
        if not await self.panel_mutation_allowed(operation, compatibility=compatibility):
            return False
        resolved = [
            await self.resolve_panel_user_reference(
                value,
                operation,
                compatibility=compatibility,
            )
            for value in references
        ]
        if any(value is None for value in resolved):
            return False
        resolved_refs = [value for value in resolved if value is not None]
        numeric_ids = [numeric_panel_user_id(value) for value in resolved_refs]
        identities: list[str | int] = []
        if all(value is not None for value in numeric_ids):
            selector = "userIds"
            identities.extend(value for value in numeric_ids if value is not None)
        elif all(value is None for value in numeric_ids):
            selector = "uuids"
            identities.extend(resolved_refs)
        else:
            logger.error("Cannot bulk-update squads for mixed Remnawave user generations.")
            return False

        squads = list(
            dict.fromkeys(
                str(value).strip() for value in active_internal_squad_uuids if str(value).strip()
            )
        )
        if not squads:
            # Remnawave 3.0.0 raises A088/500 instead of clearing the final
            # squad through this route. Callers must use per-user PATCH for an
            # empty exact state; skipping the POST keeps fallback unambiguous.
            return False
        for offset in range(0, len(identities), self._USER_SQUAD_EXACT_BULK_LIMIT):
            chunk = identities[offset : offset + self._USER_SQUAD_EXACT_BULK_LIMIT]
            response_data = await self._request(
                "POST",
                "/users/bulk/update-squads",
                operation=operation,
                json={selector: chunk, "activeInternalSquads": squads},
                log_full_response=False,
            )
            if not response_data or response_data.get("error"):
                if self._is_missing_endpoint_response(response_data) or (
                    isinstance(response_data, dict) and response_data.get("status_code") == 405
                ):
                    self.remember_panel_capability(capability, False)
                logger.warning(
                    "Exact Remnawave squad bulk failed for %s users; caller may use "
                    "the per-user compatibility path.",
                    len(chunk),
                )
                return False
            response = response_data.get("response")
            affected = response.get("affectedRows") if isinstance(response, dict) else None
            if isinstance(affected, int) and affected < len(chunk):
                logger.warning(
                    "Exact Remnawave squad bulk affected %s of %s users.",
                    affected,
                    len(chunk),
                )
                return False

        self.remember_panel_capability(capability, True)
        await self._invalidate_squad_caches()
        for reference in references:
            await self._invalidate_user_cache(reference)
        await self._invalidate_all_users_cache()
        logger.info(
            "metric panel_squad_bulk users=%s chunks=%s squads=%s selector=%s",
            len(references),
            (len(identities) + self._USER_SQUAD_EXACT_BULK_LIMIT - 1)
            // self._USER_SQUAD_EXACT_BULK_LIMIT,
            len(squads),
            selector,
        )
        return True

    async def add_users_to_internal_squad(self, squad_uuid: str, user_uuids: list[str]) -> bool:
        if not user_uuids:
            return True
        operation = PanelApiOperation.INTERNAL_SQUAD_ADD_USERS
        compatibility = await self.get_panel_api_compatibility()
        targeted_bulk = self.panel_capability_state(
            PanelApiCapability.TARGETED_SQUAD_BULK,
            compatibility,
        )
        resolved_user_refs = [
            await self.resolve_panel_user_reference(
                value,
                operation,
                compatibility=compatibility,
            )
            for value in user_uuids
        ]
        if any(value is None for value in resolved_user_refs):
            return False
        user_references = [value for value in resolved_user_refs if value is not None]
        numeric_ids = [numeric_panel_user_id(value) for value in user_references]
        if targeted_bulk is True or (
            targeted_bulk is None and all(value is not None for value in numeric_ids)
        ):
            if not await self.panel_mutation_allowed(operation, compatibility=compatibility):
                return False
            endpoint = f"/internal-squads/{squad_uuid}/bulk-actions/add-many-users"
            resolved_ids = list(dict.fromkeys(value for value in numeric_ids if value is not None))
        elif any(value is not None for value in numeric_ids):
            logger.error("Cannot add a mixed list of Remnawave 2.x and 3.x user identifiers.")
            return False
        else:
            # In 2.8.1 the add-users route means *all* users and ignores a body.
            # PATCH each requested user instead; 3.0's add-many-users route is
            # the first targeted bulk contract.
            results = await asyncio.gather(
                *(
                    self._update_legacy_user_squad_membership(squad_uuid, user_uuid, add=True)
                    for user_uuid in user_references
                )
            )
            if all(results):
                await self._invalidate_squad_caches()
                return True
            logger.error("Failed to add one or more users to squad %s.", squad_uuid)
            return False
        for offset in range(0, len(resolved_ids), self._V3_SQUAD_BULK_LIMIT):
            response_data = await self._request(
                "POST",
                endpoint,
                operation=operation,
                json={"userIds": resolved_ids[offset : offset + self._V3_SQUAD_BULK_LIMIT]},
                log_full_response=False,
            )
            if not response_data or response_data.get("error"):
                logger.error(
                    "Failed to add users to squad %s. Response: %s", squad_uuid, response_data
                )
                return False
            self.remember_panel_capability(PanelApiCapability.TARGETED_SQUAD_BULK, True)
        await self._invalidate_squad_caches()
        for user_uuid in user_uuids:
            await self._invalidate_user_cache(user_uuid)
        await self._invalidate_all_users_cache()
        return True

    async def remove_users_from_internal_squad(
        self, squad_uuid: str, user_uuids: list[str]
    ) -> bool:
        if not user_uuids:
            return True
        operation = PanelApiOperation.INTERNAL_SQUAD_REMOVE_USERS
        compatibility = await self.get_panel_api_compatibility()
        targeted_bulk = self.panel_capability_state(
            PanelApiCapability.TARGETED_SQUAD_BULK,
            compatibility,
        )
        resolved_user_refs = [
            await self.resolve_panel_user_reference(
                value,
                operation,
                compatibility=compatibility,
            )
            for value in user_uuids
        ]
        if any(value is None for value in resolved_user_refs):
            return False
        user_references = [value for value in resolved_user_refs if value is not None]
        numeric_ids = [numeric_panel_user_id(value) for value in user_references]
        if targeted_bulk is True or (
            targeted_bulk is None and all(value is not None for value in numeric_ids)
        ):
            if not await self.panel_mutation_allowed(operation, compatibility=compatibility):
                return False
            endpoint = f"/internal-squads/{squad_uuid}/bulk-actions/remove-many-users"
            resolved_ids = list(dict.fromkeys(value for value in numeric_ids if value is not None))
        elif any(value is not None for value in numeric_ids):
            logger.error("Cannot remove a mixed list of Remnawave 2.x and 3.x user identifiers.")
            return False
        else:
            results = await asyncio.gather(
                *(
                    self._update_legacy_user_squad_membership(squad_uuid, user_uuid, add=False)
                    for user_uuid in user_references
                )
            )
            if all(results):
                await self._invalidate_squad_caches()
                return True
            logger.error("Failed to remove one or more users from squad %s.", squad_uuid)
            return False
        for offset in range(0, len(resolved_ids), self._V3_SQUAD_BULK_LIMIT):
            response_data = await self._request(
                "DELETE",
                endpoint,
                operation=operation,
                json={"userIds": resolved_ids[offset : offset + self._V3_SQUAD_BULK_LIMIT]},
                log_full_response=False,
            )
            if not response_data or response_data.get("error"):
                logger.error(
                    "Failed to remove users from squad %s. Response: %s",
                    squad_uuid,
                    response_data,
                )
                return False
            self.remember_panel_capability(PanelApiCapability.TARGETED_SQUAD_BULK, True)
        await self._invalidate_squad_caches()
        for user_uuid in user_uuids:
            await self._invalidate_user_cache(user_uuid)
        await self._invalidate_all_users_cache()
        return True

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
                operation=PanelApiOperation.NODES_LIST,
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
        response_data = await self._request(
            "GET",
            "/system/stats/nodes",
            operation=PanelApiOperation.NODE_STATS,
            log_full_response=False,
        )
        if response_data and not response_data.get("error") and "response" in response_data:
            return _json_dict(response_data.get("response"))
        return None

    async def encrypt_happ_link(self, link_to_encrypt: str) -> str | None:
        """Encrypt a subscription link locally with Happ Crypt4.

        Returns the encrypted link string or None if encryption failed.
        """
        return create_happ_crypt4_link(link_to_encrypt)
