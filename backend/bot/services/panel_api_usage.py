"""Version-aware aggregate bandwidth reads used by premium accounting."""

import logging
from typing import TYPE_CHECKING, Any

from bot.services.panel_api_compat import PanelApiCompatibility
from bot.services.panel_api_contracts import PanelApiCapability, PanelApiOperation

logger = logging.getLogger(__name__)


def _response_dict(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    response = payload.get("response")
    return response if isinstance(response, dict) else None


def _route_is_unavailable(payload: dict[str, Any] | None) -> bool:
    return isinstance(payload, dict) and payload.get("status_code") in {404, 405}


class PanelApiUsageMixin:
    """Expose the two multi-node contracts without hiding their different semantics."""

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

    async def get_multi_node_user_usage(
        self,
        node_uuids: list[str],
        *,
        start: str,
        end: str,
        min_total_bytes: int = 0,
    ) -> dict[str, Any] | None:
        """Return Remnawave 3.x per-node user totals for one date range."""
        nodes = list(
            dict.fromkeys(str(value).strip() for value in node_uuids if str(value).strip())
        )
        if not nodes:
            return {"nodes": []}
        compatibility = await self.get_panel_api_compatibility()
        capability = PanelApiCapability.MULTI_NODE_USAGE
        if self.panel_capability_state(capability, compatibility) is False:
            return None
        response_data = await self._request(
            "POST",
            "/bandwidth-stats/nodes/usage",
            operation=PanelApiOperation.NODES_USER_USAGE,
            params={
                "start": start,
                "end": end,
                "minTotalBytes": max(0, int(min_total_bytes)),
            },
            json={"nodesUuids": nodes},
            log_full_response=False,
        )
        response = _response_dict(response_data)
        response_nodes = response.get("nodes") if response is not None else None
        if isinstance(response_nodes, list) and all(
            isinstance(node, dict) and isinstance(node.get("users", []), list)
            for node in response_nodes
        ):
            self.remember_panel_capability(capability, True)
            return response
        if _route_is_unavailable(response_data) or response is not None:
            self.remember_panel_capability(capability, False)
        logger.warning(
            "Remnawave multi-node usage is unavailable or returned an unsupported shape."
        )
        return None

    async def get_multi_node_users_bandwidth_stats(
        self,
        node_uuids: list[str],
        *,
        start: str,
        end: str,
        top_users_limit: int,
    ) -> dict[str, Any] | None:
        """Return the 2.8.1-compatible aggregate top-users response for many nodes."""
        nodes = list(
            dict.fromkeys(str(value).strip() for value in node_uuids if str(value).strip())
        )
        if not nodes:
            return {"topUsers": []}
        compatibility = await self.get_panel_api_compatibility()
        capability = PanelApiCapability.MULTI_NODE_TOP_USERS
        if self.panel_capability_state(capability, compatibility) is False:
            return None
        response_data = await self._request(
            "POST",
            "/bandwidth-stats/nodes/users",
            operation=PanelApiOperation.NODES_USER_BANDWIDTH,
            params={
                "start": start,
                "end": end,
                "topUsersLimit": max(1, int(top_users_limit)),
            },
            json={"nodesUuids": nodes},
            log_full_response=False,
        )
        response = _response_dict(response_data)
        top_users = response.get("topUsers") if response is not None else None
        if isinstance(top_users, list):
            self.remember_panel_capability(capability, True)
            return response
        if _route_is_unavailable(response_data) or response is not None:
            self.remember_panel_capability(capability, False)
        logger.warning(
            "Remnawave aggregate multi-node bandwidth is unavailable or returned an "
            "unsupported shape."
        )
        return None
