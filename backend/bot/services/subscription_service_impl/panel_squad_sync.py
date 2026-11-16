import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PanelSquadSyncMixin:
    panel_service: Any

    if TYPE_CHECKING:

        async def build_effective_panel_squad_fields(
            self, *args: Any, **kwargs: Any
        ) -> dict[str, Any]: ...
        async def _confirmed_panel_entitlement(self, *args: Any, **kwargs: Any) -> Any: ...

    async def _sync_panel_squads_if_needed(
        self,
        panel_user_uuid: str,
        desired_squads: list[str],
        *,
        user_id: int,
        source: str,
        session: AsyncSession | None = None,
    ) -> bool:
        panel_user: dict[str, Any] | None = None
        try:
            panel_user = await self.panel_service.get_user_by_uuid(
                panel_user_uuid,
                log_response=False,
                use_cache=False,
            )
        except Exception:
            logger.exception(
                "Failed to fetch panel user %s before premium squad update", panel_user_uuid
            )
        current_known, current_set = self._panel_active_squad_uuid_set(panel_user)
        payload: dict[str, Any] = {"uuid": panel_user_uuid, "activeInternalSquads": desired_squads}
        if session is not None:
            payload = {
                "uuid": panel_user_uuid,
                **(
                    await self.build_effective_panel_squad_fields(
                        session,
                        user_id=user_id,
                        panel_user_uuid=panel_user_uuid,
                        managed_internal_squads=desired_squads,
                        panel_user_snapshot=panel_user,
                        discover_panel_overrides=True,
                        fetch_panel_snapshot=False,
                        include_internal_squads=True,
                        source=source,
                    )
                ),
            }
        desired_set = self._panel_squad_uuid_set(
            payload.get("activeInternalSquads", desired_squads)
        )
        if current_known and current_set == desired_set:
            return True
        self._log_panel_squad_patch(
            source=source,
            user_id=user_id,
            panel_uuid=panel_user_uuid,
            current_set=current_set,
            desired_set=desired_set,
        )
        updated_panel = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid,
            payload,
            log_response=False,
        )
        confirmed = await self._confirmed_panel_entitlement(
            panel_user_uuid,
            updated_panel,
            payload,
            source=source,
        )
        return confirmed is not None

    async def _panel_squads_match(
        self,
        panel_user_uuid: str,
        desired_squads: list[str],
    ) -> tuple[bool | None, set[str] | None]:
        try:
            panel_user = await self.panel_service.get_user_by_uuid(
                panel_user_uuid,
                log_response=False,
            )
        except Exception:
            logger.exception(
                "Failed to fetch panel user %s before premium squad update", panel_user_uuid
            )
            return None, None
        current_known, current_set = self._panel_active_squad_uuid_set(panel_user)
        if not current_known:
            return None, current_set
        return current_set == self._panel_squad_uuid_set(desired_squads), current_set

    @classmethod
    def _panel_active_squad_uuid_set(
        cls,
        panel_user: dict | None,
    ) -> tuple[bool, set[str]]:
        if not isinstance(panel_user, dict):
            return False, set()
        for key in (
            "activeInternalSquads",
            "active_internal_squads",
            "activeInternalSquadUuids",
            "active_internal_squad_uuids",
        ):
            if key in panel_user:
                return True, cls._panel_squad_uuid_set(panel_user.get(key))
        return False, set()

    @staticmethod
    def _panel_squad_uuid_set(raw: object) -> set[str]:
        if not isinstance(raw, (list, tuple, set)):
            return set()
        out: set[str] = set()
        for item in raw:
            if isinstance(item, dict):
                nested_squad = item.get("internalSquad") or item.get("squad")
                if not isinstance(nested_squad, dict):
                    nested_squad = {}
                squad_uuid = (
                    item.get("uuid")
                    or item.get("internalSquadUuid")
                    or item.get("squadUuid")
                    or nested_squad.get("uuid")
                )
                if squad_uuid:
                    out.add(str(squad_uuid))
            elif item:
                out.add(str(item))
        return out

    def _log_panel_squad_patch(
        self,
        *,
        source: str,
        user_id: int,
        panel_uuid: str,
        current_set: set[str] | None,
        desired_set: set[str],
    ) -> None:
        logger.info(
            "Sync panel PATCH: source=%s user_id=%s telegram_id=%s panel_uuid=%s "
            "panel_view=full_fetch reasons=activeInternalSquads_mismatch "
            "fields=activeInternalSquads payload_fields=activeInternalSquads changes=%s",
            source,
            user_id,
            user_id,
            panel_uuid,
            f"activeInternalSquads:{self._format_panel_squad_set(current_set)}->{self._format_panel_squad_set(desired_set)}",
        )

    @staticmethod
    def _format_panel_squad_set(value: set[str] | None) -> str:
        if value is None:
            return "missing"
        values = sorted(str(item) for item in value)
        preview = ",".join(values[:4])
        suffix = ",..." if len(values) > 4 else ""
        text = f"[{len(values)}:{preview}{suffix}]"
        return f"{text[:93]}..." if len(text) > 96 else text
