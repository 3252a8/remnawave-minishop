"""Generation-aware connection teardown operations."""

import logging
from typing import TYPE_CHECKING, Any

from bot.services.panel_api_compat import PanelApiCompatibility, numeric_panel_user_id
from bot.services.panel_api_contracts import PanelApiCapability, PanelApiOperation

logger = logging.getLogger(__name__)


class PanelApiConnectionsMixin:
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
        def _panel_response_error_code(cls, response_data: dict[str, Any] | None) -> str | None: ...
        @classmethod
        def _is_missing_endpoint_response(cls, response_data: dict[str, Any] | None) -> bool: ...

    async def drop_user_connections(
        self,
        user_uuid: str,
        node_uuids: list[str] | None = None,
        log_response: bool = False,
    ) -> bool:
        return await self.drop_users_connections(
            [user_uuid],
            node_uuids,
            log_response=log_response,
        )

    async def drop_users_connections(
        self,
        user_uuids: list[str],
        node_uuids: list[str] | None = None,
        log_response: bool = False,
    ) -> bool:
        """Tear down live connections for many users through one panel job."""
        references = list(
            dict.fromkeys(str(value).strip() for value in user_uuids if str(value).strip())
        )
        if not references:
            return True
        compatibility = await self.get_panel_api_compatibility()
        initial_numeric_ids = [numeric_panel_user_id(value) for value in references]
        connections_drop = self.panel_capability_state(
            PanelApiCapability.CONNECTIONS_DROP,
            compatibility,
        )
        operation = (
            PanelApiOperation.USER_CONNECTIONS_DROP_V3
            if connections_drop is True
            or (
                connections_drop is None and all(value is not None for value in initial_numeric_ids)
            )
            else PanelApiOperation.USER_CONNECTIONS_DROP_V2
        )
        if not await self.panel_mutation_allowed(operation, compatibility=compatibility):
            return False
        resolved = [
            await self.resolve_panel_user_reference(
                reference,
                operation,
                compatibility=compatibility,
            )
            for reference in references
        ]
        if any(value is None for value in resolved):
            return False
        user_references = [value for value in resolved if value is not None]
        numeric_ids = [numeric_panel_user_id(value) for value in user_references]
        target_nodes: dict[str, Any] = (
            {
                "target": "specificNodes",
                "nodeUuids": list(
                    dict.fromkeys(str(uuid) for uuid in node_uuids if str(uuid).strip())
                ),
            }
            if node_uuids
            else {"target": "allNodes"}
        )
        identities: list[str | int] = []
        if operation is PanelApiOperation.USER_CONNECTIONS_DROP_V3:
            if any(value is None for value in numeric_ids):
                return False
            endpoint = "/connections/drop"
            selector = "userIds"
            identities.extend(value for value in numeric_ids if value is not None)
        else:
            if any(value is not None for value in numeric_ids):
                logger.error("Cannot drop connections for mixed Remnawave user generations.")
                return False
            endpoint = "/ip-control/drop-connections"
            selector = "userUuids"
            identities.extend(user_references)

        chunk_size = 500
        for offset in range(0, len(identities), chunk_size):
            chunk = identities[offset : offset + chunk_size]
            payload = {
                "dropBy": {"by": selector, selector: chunk},
                "targetNodes": target_nodes,
            }
            response_data = await self._request(
                "POST",
                endpoint,
                operation=operation,
                json=payload,
                log_full_response=log_response,
            )
            if response_data and not response_data.get("error"):
                continue

            error_code = self._panel_response_error_code(response_data)
            if error_code == "A219":
                # No connected node matched the request: nothing to tear down.
                logger.debug("Panel has no connected nodes for a connection-drop batch.")
                return False
            if self._is_missing_endpoint_response(response_data):
                self.remember_panel_capability(
                    PanelApiCapability.CONNECTIONS_DROP,
                    operation is not PanelApiOperation.USER_CONNECTIONS_DROP_V3,
                )
                logger.warning(
                    "Panel does not expose %s; live sessions stay until nodes drop them.",
                    endpoint,
                )
                return False
            logger.error(
                "Failed to drop a %s-user connection batch on panel. Response: %s",
                len(chunk),
                response_data if not log_response else "(logged above)",
            )
            return False

        self.remember_panel_capability(
            PanelApiCapability.CONNECTIONS_DROP,
            operation is PanelApiOperation.USER_CONNECTIONS_DROP_V3,
        )
        logger.info(
            "metric panel_connection_drop users=%s chunks=%s nodes=%s",
            len(identities),
            (len(identities) + chunk_size - 1) // chunk_size,
            len(node_uuids) if node_uuids else "all",
        )
        return True
