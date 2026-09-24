import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.account_roles import ADMIN_ROLES
from bot.services.panel_identity_match import (
    panel_candidate_matches_account,
    panel_origin_fingerprint,
)
from bot.services.panel_tariff_tags import (
    PanelTariffTagPlan,
    configured_tariff_tags,
    normalize_panel_tag,
    panel_tariff_tag_for_key,
    plan_panel_tariff_tag,
)
from bot.services.user_email_notifications import send_user_notification_email
from bot.utils.text_sanitizer import panel_description_from_profile
from config.traffic_strategy import normalize_traffic_limit_strategy
from db.auth_models import AccountRole
from db.dal import user_dal, user_panel_squad_override_dal
from db.models import User

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PanelUserCreateOptions:
    default_expire_days: int
    default_traffic_limit_bytes: int
    default_traffic_limit_strategy: str
    expire_at: datetime | None = None
    hwid_device_limit: int | None = None
    specific_squad_uuids: tuple[str, ...] = ()
    external_squad_uuid: str | None = None
    # Canonical tariff key; map it with the catalog before sending it to Remnawave.
    tag: str | None = None
    is_trial: bool = False


@dataclass(frozen=True, slots=True)
class PanelUserLink:
    """Local link to a panel user.

    ``panel_user_uuid`` is a legacy field name: it stores a UUID for panel
    2.8.x and a decimal-string user id for panel 3.x.  Keeping the name avoids
    a disruptive local schema migration while the API boundary translates it.
    """

    panel_user_uuid: str | None
    panel_subscription_uuid: str | None
    panel_short_uuid: str | None
    panel_user_created_now: bool
    local_link_updated_now: bool
    panel_user: dict[str, Any] | None

    def legacy_details(self) -> tuple[str | None, str | None, str | None, bool]:
        return (
            self.panel_user_uuid,
            self.panel_subscription_uuid,
            self.panel_short_uuid,
            self.panel_user_created_now,
        )


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

    async def _notify_admin_panel_user_creation_failed(
        self, session: AsyncSession, user_id: int
    ) -> None:
        admin_lang = self.settings.DEFAULT_LANGUAGE
        _adm = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        msg = _adm("admin_panel_user_creation_failed", user_id=user_id)
        admins = (
            (
                await session.execute(
                    select(User)
                    .join(AccountRole, AccountRole.user_id == User.user_id)
                    .where(AccountRole.role.in_(ADMIN_ROLES), AccountRole.revoked_at.is_(None))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        for admin in admins:
            if self.bot and admin.telegram_id:
                try:
                    await self.bot.send_message(int(admin.telegram_id), msg)
                except Exception:
                    logger.exception("Failed to notify admin %s in Telegram", admin.user_id)
            await send_user_notification_email(
                settings=self.settings,
                i18n=self.i18n,
                user=admin,
                subject_key="admin_panel_user_creation_failed",
                subject_kwargs={"user_id": user_id},
                message_text=msg,
            )

    def _telegram_id_for_panel(self, db_user: User) -> int | None:
        if db_user.telegram_id:
            return int(db_user.telegram_id)
        return None

    async def _panel_username_for_user(self, session: AsyncSession, db_user: User) -> str:
        if not db_user.minishop_id:
            await session.flush()
            await session.refresh(db_user, attribute_names=["minishop_id"])
        return str(db_user.minishop_id)

    def _panel_description_for_user(self, db_user: User) -> str:
        description = str(
            panel_description_from_profile(
                db_user.username,
                db_user.first_name,
                db_user.last_name,
            )
        )
        if db_user.panel_username and db_user.panel_username != db_user.minishop_id:
            return f"{description[:200]} | {db_user.minishop_id}"
        return description

    def _panel_identity_payload_for_user(self, db_user: User) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        telegram_id = self._telegram_id_for_panel(db_user)
        if telegram_id:
            payload["telegramId"] = telegram_id
        if db_user.email:
            payload["email"] = db_user.email
        return payload

    def _plan_panel_tariff_tag(
        self,
        db_user: User,
        panel_user: dict[str, Any] | None,
        desired_tag: str | None,
        *,
        source: str,
        is_trial: bool = False,
    ) -> PanelTariffTagPlan:
        tariffs_config = getattr(self.settings, "tariffs_config", None)
        plan = plan_panel_tariff_tag(
            current_tag=panel_user.get("tag") if isinstance(panel_user, dict) else None,
            managed_tag=getattr(db_user, "managed_panel_tariff_tag", None),
            desired_tag=panel_tariff_tag_for_key(desired_tag, tariffs_config, is_trial=is_trial),
            known_tariff_tags=configured_tariff_tags(tariffs_config),
        )
        if not plan.allowed:
            logger.warning(
                "Preserving external Remnawave tag for user %s during %s: current_tag=%r "
                "desired_tariff_tag=%r",
                db_user.user_id,
                source,
                plan.current_tag,
                plan.desired_tag,
            )
            db_user.managed_panel_tariff_tag = None
        return plan

    @staticmethod
    def _remember_confirmed_panel_tariff_tag(
        db_user: User,
        plan: PanelTariffTagPlan,
        confirmed_panel_user: dict[str, Any] | None,
    ) -> None:
        if not plan.allowed:
            return
        confirmed_tag = normalize_panel_tag(
            confirmed_panel_user.get("tag") if isinstance(confirmed_panel_user, dict) else None
        )
        if confirmed_tag == plan.desired_tag:
            db_user.managed_panel_tariff_tag = plan.managed_tag_after

    async def _get_or_create_panel_user_link(
        self,
        session: AsyncSession,
        user_id: int,
        db_user: User | None = None,
        *,
        create_options: PanelUserCreateOptions | None = None,
    ) -> PanelUserLink:
        if not db_user:
            db_user = await user_dal.get_user_by_id(session, user_id)

        if not db_user:
            logger.error(
                "_get_or_create_panel_user_link_details: User %s not found in local DB. Cannot "
                "proceed.",
                user_id,
            )
            return PanelUserLink(None, None, None, False, False, None)

        if create_options is None:
            create_options = PanelUserCreateOptions(
                default_expire_days=1,
                default_traffic_limit_bytes=self.settings.user_traffic_limit_bytes,
                default_traffic_limit_strategy=self.settings.USER_TRAFFIC_STRATEGY,
                specific_squad_uuids=tuple(self.settings.parsed_user_squad_uuids or ()),
                external_squad_uuid=self.settings.parsed_user_external_squad_uuid,
            )

        # Creation and later reconciliation must use the same collision-aware mapping.
        creation_tag = panel_tariff_tag_for_key(
            create_options.tag,
            getattr(self.settings, "tariffs_config", None),
            is_trial=create_options.is_trial,
        )
        current_local_panel_uuid = db_user.panel_user_uuid
        current_panel_origin = panel_origin_fingerprint(
            getattr(self.settings, "PANEL_API_URL", None)
        )
        if getattr(db_user, "panel_origin", None) and db_user.panel_origin != current_panel_origin:
            logger.error(
                "Panel origin changed for account %s; manual reconciliation required",
                user_id,
            )
            return PanelUserLink(None, None, None, False, False, None)
        panel_username_on_panel_standard = await self._panel_username_for_user(session, db_user)
        telegram_id_for_panel = self._telegram_id_for_panel(db_user)

        panel_user_obj_from_api = None
        panel_user_created_now = False
        local_link_updated_now = False
        identity_lookup_failed = False

        panel_users_by_tg_id_list = None
        if current_local_panel_uuid:
            lookup_method = getattr(self.panel_service, "get_user_by_uuid_lookup", None)
            if callable(lookup_method):
                lookup = await lookup_method(current_local_panel_uuid)
                if isinstance(lookup, dict) and lookup.get("ok"):
                    candidate = lookup.get("user")
                    if isinstance(candidate, dict):
                        panel_user_obj_from_api = candidate
            else:
                panel_user_obj_from_api = await self.panel_service.get_user_by_uuid(
                    current_local_panel_uuid
                )

        if not panel_user_obj_from_api and current_local_panel_uuid:
            legacy_names: list[str] = []
            if db_user.panel_username:
                legacy_names.append(str(db_user.panel_username))
            for legacy_name in dict.fromkeys(legacy_names):
                matches = await self.panel_service.get_users_by_filter(username=legacy_name)
                if matches is None:
                    identity_lookup_failed = True
                    continue
                if len(matches) == 1:
                    panel_user_obj_from_api = matches[0]
                    break
                if len(matches) > 1:
                    logger.error("Ambiguous legacy panel username for account %s", user_id)
                    return PanelUserLink(None, None, None, False, False, None)

        if not panel_user_obj_from_api and current_local_panel_uuid and telegram_id_for_panel:
            panel_users_by_tg_id_list = await self.panel_service.get_users_by_filter(
                telegram_id=telegram_id_for_panel
            )
            identity_lookup_failed = panel_users_by_tg_id_list is None
        if panel_users_by_tg_id_list and len(panel_users_by_tg_id_list) == 1:
            panel_user_obj_from_api = panel_users_by_tg_id_list[0]
            logger.info(
                "Found panel user by telegramId %s: UUID %s, Username: %s",
                telegram_id_for_panel,
                panel_user_obj_from_api.get("uuid"),
                panel_user_obj_from_api.get("username"),
            )
        elif panel_users_by_tg_id_list and len(panel_users_by_tg_id_list) > 1:
            locally_linked_matches = [
                candidate
                for candidate in panel_users_by_tg_id_list
                if current_local_panel_uuid
                and str(candidate.get("uuid") or "") == str(current_local_panel_uuid)
            ]
            if len(locally_linked_matches) == 1:
                panel_user_obj_from_api = locally_linked_matches[0]
                logger.warning(
                    "Multiple panel users found for telegramId %s; using the existing local "
                    "panel link for user %s.",
                    telegram_id_for_panel,
                    user_id,
                )
            else:
                logger.error(
                    "CRITICAL: Multiple panel users found for telegramId %s without one "
                    "unambiguous existing local link. Manual intervention needed.",
                    telegram_id_for_panel,
                )
                return PanelUserLink(None, None, None, False, False, None)

        if not panel_user_obj_from_api and current_local_panel_uuid and db_user.email:
            panel_users_by_email_list = await self.panel_service.get_users_by_filter(
                email=db_user.email
            )
            identity_lookup_failed = identity_lookup_failed or panel_users_by_email_list is None
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
                return PanelUserLink(None, None, None, False, False, None)

        if not panel_user_obj_from_api:
            # The deterministic Mini Shop username survives Remnawave's 3.0
            # UUID -> numeric id migration.  Check it before a stale local UUID
            # so users without Telegram/email identity are relinked, not cloned.
            panel_users_by_username = await self.panel_service.get_users_by_filter(
                username=panel_username_on_panel_standard
            )
            identity_lookup_failed = identity_lookup_failed or panel_users_by_username is None
            if panel_users_by_username and len(panel_users_by_username) == 1:
                candidate = panel_users_by_username[0]
                if not current_local_panel_uuid:
                    candidate_telegram_id = self._coerce_panel_int(candidate.get("telegramId"))
                    matching_telegram = bool(
                        telegram_id_for_panel and candidate_telegram_id == telegram_id_for_panel
                    )
                    matching_verified_email = bool(
                        getattr(db_user, "email_verified_at", None)
                        and db_user.email
                        and str(candidate.get("email") or "").strip().lower()
                        == str(db_user.email).strip().lower()
                    )
                    candidate_uuid = str(candidate.get("uuid") or "")
                    linked_account = (
                        await user_dal.get_user_by_panel_uuid(session, candidate_uuid)
                        if candidate_uuid
                        else None
                    )
                    if (
                        not candidate_uuid
                        or not (matching_telegram or matching_verified_email)
                        or (linked_account and linked_account.user_id != user_id)
                    ):
                        logger.error(
                            "Panel username collision requires reconciliation for %s", user_id
                        )
                        return PanelUserLink(None, None, None, False, False, None)
                panel_user_obj_from_api = candidate
                logger.info(
                    "Found panel user by deterministic username '%s': identifier %s.",
                    panel_username_on_panel_standard,
                    panel_user_obj_from_api.get("uuid"),
                )
            elif panel_users_by_username and len(panel_users_by_username) > 1:
                logger.error(
                    "CRITICAL: Multiple panel users found for deterministic username '%s'.",
                    panel_username_on_panel_standard,
                )
                return PanelUserLink(None, None, None, False, False, None)

        if not panel_user_obj_from_api:
            if current_local_panel_uuid:
                logger.info(
                    "User %s (local panel_uuid: %s) not found on panel by TG ID. Fetching by "
                    "panel_uuid.",
                    user_id,
                    current_local_panel_uuid,
                )
                lookup_method = getattr(self.panel_service, "get_user_by_uuid_lookup", None)
                if callable(lookup_method):
                    lookup = await lookup_method(current_local_panel_uuid)
                    if isinstance(lookup, dict):
                        lookup_user = lookup.get("user")
                        if lookup.get("ok") and isinstance(lookup_user, dict):
                            panel_user_obj_from_api = lookup_user
                    else:
                        panel_user_obj_from_api = await self.panel_service.get_user_by_uuid(
                            current_local_panel_uuid
                        )
                else:
                    panel_user_obj_from_api = await self.panel_service.get_user_by_uuid(
                        current_local_panel_uuid
                    )
                if not panel_user_obj_from_api:
                    logger.error(
                        "Existing panel link %s for account %s could not be verified; "
                        "manual reconciliation is required before creating another panel user.",
                        current_local_panel_uuid,
                        user_id,
                    )
                    return PanelUserLink(
                        current_local_panel_uuid,
                        None,
                        None,
                        False,
                        False,
                        None,
                    )

            else:
                if identity_lookup_failed:
                    logger.error(
                        "Refusing to create a panel user for local user %s because an identity "
                        "lookup failed; retrying later avoids duplicate panel users.",
                        user_id,
                    )
                    return PanelUserLink(None, None, None, False, False, None)
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
                    default_expire_days=create_options.default_expire_days,
                    expire_at=create_options.expire_at,
                    hwid_device_limit=create_options.hwid_device_limit,
                    specific_squad_uuids=list(create_options.specific_squad_uuids),
                    external_squad_uuid=create_options.external_squad_uuid,
                    default_traffic_limit_bytes=create_options.default_traffic_limit_bytes,
                    default_traffic_limit_strategy=create_options.default_traffic_limit_strategy,
                    tag=creation_tag,
                )
                if (
                    creation_response
                    and not creation_response.get("error")
                    and creation_response.get("response")
                ):
                    panel_user_obj_from_api = creation_response.get("response")
                    panel_user_created_now = True

                elif creation_response and creation_response.get("errorCode") == "A019":
                    logger.error(
                        "Panel username '%s' is occupied; reconciliation is required "
                        "before linking.",
                        panel_username_on_panel_standard,
                    )
                    return PanelUserLink(None, None, None, False, False, None)

                if not panel_user_obj_from_api:
                    logger.error(
                        "Failed to create or link panel user for TG_ID %s with panel username "
                        "'%s'. Response: %s",
                        user_id,
                        panel_username_on_panel_standard,
                        creation_response if "creation_response" in locals() else "N/A",
                    )
                    await self._notify_admin_panel_user_creation_failed(session, user_id)
                    return PanelUserLink(None, None, None, False, False, None)

        if not panel_user_obj_from_api:
            logger.error(
                "Could not obtain panel user object for TG user %s after all checks.", user_id
            )

            return PanelUserLink(
                current_local_panel_uuid if current_local_panel_uuid else None,
                None,
                None,
                panel_user_created_now,
                local_link_updated_now,
                None,
            )

        if not panel_user_created_now and not panel_candidate_matches_account(
            db_user, panel_user_obj_from_api
        ):
            logger.error(
                "Panel native reference or search result lacks matching account identity for %s",
                user_id,
            )
            return PanelUserLink(None, None, None, False, False, None)

        actual_panel_uuid_from_api = panel_user_obj_from_api.get("uuid")
        if actual_panel_uuid_from_api:
            linked_account = await user_dal.get_user_by_panel_uuid(
                session, str(actual_panel_uuid_from_api)
            )
            if linked_account and linked_account.user_id != user_id:
                logger.error("Panel reference belongs to another local account for %s", user_id)
                return PanelUserLink(None, None, None, False, False, None)
        db_user.panel_origin = current_panel_origin
        actual_panel_username = str(panel_user_obj_from_api.get("username") or "").strip()
        if actual_panel_username:
            db_user.panel_username = actual_panel_username
            db_user.panel_username_state = (
                "current" if actual_panel_username == db_user.minishop_id else "legacy_pending"
            )
            await session.flush()
        panel_telegram_id_from_api = panel_user_obj_from_api.get("telegramId")

        if not actual_panel_uuid_from_api:
            logger.error(
                "Panel user object for TG user %s does not contain 'uuid'. Data: %s",
                user_id,
                panel_user_obj_from_api,
            )
            return PanelUserLink(
                current_local_panel_uuid,
                None,
                None,
                panel_user_created_now,
                local_link_updated_now,
                panel_user_obj_from_api,
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

                return PanelUserLink(None, None, None, False, False, panel_user_obj_from_api)
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
                local_link_updated_now = True
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

        if (
            panel_user_created_now
            and normalize_panel_tag(panel_user_obj_from_api.get("tag")) == creation_tag
        ):
            # Frozen/retired tariffs may no longer be in the catalog. A confirmed
            # CREATE still establishes ownership of the exact tag we just sent.
            db_user.managed_panel_tariff_tag = creation_tag

        return PanelUserLink(
            current_local_panel_uuid,
            panel_sub_link_id,
            panel_short_uuid,
            panel_user_created_now,
            local_link_updated_now,
            panel_user_obj_from_api,
        )

    async def _get_or_create_panel_user_link_details(
        self,
        session: AsyncSession,
        user_id: int,
        db_user: User | None = None,
        *,
        create_options: PanelUserCreateOptions | None = None,
    ) -> tuple[str | None, str | None, str | None, bool]:
        link = await self._get_or_create_panel_user_link(
            session,
            user_id,
            db_user,
            create_options=create_options,
        )
        if link.panel_user_uuid and isinstance(link.panel_user, dict):
            self._panel_user_link_snapshots[link.panel_user_uuid] = link.panel_user
        return link.legacy_details()

    def _take_panel_user_link_snapshot(
        self,
        panel_user_uuid: str,
    ) -> dict[str, Any] | None:
        return self._panel_user_link_snapshots.pop(panel_user_uuid, None)

    async def _compensate_failed_panel_user_creation(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        panel_user_uuid: str | None,
        previous_panel_user_uuid: str | None,
        panel_user_created_now: bool,
        source: str,
    ) -> None:
        if not panel_user_created_now or not panel_user_uuid:
            return
        try:
            deleted = await self.panel_service.delete_user_from_panel(panel_user_uuid)
        except Exception:
            logger.exception(
                "Failed to compensate panel user creation for user %s after %s failure.",
                user_id,
                source,
            )
            return
        if not deleted:
            logger.error(
                "Panel refused compensation delete for user %s after %s failure (panel UUID %s).",
                user_id,
                source,
                panel_user_uuid,
            )
            return
        await user_dal.update_user(
            session,
            user_id,
            {"panel_user_uuid": previous_panel_user_uuid},
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
