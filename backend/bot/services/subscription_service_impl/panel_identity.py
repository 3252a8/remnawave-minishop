import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.text_sanitizer import panel_description_from_profile
from config.traffic_strategy import normalize_traffic_limit_strategy
from db.dal import user_dal
from db.models import User

from ._typing import SubscriptionServiceMixinContract


class PanelIdentityMixin(SubscriptionServiceMixinContract):
    @staticmethod
    def _coerce_panel_int(value: Any) -> Optional[int]:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _extract_panel_traffic_details(
        self, panel_user_data: Dict[str, Any]
    ) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        traffic_stats = panel_user_data.get("userTraffic") or {}
        used = traffic_stats.get("usedTrafficBytes")
        if used is None:
            used = panel_user_data.get("usedTrafficBytes")
        limit = panel_user_data.get("trafficLimitBytes")
        strategy = panel_user_data.get("trafficLimitStrategy")
        if strategy is None:
            strategy = traffic_stats.get("trafficLimitStrategy")
        return self._coerce_panel_int(used), self._coerce_panel_int(limit), strategy

    def _extract_lifetime_used_traffic(self, panel_user_data: Dict[str, Any]) -> Optional[int]:
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
                logging.error(
                    f"Failed to notify admin {admin_id} about panel user creation failure: {e}"
                )

    def _telegram_id_for_panel(self, db_user: User) -> Optional[int]:
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

    def _panel_identity_payload_for_user(self, db_user: User) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        telegram_id = self._telegram_id_for_panel(db_user)
        if telegram_id:
            payload["telegramId"] = telegram_id
        if db_user.email:
            payload["email"] = db_user.email
        return payload

    async def _get_or_create_panel_user_link_details(
        self, session: AsyncSession, user_id: int, db_user: Optional[User] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str], bool]:
        if not db_user:
            db_user = await user_dal.get_user_by_id(session, user_id)

        if not db_user:
            logging.error(
                f"_get_or_create_panel_user_link_details: User {user_id} not found in local DB. Cannot proceed."  # noqa: E501
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
            logging.info(
                f"Found panel user by telegramId {telegram_id_for_panel}: UUID {panel_user_obj_from_api.get('uuid')}, Username: {panel_user_obj_from_api.get('username')}"  # noqa: E501
            )
        elif panel_users_by_tg_id_list and len(panel_users_by_tg_id_list) > 1:
            logging.error(
                f"CRITICAL: Multiple panel users found for telegramId {telegram_id_for_panel}. Manual intervention needed."  # noqa: E501
            )
            return None, None, None, False

        if not panel_user_obj_from_api and db_user.email:
            panel_users_by_email_list = await self.panel_service.get_users_by_filter(
                email=db_user.email
            )
            if panel_users_by_email_list and len(panel_users_by_email_list) == 1:
                panel_user_obj_from_api = panel_users_by_email_list[0]
                logging.info(
                    f"Found panel user by email {db_user.email}: UUID {panel_user_obj_from_api.get('uuid')}, Username: {panel_user_obj_from_api.get('username')}"  # noqa: E501
                )
            elif panel_users_by_email_list and len(panel_users_by_email_list) > 1:
                logging.error(
                    f"CRITICAL: Multiple panel users found for email {db_user.email}. Manual intervention needed."  # noqa: E501
                )
                return None, None, None, False

        if not panel_user_obj_from_api:
            if current_local_panel_uuid:
                logging.info(
                    f"User {user_id} (local panel_uuid: {current_local_panel_uuid}) not found on panel by TG ID. Fetching by panel_uuid."  # noqa: E501
                )
                panel_user_obj_from_api = await self.panel_service.get_user_by_uuid(
                    current_local_panel_uuid
                )
                if not panel_user_obj_from_api:
                    logging.warning(
                        f"Local panel_uuid {current_local_panel_uuid} for TG user {user_id} also not found on panel. User might be deleted from panel or UUID desynced."  # noqa: E501
                    )
                    logging.info(
                        f"Creating new panel user '{panel_username_on_panel_standard}' for TG user {user_id}."  # noqa: E501
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
                logging.info(
                    f"No panel user by TG ID & no local panel_uuid for TG user {user_id}. Creating new panel user '{panel_username_on_panel_standard}'."  # noqa: E501
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
                    logging.warning(
                        f"Panel user '{panel_username_on_panel_standard}' already exists (errorCode A019). Fetching by username."  # noqa: E501
                    )
                    fetched_by_username_list = await self.panel_service.get_users_by_filter(
                        username=panel_username_on_panel_standard
                    )
                    if fetched_by_username_list and len(fetched_by_username_list) == 1:
                        panel_user_obj_from_api = fetched_by_username_list[0]

                if not panel_user_obj_from_api:
                    logging.error(
                        f"Failed to create or link panel user for TG_ID {user_id} with panel username '{panel_username_on_panel_standard}'. Response: {creation_response if 'creation_response' in locals() else 'N/A'}"  # noqa: E501
                    )
                    await self._notify_admin_panel_user_creation_failed(user_id)
                    return None, None, None, False

        if not panel_user_obj_from_api:
            logging.error(
                f"Could not obtain panel user object for TG user {user_id} after all checks."
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
            logging.error(
                f"Panel user object for TG user {user_id} does not contain 'uuid'. Data: {panel_user_obj_from_api}"  # noqa: E501
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
            logging.warning(
                f"Local panel_uuid for user {user_id} ('{current_local_panel_uuid}') "
                f"differs from panel's UUID ('{actual_panel_uuid_from_api}') for their telegramId. "
                f"Will attempt to update local to panel's version."
            )
            needs_local_panel_uuid_update = True

        if needs_local_panel_uuid_update:
            conflicting_user_record = await user_dal.get_user_by_panel_uuid(
                session, actual_panel_uuid_from_api
            )
            if conflicting_user_record and conflicting_user_record.user_id != user_id:
                logging.error(
                    f"CRITICAL CONFLICT: Panel UUID {actual_panel_uuid_from_api} (from panel for TG ID {user_id}) "  # noqa: E501
                    f"is ALREADY LINKED in local DB to a different TG User {conflicting_user_record.user_id}. "  # noqa: E501
                    f"Cannot update panel_user_uuid for user {user_id}. Manual data correction needed."  # noqa: E501
                )

                return None, None, None, False
            else:
                update_data_for_local_user = {"panel_user_uuid": actual_panel_uuid_from_api}

                # Do not overwrite Telegram username with panel username.
                # Only update the local linkage to panel UUID here.
                await user_dal.update_user(session, user_id, update_data_for_local_user)
                db_user.panel_user_uuid = actual_panel_uuid_from_api
                panel_user_created_or_linked_now = True
                current_local_panel_uuid = actual_panel_uuid_from_api
        else:
            pass

        panel_telegram_id_int = None
        if panel_telegram_id_from_api is not None:
            try:
                panel_telegram_id_int = int(panel_telegram_id_from_api)
            except ValueError:
                pass

        if (
            panel_user_obj_from_api
            and current_local_panel_uuid
            and telegram_id_for_panel
            and panel_telegram_id_int != telegram_id_for_panel
        ):
            logging.info(
                f"Panel user {current_local_panel_uuid} has telegramId '{panel_telegram_id_from_api}'. Updating on panel to '{telegram_id_for_panel}'."  # noqa: E501
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
            logging.warning(
                f"No subscriptionUuid or shortUuid found on panel for panel_user_uuid {current_local_panel_uuid} (TG ID: {user_id})."  # noqa: E501
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
        panel_user_uuid: Optional[str] = None,
        expire_at: Optional[datetime] = None,
        status: Optional[str] = None,
        traffic_limit_bytes: Optional[int] = None,
        include_uuid: bool = True,
        traffic_limit_strategy: Optional[str] = None,
        hwid_device_limit: Optional[int] = None,
        include_default_squads: bool = True,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
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
            payload["trafficLimitStrategy"] = normalize_traffic_limit_strategy(
                traffic_limit_strategy or self.settings.USER_TRAFFIC_STRATEGY
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
