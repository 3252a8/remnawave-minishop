import contextlib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.text_sanitizer import panel_description_from_profile
from config.traffic_strategy import normalize_traffic_limit_strategy
from db.dal import user_dal, user_panel_squad_override_dal
from db.models import User

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


class PanelIdentityMixin(SubscriptionServiceMixinContract):
    @staticmethod
    def _coerce_panel_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _extract_panel_traffic_details(
        self, panel_user_data: dict[str, Any]
    ) -> tuple[int | None, int | None, str | None]:
        traffic_stats = panel_user_data.get("userTraffic") or {}
        used = traffic_stats.get("usedTrafficBytes")
        if used is None:
            used = panel_user_data.get("usedTrafficBytes")
        limit = panel_user_data.get("trafficLimitBytes")
        strategy = panel_user_data.get("trafficLimitStrategy")
        if strategy is None:
            strategy = traffic_stats.get("trafficLimitStrategy")
        return self._coerce_panel_int(used), self._coerce_panel_int(limit), strategy

    def _extract_lifetime_used_traffic(self, panel_user_data: dict[str, Any]) -> int | None:
        traffic_stats = panel_user_data.get("userTraffic") or {}
        lifetime = traffic_stats.get("lifetimeUsedTrafficBytes")
        if lifetime is None:
            lifetime = panel_user_data.get("lifetimeUsedTrafficBytes")
        return self._coerce_panel_int(lifetime)

    async def _notify_admin_panel_user_creation_failed(self, user_id: int) -> None:
        if not self.bot or not self.i18n or not self.settings.ADMIN_IDS:
            return
        admin_lang = self.settings.DEFAULT_LANGUAGE
        _adm = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw)
        msg = _adm("admin_panel_user_creation_failed", user_id=user_id)
        for admin_id in self.settings.ADMIN_IDS:
            try:
                await self.bot.send_message(admin_id, msg)
            except Exception as e:
                logger.error(
                    "Failed to notify admin %s about panel user creation failure: %s", admin_id, e
                )

    def _telegram_id_for_panel(self, db_user: User) -> int | None:
        if db_user.telegram_id:
            return int(db_user.telegram_id)
        if db_user.user_id and int(db_user.user_id) > 0:
            return int(db_user.user_id)
        return None

    async def _panel_username_for_user(self, session: AsyncSession, db_user: User) -> str:
        telegram_id = self._telegram_id_for_panel(db_user)
        if telegram_id and int(db_user.user_id) == telegram_id:
            return f"tg_{telegram_id}"
        referral_code = await user_dal.ensure_referral_code(session, db_user)
        return f"em_{referral_code}"

    def _panel_description_for_user(self, db_user: User) -> str:
        return str(
            panel_description_from_profile(
                db_user.username,
                db_user.first_name,
                db_user.last_name,
            )
        )

    def _panel_identity_payload_for_user(self, db_user: User) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        telegram_id = self._telegram_id_for_panel(db_user)
        if telegram_id:
            payload["telegramId"] = telegram_id
        if db_user.email:
            payload["email"] = db_user.email
        return payload

    async def _get_or_create_panel_user_link_details(
        self, session: AsyncSession, user_id: int, db_user: User | None = None
    ) -> tuple[str | None, str | None, str | None, bool]:
        if not db_user:
            db_user = await user_dal.get_user_by_id(session, user_id)

        if not db_user:
            logger.error(
                "_get_or_create_panel_user_link_details: User %s not found in local DB. Cannot "
                "proceed.",
                user_id,
            )
            return None, None, None, False

        current_local_panel_uuid = db_user.panel_user_uuid
        panel_username_on_panel_standard = await self._panel_username_for_user(session, db_user)
        telegram_id_for_panel = self._telegram_id_for_panel(db_user)

        panel_user_obj_from_api = None
        panel_user_created_or_linked_now = False

        panel_users_by_tg_id_list = None
        if telegram_id_for_panel:
            panel_users_by_tg_id_list = await self.panel_service.get_users_by_filter(
                telegram_id=telegram_id_for_panel
            )
        if panel_users_by_tg_id_list and len(panel_users_by_tg_id_list) == 1:
            panel_user_obj_from_api = panel_users_by_tg_id_list[0]
            logger.info(
                "Found panel user by telegramId %s: UUID %s, Username: %s",
                telegram_id_for_panel,
                panel_user_obj_from_api.get("uuid"),
                panel_user_obj_from_api.get("username"),
            )
        elif panel_users_by_tg_id_list and len(panel_users_by_tg_id_list) > 1:
            logger.error(
                "CRITICAL: Multiple panel users found for telegramId %s. Manual intervention "
                "needed.",
                telegram_id_for_panel,
            )
            return None, None, None, False

        if not panel_user_obj_from_api and db_user.email:
            panel_users_by_email_list = await self.panel_service.get_users_by_filter(
                email=db_user.email
            )
            if panel_users_by_email_list and len(panel_users_by_email_list) == 1:
                panel_user_obj_from_api = panel_users_by_email_list[0]
                logger.info(
                    "Found panel user by email %s: UUID %s, Username: %s",
                    db_user.email,
                    panel_user_obj_from_api.get("uuid"),
                    panel_user_obj_from_api.get("username"),
                )
            elif panel_users_by_email_list and len(panel_users_by_email_list) > 1:
                logger.error(
                    "CRITICAL: Multiple panel users found for email %s. Manual intervention "
                    "needed.",
                    db_user.email,
                )
                return None, None, None, False

        if not panel_user_obj_from_api:
            if current_local_panel_uuid:
                logger.info(
                    "User %s (local panel_uuid: %s) not found on panel by TG ID. Fetching by "
                    "panel_uuid.",
                    user_id,
                    current_local_panel_uuid,
                )
                panel_user_obj_from_api = await self.panel_service.get_user_by_uuid(
                    current_local_panel_uuid
                )
                if not panel_user_obj_from_api:
                    logger.warning(
                        "Local panel_uuid %s for TG user %s also not found on panel. User might be "
                        "deleted from panel or UUID desynced.",
                        current_local_panel_uuid,
                        user_id,
                    )
                    logger.info(
                        "Creating new panel user '%s' for TG user %s.",
                        panel_username_on_panel_standard,
                        user_id,
                    )
                    creation_response = await self.panel_service.create_panel_user(
                        username_on_panel=panel_username_on_panel_standard,
                        telegram_id=telegram_id_for_panel,
                        email=db_user.email,
                        description=self._panel_description_for_user(db_user),
                        specific_squad_uuids=self.settings.parsed_user_squad_uuids,
                        external_squad_uuid=self.settings.parsed_user_external_squad_uuid,
                        default_traffic_limit_bytes=self.settings.user_traffic_limit_bytes,
                        default_traffic_limit_strategy=self.settings.USER_TRAFFIC_STRATEGY,
                    )
                    if (
                        creation_response
                        and not creation_response.get("error")
                        and creation_response.get("response")
                    ):
                        panel_user_obj_from_api = creation_response.get("response")
                        panel_user_created_or_linked_now = True
                    else:
                        await self._notify_admin_panel_user_creation_failed(user_id)
                        return None, None, None, False

            else:
                logger.info(
                    "No panel user by TG ID & no local panel_uuid for TG user %s. Creating new "
                    "panel user '%s'.",
                    user_id,
                    panel_username_on_panel_standard,
                )
                creation_response = await self.panel_service.create_panel_user(
                    username_on_panel=panel_username_on_panel_standard,
                    telegram_id=telegram_id_for_panel,
                    email=db_user.email,
                    description=self._panel_description_for_user(db_user),
                    specific_squad_uuids=self.settings.parsed_user_squad_uuids,
                    external_squad_uuid=self.settings.parsed_user_external_squad_uuid,
                    default_traffic_limit_bytes=self.settings.user_traffic_limit_bytes,
                    default_traffic_limit_strategy=self.settings.USER_TRAFFIC_STRATEGY,
                )
                if (
                    creation_response
                    and not creation_response.get("error")
                    and creation_response.get("response")
                ):
                    panel_user_obj_from_api = creation_response.get("response")
                    panel_user_created_or_linked_now = True

                elif creation_response and creation_response.get("errorCode") == "A019":
                    logger.warning(
                        "Panel user '%s' already exists (errorCode A019). Fetching by username.",
                        panel_username_on_panel_standard,
                    )
                    fetched_by_username_list = await self.panel_service.get_users_by_filter(
                        username=panel_username_on_panel_standard
                    )
                    if fetched_by_username_list and len(fetched_by_username_list) == 1:
                        panel_user_obj_from_api = fetched_by_username_list[0]

                if not panel_user_obj_from_api:
                    logger.error(
                        "Failed to create or link panel user for TG_ID %s with panel username "
                        "'%s'. Response: %s",
                        user_id,
                        panel_username_on_panel_standard,
                        creation_response if "creation_response" in locals() else "N/A",
                    )
                    await self._notify_admin_panel_user_creation_failed(user_id)
                    return None, None, None, False

        if not panel_user_obj_from_api:
            logger.error(
                "Could not obtain panel user object for TG user %s after all checks.", user_id
            )

            return (
                current_local_panel_uuid if current_local_panel_uuid else None,
                None,
                None,
                panel_user_created_or_linked_now,
            )

        actual_panel_uuid_from_api = panel_user_obj_from_api.get("uuid")
        panel_telegram_id_from_api = panel_user_obj_from_api.get("telegramId")

        if not actual_panel_uuid_from_api:
            logger.error(
                "Panel user object for TG user %s does not contain 'uuid'. Data: %s",
                user_id,
                panel_user_obj_from_api,
            )
            return (
                current_local_panel_uuid,
                None,
                None,
                panel_user_created_or_linked_now,
            )

        needs_local_panel_uuid_update = False
        if current_local_panel_uuid is None and actual_panel_uuid_from_api:
            needs_local_panel_uuid_update = True
        elif (
            current_local_panel_uuid is not None
            and current_local_panel_uuid != actual_panel_uuid_from_api
        ):
            logger.warning(
                "Local panel_uuid for user %s ('%s') differs from panel's UUID ('%s') for their "
                "telegramId. Will attempt to update local to panel's version.",
                user_id,
                current_local_panel_uuid,
                actual_panel_uuid_from_api,
            )
            needs_local_panel_uuid_update = True

        if needs_local_panel_uuid_update:
            conflicting_user_record = await user_dal.get_user_by_panel_uuid(
                session, actual_panel_uuid_from_api
            )
            if conflicting_user_record and conflicting_user_record.user_id != user_id:
                logger.error(
                    "CRITICAL CONFLICT: Panel UUID %s (from panel for TG ID %s) is ALREADY LINKED "
                    "in local DB to a different TG User %s. Cannot update panel_user_uuid for user "
                    "%s. Manual data correction needed.",
                    actual_panel_uuid_from_api,
                    user_id,
                    conflicting_user_record.user_id,
                    user_id,
                )

                return None, None, None, False
            else:
                previous_panel_uuid = current_local_panel_uuid
                update_data_for_local_user = {"panel_user_uuid": actual_panel_uuid_from_api}

                # Do not overwrite Telegram username with panel username.
                # Only update the local linkage to panel UUID here.
                await user_dal.update_user(session, user_id, update_data_for_local_user)
                if previous_panel_uuid:
                    moved_overrides = await user_panel_squad_override_dal.merge_panel_user_uuid(
                        session,
                        user_id=user_id,
                        old_panel_user_uuid=previous_panel_uuid,
                        new_panel_user_uuid=actual_panel_uuid_from_api,
                    )
                    if moved_overrides:
                        logger.info(
                            "Moved %s panel squad override records for user %s from panel UUID "
                            "%s to %s.",
                            moved_overrides,
                            user_id,
                            previous_panel_uuid,
                            actual_panel_uuid_from_api,
                        )
                db_user.panel_user_uuid = actual_panel_uuid_from_api
                panel_user_created_or_linked_now = True
                current_local_panel_uuid = actual_panel_uuid_from_api
        else:
            pass

        panel_telegram_id_int = None
        if panel_telegram_id_from_api is not None:
            with contextlib.suppress(ValueError):
                panel_telegram_id_int = int(panel_telegram_id_from_api)

        if (
            panel_user_obj_from_api
            and current_local_panel_uuid
            and telegram_id_for_panel
            and panel_telegram_id_int != telegram_id_for_panel
        ):
            logger.info(
                "Panel user %s has telegramId '%s'. Updating on panel to '%s'.",
                current_local_panel_uuid,
                panel_telegram_id_from_api,
                telegram_id_for_panel,
            )
            await self.panel_service.update_user_details_on_panel(
                current_local_panel_uuid,
                self._panel_identity_payload_for_user(db_user),
            )

        panel_sub_link_id = panel_user_obj_from_api.get(
            "subscriptionUuid"
        ) or panel_user_obj_from_api.get("shortUuid")
        panel_short_uuid = panel_user_obj_from_api.get("shortUuid")

        if not panel_sub_link_id and current_local_panel_uuid:
            logger.warning(
                "No subscriptionUuid or shortUuid found on panel for panel_user_uuid %s (TG ID: "
                "%s).",
                current_local_panel_uuid,
                user_id,
            )

        return (
            current_local_panel_uuid,
            panel_sub_link_id,
            panel_short_uuid,
            panel_user_created_or_linked_now,
        )

    def _build_panel_update_payload(
        self,
        *,
        panel_user_uuid: str | None = None,
        expire_at: datetime | None = None,
        status: str | None = None,
        traffic_limit_bytes: int | None = None,
        include_uuid: bool = True,
        traffic_limit_strategy: str | None = None,
        hwid_device_limit: int | None = None,
        include_default_squads: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if include_uuid and panel_user_uuid:
            payload["uuid"] = panel_user_uuid
        if expire_at is not None:
            payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            )
        if status is not None:
            payload["status"] = status
        if traffic_limit_bytes is not None:
            payload["trafficLimitBytes"] = traffic_limit_bytes
            if traffic_limit_strategy is not None:
                payload["trafficLimitStrategy"] = normalize_traffic_limit_strategy(
                    traffic_limit_strategy
                )
        if hwid_device_limit is not None:
            try:
                hwid_limit_int = int(hwid_device_limit)
                if hwid_limit_int >= 0:
                    payload["hwidDeviceLimit"] = hwid_limit_int
            except (TypeError, ValueError):
                pass
        if include_default_squads:
            if self.settings.parsed_user_squad_uuids:
                payload["activeInternalSquads"] = self.settings.parsed_user_squad_uuids
            if self.settings.parsed_user_external_squad_uuid:
                payload["externalSquadUuid"] = self.settings.parsed_user_external_squad_uuid
        return payload
