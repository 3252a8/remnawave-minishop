import logging
from typing import TYPE_CHECKING, Any

from bot.services.panel_api_compat import normalize_panel_user
from bot.services.panel_api_contracts import PanelApiOperation

logger = logging.getLogger(__name__)


class PanelApiUserMutationMixin:
    if TYPE_CHECKING:

        async def get_panel_api_compatibility(self) -> Any: ...
        async def panel_mutation_allowed(self, *args: Any, **kwargs: Any) -> bool: ...
        async def resolve_panel_user_reference(self, *args: Any, **kwargs: Any) -> Any: ...
        async def _request(self, *args: Any, **kwargs: Any) -> Any: ...
        def _panel_response_error_code(self, response: Any) -> Any: ...
        def _is_user_not_found_response(self, response: Any) -> bool: ...
        async def _invalidate_user_cache(self, *args: Any, **kwargs: Any) -> None: ...
        async def _invalidate_devices_cache(self, *args: Any, **kwargs: Any) -> None: ...
        async def _invalidate_all_users_cache(self) -> None: ...
        async def get_user_by_uuid(self, *args: Any, **kwargs: Any) -> Any: ...
        async def get_user_devices(self, *args: Any, **kwargs: Any) -> Any: ...
        async def disconnect_device(self, *args: Any, **kwargs: Any) -> bool: ...

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

    async def reset_user_hwid_devices(self, user_uuid: str) -> bool:
        """Clear recorded devices while preserving the link, limit and entitlements.

        Deletions use the panel compatibility layer. Failure may mean only some
        devices were cleared, so discard the device snapshot even on failure.
        """
        try:
            return await self._disconnect_all_hwid_devices(user_uuid)
        finally:
            await self._invalidate_devices_cache(user_uuid)

    async def _disconnect_all_hwid_devices(self, user_uuid: str) -> bool:
        await self._invalidate_devices_cache(user_uuid)
        devices = await self.get_user_devices(user_uuid)
        if devices is None:
            logger.error(
                "Cannot clear registered devices for user %s: failed to read registered devices.",
                user_uuid,
            )
            return False

        hwids: list[str] = []
        seen: set[str] = set()
        for device in devices:
            hwid = str(device.get("hwid") or "").strip()
            if not hwid:
                logger.error(
                    "Cannot clear registered devices for user %s: panel returned a device "
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
                    "Cannot clear registered devices for user %s: failed to clear all "
                    "registered devices.",
                    user_uuid,
                )
                return False

        return True
