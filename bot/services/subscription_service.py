import logging
import math
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from aiogram import Bot
from bot.middlewares.i18n import JsonI18n

from db.dal import user_dal, subscription_dal, promo_code_dal, payment_dal, user_billing_dal, tariff_dal
from config.tariffs_config import Tariff
from bot.utils.date_utils import add_months
from bot.utils.config_link import prepare_config_links
from db.models import User, Subscription

from config.settings import Settings
from .panel_api_service import PanelApiService
from .email_auth_service import EmailAuthService
from .email_templates import render_payment_success


class SubscriptionService:

    def __init__(
        self,
        settings: Settings,
        panel_service: PanelApiService,
        bot: Optional[Bot] = None,
        i18n: Optional[JsonI18n] = None,
    ):
        self.settings = settings
        self.panel_service = panel_service
        self.bot = bot
        self.i18n = i18n

    @staticmethod
    def gb_to_bytes(gb: float) -> int:
        return int(float(gb) * (1024**3))

    @staticmethod
    def _far_future() -> datetime:
        return datetime(2099, 1, 1, tzinfo=timezone.utc)

    def _parse_sale_mode_context(
        self,
        sale_mode: str,
        explicit_tariff_key: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        mode = (sale_mode or "subscription").strip()
        tariff_key = explicit_tariff_key
        for separator in ("@", "|"):
            if separator in mode:
                base, suffix = mode.split(separator, 1)
                mode = base or mode
                tariff_key = tariff_key or suffix or None
                break
        return mode, tariff_key

    def _tariffs_config(self):
        return getattr(self.settings, "tariffs_config", None)

    def _default_tariff(self) -> Optional[Tariff]:
        config = self._tariffs_config()
        return config.default if config else None

    def _resolve_tariff(self, tariff_key: Optional[str], billing_model: Optional[str] = None) -> Optional[Tariff]:
        config = self._tariffs_config()
        if not config:
            return None
        tariff = config.require(tariff_key or config.default_tariff)
        if billing_model and tariff.billing_model != billing_model:
            raise ValueError(f"Tariff {tariff.key} is {tariff.billing_model}, expected {billing_model}")
        return tariff

    def _panel_squads_for_tariff(self, tariff: Optional[Tariff]) -> Optional[List[str]]:
        if tariff:
            return tariff.squad_uuids
        return self.settings.parsed_user_squad_uuids

    def _traffic_limit_for_period_tariff(self, tariff: Optional[Tariff], topup_balance_bytes: int = 0) -> int:
        if tariff:
            return int(tariff.monthly_bytes + max(0, topup_balance_bytes))
        return self.settings.user_traffic_limit_bytes

    async def _record_payment_context(
        self,
        session: AsyncSession,
        payment_db_id: int,
        *,
        sale_mode: str,
        tariff_key: Optional[str],
        purchased_gb: Optional[float] = None,
    ) -> None:
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if not payment:
            return
        payment.sale_mode = sale_mode
        payment.tariff_key = tariff_key
        payment.purchased_gb = purchased_gb
        await session.flush()

    async def get_user_language(self, session: AsyncSession, user_id: int) -> str:
        user_record = await user_dal.get_user_by_id(session, user_id)
        return (
            user_record.language_code
            if user_record and user_record.language_code
            else self.settings.DEFAULT_LANGUAGE
        )

    async def has_had_any_subscription(self, session: AsyncSession, user_id: int) -> bool:
        return await subscription_dal.has_any_subscription_for_user(session, user_id)

    async def has_active_subscription(self, session: AsyncSession, user_id: int) -> bool:
        """Return True if user currently has an active subscription (end_date in future)."""
        try:
            user_record = await user_dal.get_user_by_id(session, user_id)
            if not user_record or not user_record.panel_user_uuid:
                return False
            active_sub = await subscription_dal.get_active_subscription_by_user_id(
                session, user_id, user_record.panel_user_uuid
            )
            if not active_sub or not active_sub.end_date:
                return False
            from datetime import datetime, timezone
            return active_sub.is_active and active_sub.end_date > datetime.now(timezone.utc)
        except Exception:
            return False

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
        return used, limit, strategy

    def _extract_lifetime_used_traffic(
        self, panel_user_data: Dict[str, Any]
    ) -> Optional[int]:
        traffic_stats = panel_user_data.get("userTraffic") or {}
        lifetime = traffic_stats.get("lifetimeUsedTrafficBytes")
        if lifetime is None:
            lifetime = panel_user_data.get("lifetimeUsedTrafficBytes")
        try:
            if lifetime is None:
                return None
            return int(lifetime)
        except (TypeError, ValueError):
            return None

    async def _notify_admin_panel_user_creation_failed(self, user_id: int):
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

    async def _panel_username_for_user(
        self, session: AsyncSession, db_user: User
    ) -> str:
        telegram_id = self._telegram_id_for_panel(db_user)
        if telegram_id and int(db_user.user_id) == telegram_id:
            return f"tg_{telegram_id}"
        referral_code = await user_dal.ensure_referral_code(session, db_user)
        return f"em_{referral_code}"

    def _panel_description_for_user(self, db_user: User) -> str:
        lines = [
            db_user.email or "",
            db_user.username or "",
            db_user.first_name or "",
            db_user.last_name or "",
        ]
        return "\n".join(line for line in lines if line).strip()

    def _panel_identity_payload_for_user(self, db_user: User) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "description": self._panel_description_for_user(db_user),
        }
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
                f"_get_or_create_panel_user_link_details: User {user_id} not found in local DB. Cannot proceed."
            )
            return None, None, None, False

        current_local_panel_uuid = db_user.panel_user_uuid
        panel_username_on_panel_standard = await self._panel_username_for_user(
            session, db_user
        )
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
                f"Found panel user by telegramId {telegram_id_for_panel}: UUID {panel_user_obj_from_api.get('uuid')}, Username: {panel_user_obj_from_api.get('username')}"
            )
        elif panel_users_by_tg_id_list and len(panel_users_by_tg_id_list) > 1:
            logging.error(
                f"CRITICAL: Multiple panel users found for telegramId {telegram_id_for_panel}. Manual intervention needed."
            )
            return None, None, None, False

        if not panel_user_obj_from_api and db_user.email:
            panel_users_by_email_list = await self.panel_service.get_users_by_filter(
                email=db_user.email
            )
            if panel_users_by_email_list and len(panel_users_by_email_list) == 1:
                panel_user_obj_from_api = panel_users_by_email_list[0]
                logging.info(
                    f"Found panel user by email {db_user.email}: UUID {panel_user_obj_from_api.get('uuid')}, Username: {panel_user_obj_from_api.get('username')}"
                )
            elif panel_users_by_email_list and len(panel_users_by_email_list) > 1:
                logging.error(
                    f"CRITICAL: Multiple panel users found for email {db_user.email}. Manual intervention needed."
                )
                return None, None, None, False

        if not panel_user_obj_from_api:
            if current_local_panel_uuid:

                logging.info(
                    f"User {user_id} (local panel_uuid: {current_local_panel_uuid}) not found on panel by TG ID. Fetching by panel_uuid."
                )
                panel_user_obj_from_api = await self.panel_service.get_user_by_uuid(
                    current_local_panel_uuid
                )
                if not panel_user_obj_from_api:
                    logging.warning(
                        f"Local panel_uuid {current_local_panel_uuid} for TG user {user_id} also not found on panel. User might be deleted from panel or UUID desynced."
                    )
                    logging.info(
                        f"Creating new panel user '{panel_username_on_panel_standard}' for TG user {user_id}."
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
                    f"No panel user by TG ID & no local panel_uuid for TG user {user_id}. Creating new panel user '{panel_username_on_panel_standard}'."
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
                        f"Panel user '{panel_username_on_panel_standard}' already exists (errorCode A019). Fetching by username."
                    )
                    fetched_by_username_list = (
                        await self.panel_service.get_users_by_filter(
                            username=panel_username_on_panel_standard
                        )
                    )
                    if fetched_by_username_list and len(fetched_by_username_list) == 1:
                        panel_user_obj_from_api = fetched_by_username_list[0]

                if not panel_user_obj_from_api:
                    logging.error(
                        f"Failed to create or link panel user for TG_ID {user_id} with panel username '{panel_username_on_panel_standard}'. Response: {creation_response if 'creation_response' in locals() else 'N/A'}"
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
                f"Panel user object for TG user {user_id} does not contain 'uuid'. Data: {panel_user_obj_from_api}"
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
                    f"CRITICAL CONFLICT: Panel UUID {actual_panel_uuid_from_api} (from panel for TG ID {user_id}) "
                    f"is ALREADY LINKED in local DB to a different TG User {conflicting_user_record.user_id}. "
                    f"Cannot update panel_user_uuid for user {user_id}. Manual data correction needed."
                )

                return None, None, None, False
            else:

                update_data_for_local_user = {
                    "panel_user_uuid": actual_panel_uuid_from_api
                }

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
                f"Panel user {current_local_panel_uuid} has telegramId '{panel_telegram_id_from_api}'. Updating on panel to '{telegram_id_for_panel}'."
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
                f"No subscriptionUuid or shortUuid found on panel for panel_user_uuid {current_local_panel_uuid} (TG ID: {user_id})."
            )

        return (
            current_local_panel_uuid,
            panel_sub_link_id,
            panel_short_uuid,
            panel_user_created_or_linked_now,
        )

    async def activate_trial_subscription(
        self, session: AsyncSession, user_id: int
    ) -> Optional[Dict[str, Any]]:
        if not self.settings.TRIAL_ENABLED or self.settings.TRIAL_DURATION_DAYS <= 0:
            return {
                "eligible": False,
                "activated": False,
                "message_key": "trial_feature_disabled",
            }

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(f"User {user_id} not found in DB, cannot activate trial.")
            return {
                "eligible": False,
                "activated": False,
                "message_key": "user_not_found_for_trial",
            }

        if await self.has_had_any_subscription(session, user_id):
            return {
                "eligible": False,
                "activated": False,
                "message_key": "trial_already_had_subscription_or_trial",
            }

        panel_user_uuid, panel_sub_link_id, panel_short_uuid, panel_user_created_now = (
            await self._get_or_create_panel_user_link_details(session, user_id, db_user)
        )

        if not panel_user_uuid or not panel_sub_link_id:
            logging.error(f"Failed to get panel link details for trial user {user_id}.")
            return {
                "eligible": True,
                "activated": False,
                "message_key": "trial_activation_failed_panel_link",
            }

        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=self.settings.TRIAL_DURATION_DAYS)

        await subscription_dal.deactivate_other_active_subscriptions(
            session, panel_user_uuid, panel_sub_link_id
        )

        trial_sub_data = {
            "user_id": user_id,
            "panel_user_uuid": panel_user_uuid,
            "panel_subscription_uuid": panel_sub_link_id,
            "start_date": start_date,
            "end_date": end_date,
            "duration_months": 0,
            "is_active": True,
            "status_from_panel": "TRIAL",
            "traffic_limit_bytes": self.settings.trial_traffic_limit_bytes,
            "auto_renew_enabled": False,
        }
        try:
            await subscription_dal.upsert_subscription(session, trial_sub_data)
        except Exception as e_upsert:
            logging.error(
                f"Failed to upsert trial subscription for user {user_id}: {e_upsert}",
                exc_info=True,
            )
            await session.rollback()
            return {
                "eligible": True,
                "activated": False,
                "message_key": "trial_activation_failed_db",
            }

        panel_update_payload = self._build_panel_update_payload(
            panel_user_uuid=panel_user_uuid,
            expire_at=end_date,
            status="ACTIVE",
            traffic_limit_bytes=self.settings.trial_traffic_limit_bytes,
        )

        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))

        updated_panel_user = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid, panel_update_payload
        )
        if not updated_panel_user or updated_panel_user.get("error"):
            logging.warning(
                f"Panel user details update FAILED for trial user {panel_user_uuid}. Response: {updated_panel_user}"
            )
            await session.rollback()
            return {
                "eligible": True,
                "activated": False,
                "message_key": "trial_activation_failed_panel_update",
            }

        await session.commit()

        final_subscription_url = updated_panel_user.get("subscriptionUrl")
        final_panel_short_uuid = updated_panel_user.get("shortUuid", panel_short_uuid)

        return {
            "eligible": True,
            "activated": True,
            "end_date": end_date,
            "days": self.settings.TRIAL_DURATION_DAYS,
            "traffic_gb": self.settings.TRIAL_TRAFFIC_LIMIT_GB,
            "panel_user_uuid": panel_user_uuid,
            "panel_short_uuid": final_panel_short_uuid,
            "subscription_url": final_subscription_url,
        }

    async def _activate_traffic_package(
        self,
        session: AsyncSession,
        user_id: int,
        traffic_gb: float,
        payment_amount: float,
        payment_db_id: int,
        provider: str = "yookassa",
        tariff_key: Optional[str] = None,
        sale_mode: str = "traffic",
    ) -> Optional[Dict[str, Any]]:
        """Activate or extend a traffic-based package instead of a time-based subscription."""
        tariff = self._resolve_tariff(tariff_key, "traffic") if self._tariffs_config() else None
        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode=sale_mode,
            tariff_key=tariff.key if tariff else tariff_key,
            purchased_gb=float(traffic_gb),
        )
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error("User %s not found for traffic package activation", user_id)
            return None

        panel_user_uuid, panel_sub_link_id, panel_short_uuid, _ = (
            await self._get_or_create_panel_user_link_details(session, user_id, db_user)
        )

        if not panel_user_uuid or not panel_sub_link_id:
            logging.error("Failed to ensure panel linkage for user %s during traffic activation", user_id)
            return None

        panel_user_data = await self.panel_service.get_user_by_uuid(panel_user_uuid) or {}
        current_used, current_limit, _ = self._extract_panel_traffic_details(panel_user_data)

        active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, panel_user_uuid
        )
        if current_limit is None and active_sub:
            current_limit = active_sub.traffic_limit_bytes
        if current_used is None and active_sub:
            current_used = active_sub.traffic_used_bytes

        purchase_bytes = self.gb_to_bytes(traffic_gb)
        remaining_bytes = max(0, int(current_limit or 0) - int(current_used or 0))
        new_balance = remaining_bytes + purchase_bytes
        new_limit = int(current_used or 0) + new_balance

        start_date = datetime.now(timezone.utc)
        # Set a far-future expiry to satisfy panel requirements; keep the latest known expiry if it's further.
        far_future = self._far_future()
        final_end_date = far_future
        if active_sub and active_sub.end_date and active_sub.end_date > final_end_date:
            final_end_date = active_sub.end_date

        await subscription_dal.deactivate_other_active_subscriptions(
            session, panel_user_uuid, panel_sub_link_id
        )

        sub_payload = {
            "user_id": user_id,
            "panel_user_uuid": panel_user_uuid,
            "panel_subscription_uuid": panel_sub_link_id,
            "start_date": start_date,
            "end_date": final_end_date,
            "duration_months": 0,
            "is_active": True,
            "status_from_panel": "ACTIVE",
            "traffic_limit_bytes": new_limit,
            "traffic_used_bytes": current_used,
            "provider": provider,
            "skip_notifications": True,
            "auto_renew_enabled": False,
            "tariff_key": tariff.key if tariff else None,
            "tier_baseline_bytes": 0,
            "topup_balance_bytes": new_balance,
            "period_start_at": None,
            "is_throttled": False,
            "effective_monthly_price_rub": None,
        }

        try:
            new_or_updated_sub = await subscription_dal.upsert_subscription(session, sub_payload)
        except Exception as exc:
            logging.error("Failed to upsert traffic subscription for user %s: %s", user_id, exc, exc_info=True)
            return None

        panel_update_payload = self._build_panel_update_payload(
            panel_user_uuid=panel_user_uuid,
            expire_at=final_end_date,
            status="ACTIVE",
            traffic_limit_bytes=new_limit,
            traffic_limit_strategy="NO_RESET",
        )
        if tariff:
            panel_update_payload["activeInternalSquads"] = tariff.squad_uuids

        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))

        updated_panel_user = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid, panel_update_payload
        )
        if not updated_panel_user or updated_panel_user.get("error"):
            logging.warning(
                "Panel user details update FAILED for traffic package user %s. Response: %s",
                panel_user_uuid,
                updated_panel_user,
            )
            return None

        final_subscription_url = updated_panel_user.get("subscriptionUrl")
        final_panel_short_uuid = updated_panel_user.get("shortUuid", panel_short_uuid)
        await tariff_dal.create_traffic_topup(
            session,
            subscription_id=new_or_updated_sub.subscription_id,
            payment_id=payment_db_id,
            purchased_bytes=purchase_bytes,
            kind="traffic_package",
        )

        await self._send_payment_success_email(
            db_user=db_user,
            sale_mode="traffic",
            months=0,
            traffic_gb=float(traffic_gb),
            payment_amount=payment_amount,
            end_date=None,
            provider=provider,
        )

        return {
            "subscription_id": new_or_updated_sub.subscription_id,
            "end_date": final_end_date,
            "is_active": True,
            "panel_user_uuid": panel_user_uuid,
            "panel_short_uuid": final_panel_short_uuid,
            "subscription_url": final_subscription_url,
            "applied_promo_bonus_days": 0,
            "traffic_limit_bytes": new_limit,
            "tariff_key": tariff.key if tariff else None,
        }

    async def activate_topup(
        self,
        session: AsyncSession,
        user_id: int,
        tariff_key: str,
        traffic_gb: float,
        payment_amount: float,
        payment_db_id: int,
        provider: str = "yookassa",
    ) -> Optional[Dict[str, Any]]:
        tariff = self._resolve_tariff(tariff_key)
        if tariff.billing_model == "traffic":
            return await self._activate_traffic_package(
                session=session,
                user_id=user_id,
                traffic_gb=traffic_gb,
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                tariff_key=tariff.key,
                sale_mode="traffic_package",
            )

        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode="topup",
            tariff_key=tariff.key,
            purchased_gb=float(traffic_gb),
        )
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id, db_user.panel_user_uuid)
        if not sub:
            return None

        purchase_bytes = self.gb_to_bytes(traffic_gb)
        new_topup_balance = int(sub.topup_balance_bytes or 0) + purchase_bytes
        new_limit = int(sub.tier_baseline_bytes or tariff.monthly_bytes) + new_topup_balance
        updated_sub = await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "topup_balance_bytes": new_topup_balance,
                "traffic_limit_bytes": new_limit,
                "is_throttled": False,
                "tariff_key": tariff.key,
            },
        )
        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=updated_sub.end_date,
            status="ACTIVE",
            traffic_limit_bytes=new_limit,
        )
        panel_payload["activeInternalSquads"] = tariff.squad_uuids
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        await self.panel_service.update_user_details_on_panel(db_user.panel_user_uuid, panel_payload)
        await tariff_dal.create_traffic_topup(
            session,
            subscription_id=sub.subscription_id,
            payment_id=payment_db_id,
            purchased_bytes=purchase_bytes,
            kind="topup",
        )
        return {
            "subscription_id": sub.subscription_id,
            "traffic_limit_bytes": new_limit,
            "topup_balance_bytes": new_topup_balance,
            "tariff_key": tariff.key,
        }

    def calculate_tariff_switch_options(self, sub: Subscription, target_tariff: Tariff) -> Dict[str, Any]:
        current_tariff = self._resolve_tariff(sub.tariff_key) if sub.tariff_key else self._default_tariff()
        now = datetime.now(timezone.utc)
        remaining_days = max(0, (sub.end_date - now).days) if sub.end_date else 0
        effective = float(sub.effective_monthly_price_rub or 0)
        current_model = current_tariff.billing_model if current_tariff else "period"

        if current_model == "period" and target_tariff.billing_model == "period":
            target_monthly = target_tariff.period_price(1, "rub") or target_tariff.min_period_price_rub() or effective or 1
            remaining_value = remaining_days * (effective / 30) if effective else 0
            days_after = math.floor((remaining_value / float(target_monthly)) * 30) if target_monthly else remaining_days
            paid_diff = max(0, math.ceil((float(target_monthly) - effective) * remaining_days / 30)) if effective else 0
            return {
                "mode": "period_to_period",
                "remaining_days": remaining_days,
                "recalc_days": max(0, days_after),
                "paid_diff_rub": paid_diff,
                "target_monthly_rub": float(target_monthly),
            }

        if current_model == "period" and target_tariff.billing_model == "traffic":
            rub_per_gb = target_tariff.rub_per_gb_for_conversion()
            remaining_value = remaining_days * (effective / 30) if effective else 0
            converted_gb = math.floor(remaining_value / rub_per_gb) if rub_per_gb else 0
            return {
                "mode": "period_to_traffic",
                "remaining_days": remaining_days,
                "converted_gb": max(0, converted_gb),
                "rub_per_gb": rub_per_gb,
            }

        return {"mode": "traffic_to_period", "remaining_days": remaining_days}

    async def switch_tariff_without_payment(
        self,
        session: AsyncSession,
        user_id: int,
        target_tariff_key: str,
        mode: str,
    ) -> Optional[Dict[str, Any]]:
        config = self._tariffs_config()
        if not config:
            return None
        target = config.require(target_tariff_key)
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id, db_user.panel_user_uuid)
        if not sub:
            return None
        before_tariff_key = sub.tariff_key
        options = self.calculate_tariff_switch_options(sub, target)
        now = datetime.now(timezone.utc)
        update_data: Dict[str, Any] = {"tariff_key": target.key, "is_throttled": False}
        converted_bytes = None

        if target.billing_model == "period":
            update_data["tier_baseline_bytes"] = target.monthly_bytes
            update_data["traffic_limit_bytes"] = target.monthly_bytes + int(sub.topup_balance_bytes or 0)
            update_data["period_start_at"] = None
            update_data["effective_monthly_price_rub"] = target.period_price(1, "rub") or target.min_period_price_rub()
            if mode == "recalc_days" and options.get("recalc_days") is not None:
                update_data["end_date"] = now + timedelta(days=int(options["recalc_days"]))
        else:
            converted_gb = float(options.get("converted_gb", 0))
            converted_bytes = self.gb_to_bytes(converted_gb)
            old_topup = int(sub.topup_balance_bytes or 0)
            new_balance = old_topup + converted_bytes
            panel_user = await self.panel_service.get_user_by_uuid(db_user.panel_user_uuid, log_response=False) or {}
            current_used, _, _ = self._extract_panel_traffic_details(panel_user)
            update_data.update(
                {
                    "end_date": self._far_future(),
                    "period_start_at": None,
                    "tier_baseline_bytes": 0,
                    "topup_balance_bytes": new_balance,
                    "traffic_limit_bytes": int(current_used or 0) + new_balance,
                    "traffic_used_bytes": current_used,
                    "effective_monthly_price_rub": None,
                    "auto_renew_enabled": False,
                    "skip_notifications": True,
                }
            )

        updated = await subscription_dal.update_subscription(session, sub.subscription_id, update_data)
        if not updated:
            return None
        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=updated.end_date,
            status="ACTIVE",
            traffic_limit_bytes=updated.traffic_limit_bytes,
            traffic_limit_strategy="NO_RESET" if target.billing_model == "traffic" else "MONTH",
        )
        panel_payload["activeInternalSquads"] = target.squad_uuids
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        await self.panel_service.update_user_details_on_panel(db_user.panel_user_uuid, panel_payload)
        if converted_bytes:
            await tariff_dal.create_traffic_topup(
                session,
                subscription_id=updated.subscription_id,
                payment_id=None,
                purchased_bytes=converted_bytes,
                kind="conversion",
            )
        await tariff_dal.create_tariff_change(
            session,
            {
                "subscription_id": updated.subscription_id,
                "from_tariff_key": before_tariff_key,
                "to_tariff_key": target.key,
                "mode": mode,
                "payment_id": None,
                "days_before": options.get("remaining_days"),
                "days_after": (updated.end_date - now).days if updated.end_date and target.billing_model == "period" else None,
                "converted_bytes": converted_bytes,
                "eff_price_before": sub.effective_monthly_price_rub,
                "eff_price_after": updated.effective_monthly_price_rub,
            },
        )
        return {"subscription_id": updated.subscription_id, "tariff_key": target.key}

    async def activate_subscription(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        payment_amount: float,
        payment_db_id: int,
        promo_code_id_from_payment: Optional[int] = None,
        provider: str = "yookassa",
        sale_mode: str = "subscription",
        traffic_gb: Optional[float] = None,
        tariff_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        sale_mode_base, sale_mode_tariff_key = self._parse_sale_mode_context(sale_mode, tariff_key)
        tariff_key = sale_mode_tariff_key
        if sale_mode_base in {"traffic", "traffic_package"} or (
            getattr(self.settings, "traffic_sale_mode", False) and not self._tariffs_config()
        ):
            target_gb = traffic_gb if traffic_gb is not None else float(months)
            return await self._activate_traffic_package(
                session=session,
                user_id=user_id,
                traffic_gb=target_gb,
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                tariff_key=tariff_key,
                sale_mode="traffic_package" if self._tariffs_config() else "traffic",
            )
        if sale_mode_base == "topup":
            if not tariff_key:
                active_user = await user_dal.get_user_by_id(session, user_id)
                active_sub = (
                    await subscription_dal.get_active_subscription_by_user_id(
                        session, user_id, active_user.panel_user_uuid
                    )
                    if active_user and active_user.panel_user_uuid
                    else None
                )
                tariff_key = active_sub.tariff_key if active_sub else None
            if not tariff_key:
                logging.error("Top-up activation requires tariff_key for user %s", user_id)
                return None
            return await self.activate_topup(
                session=session,
                user_id=user_id,
                tariff_key=tariff_key,
                traffic_gb=traffic_gb if traffic_gb is not None else float(months),
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
            )
        if sale_mode_base == "tariff_upgrade":
            if not tariff_key:
                logging.error("Tariff upgrade activation requires tariff_key for user %s", user_id)
                return None
            await self._record_payment_context(
                session,
                payment_db_id,
                sale_mode="tariff_upgrade",
                tariff_key=tariff_key,
                purchased_gb=None,
            )
            result = await self.switch_tariff_without_payment(
                session,
                user_id,
                tariff_key,
                "paid_diff",
            )
            if result:
                sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
                if sub:
                    await tariff_dal.create_tariff_change(
                        session,
                        {
                            "subscription_id": sub.subscription_id,
                            "from_tariff_key": None,
                            "to_tariff_key": tariff_key,
                            "mode": "paid_diff",
                            "payment_id": payment_db_id,
                            "days_before": None,
                            "days_after": (sub.end_date - datetime.now(timezone.utc)).days if sub.end_date else None,
                            "converted_bytes": None,
                            "eff_price_before": None,
                            "eff_price_after": sub.effective_monthly_price_rub,
                        },
                    )
                    result["end_date"] = sub.end_date
                    result["is_active"] = sub.is_active
            return result

        tariff = self._resolve_tariff(tariff_key, "period") if self._tariffs_config() else None
        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode=sale_mode_base,
            tariff_key=tariff.key if tariff else tariff_key,
            purchased_gb=None,
        )

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(
                f"User {user_id} not found in DB for paid subscription activation."
            )
            return None

        panel_user_uuid, panel_sub_link_id, panel_short_uuid, panel_user_created_now = (
            await self._get_or_create_panel_user_link_details(session, user_id, db_user)
        )

        if not panel_user_uuid or not panel_sub_link_id:
            logging.error(
                f"Failed to ensure panel user for TG {user_id} during paid subscription."
            )
            return None

        try:
            months_int = int(months)
        except Exception:
            months_int = 1

        current_active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, panel_user_uuid
        )
        start_date = datetime.now(timezone.utc)
        starts_after_lapse = not (
            current_active_sub
            and current_active_sub.end_date
            and current_active_sub.end_date > start_date
        )
        if (
            current_active_sub
            and current_active_sub.end_date
            and current_active_sub.end_date > start_date
        ):
            start_date = current_active_sub.end_date

        # base duration by months
        end_after_months = add_months(start_date, months_int)
        duration_days_total = (end_after_months - start_date).days
        applied_promo_bonus_days = 0

        if promo_code_id_from_payment:
            promo_model = await promo_code_dal.get_promo_code_by_id(
                session, promo_code_id_from_payment
            )
            if (
                promo_model
                and promo_model.is_active
                and promo_model.current_activations < promo_model.max_activations
            ):
                applied_promo_bonus_days = promo_model.bonus_days
                duration_days_total += applied_promo_bonus_days

                activation = await promo_code_dal.record_promo_activation(
                    session,
                    promo_code_id_from_payment,
                    user_id,
                    payment_id=payment_db_id,
                )
                if activation:
                    await promo_code_dal.increment_promo_code_usage(
                        session, promo_code_id_from_payment
                    )
                else:
                    logging.warning(
                        f"Promo code {promo_code_id_from_payment} was already activated by user {user_id}, but bonus applied via payment {payment_db_id}."
                    )
            else:
                logging.warning(
                    f"Promo code ID {promo_code_id_from_payment} (from payment) not found or invalid."
                )
                promo_code_id_from_payment = None

        final_end_date = start_date + timedelta(days=duration_days_total)
        await subscription_dal.deactivate_other_active_subscriptions(
            session, panel_user_uuid, panel_sub_link_id
        )

        auto_renew_should_enable = False
        if provider == "yookassa" and self.settings.yookassa_autopayments_active:
            auto_renew_should_enable = await user_billing_dal.user_has_saved_payment_method(
                session, user_id
            )

        topup_balance_bytes = int(getattr(current_active_sub, "topup_balance_bytes", 0) or 0)
        tier_baseline_bytes = tariff.monthly_bytes if tariff else self.settings.user_traffic_limit_bytes
        effective_monthly_price = float(payment_amount) / max(1, months_int)
        traffic_limit_bytes = self._traffic_limit_for_period_tariff(tariff, topup_balance_bytes)
        sub_payload = {
            "user_id": user_id,
            "panel_user_uuid": panel_user_uuid,
            "panel_subscription_uuid": panel_sub_link_id,
            "start_date": start_date,
            "end_date": final_end_date,
            "duration_months": months_int,
            "is_active": True,
            "status_from_panel": "ACTIVE",
            "traffic_limit_bytes": traffic_limit_bytes,
            "provider": provider,
            "skip_notifications": False,
            "auto_renew_enabled": auto_renew_should_enable,
            "tariff_key": tariff.key if tariff else None,
            "tier_baseline_bytes": tier_baseline_bytes,
            "topup_balance_bytes": topup_balance_bytes,
            "period_start_at": None,
            "is_throttled": False,
            "effective_monthly_price_rub": effective_monthly_price,
        }
        try:
            new_or_updated_sub = await subscription_dal.upsert_subscription(
                session, sub_payload
            )
        except Exception as e_upsert_sub:
            logging.error(
                f"Failed to upsert paid subscription for user {user_id}: {e_upsert_sub}",
                exc_info=True,
            )
            return None

        panel_update_payload = self._build_panel_update_payload(
            panel_user_uuid=panel_user_uuid,
            expire_at=final_end_date,
            status="ACTIVE",
            traffic_limit_bytes=traffic_limit_bytes,
            traffic_limit_strategy="MONTH" if tariff else self.settings.USER_TRAFFIC_STRATEGY,
        )
        if tariff:
            panel_update_payload["activeInternalSquads"] = tariff.squad_uuids

        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))

        updated_panel_user = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid, panel_update_payload
        )
        if not updated_panel_user or updated_panel_user.get("error"):
            logging.warning(
                f"Panel user details update FAILED for paid sub user {panel_user_uuid}. Response: {updated_panel_user}"
            )
            return None

        final_subscription_url = updated_panel_user.get("subscriptionUrl")
        final_panel_short_uuid = updated_panel_user.get("shortUuid", panel_short_uuid)

        await self._send_payment_success_email(
            db_user=db_user,
            sale_mode="subscription",
            months=months_int,
            traffic_gb=None,
            payment_amount=payment_amount,
            end_date=final_end_date,
            provider=provider,
        )

        return {
            "subscription_id": new_or_updated_sub.subscription_id,
            "end_date": final_end_date,
            "is_active": True,
            "panel_user_uuid": panel_user_uuid,
            "panel_short_uuid": final_panel_short_uuid,
            "subscription_url": final_subscription_url,
            "applied_promo_bonus_days": applied_promo_bonus_days,
            "tariff_key": tariff.key if tariff else None,
        }

    async def extend_active_subscription_days(
        self,
        session: AsyncSession,
        user_id: int,
        bonus_days: int,
        reason: str = "bonus",
    ) -> Optional[datetime]:
        reason_lower = (reason or "").lower()
        apply_main_traffic_limit = any(
            keyword in reason_lower for keyword in ("admin", "promo code", "referral", "bonus")
        )

        user = await user_dal.get_user_by_id(session, user_id)
        if not user:
            logging.warning(
                f"Cannot extend subscription for user {user_id}: user not found."
            )
            return None

        panel_uuid, panel_sub_uuid, _, _ = await self._get_or_create_panel_user_link_details(
            session, user_id, user
        )
        if not panel_uuid or not panel_sub_uuid:
            logging.error(
                f"Failed to ensure panel user for subscription extension of user {user_id}."
            )
            return None

        active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, panel_uuid
        )
        if not active_sub or not active_sub.end_date:
            logging.info(
                f"No active subscription found for user {user_id}. Creating new one for {bonus_days} days."
            )
            start_date = datetime.now(timezone.utc)
            new_end_date_obj = start_date + timedelta(days=bonus_days)

            # Apply main traffic limit for admin/referral/promo bonuses, fallback to trial limit otherwise
            traffic_limit = (
                self.settings.user_traffic_limit_bytes
                if apply_main_traffic_limit
                else self.settings.trial_traffic_limit_bytes
            )

            bonus_sub_payload = {
                "user_id": user_id,
                "panel_user_uuid": panel_uuid,
                "panel_subscription_uuid": panel_sub_uuid,
                "start_date": start_date,
                "end_date": new_end_date_obj,
                "duration_months": 0,
                "is_active": True,
                "status_from_panel": "ACTIVE_BONUS",
                "traffic_limit_bytes": traffic_limit,
                "auto_renew_enabled": False,
            }
            await subscription_dal.deactivate_other_active_subscriptions(
                session, panel_uuid, panel_sub_uuid
            )
            updated_sub_model = await subscription_dal.upsert_subscription(
                session, bonus_sub_payload
            )
        else:
            current_end_date = active_sub.end_date
            now_utc = datetime.now(timezone.utc)
            start_point_for_bonus = (
                current_end_date if current_end_date > now_utc else now_utc
            )
            new_end_date_obj = start_point_for_bonus + timedelta(days=bonus_days)

            updated_sub_model = await subscription_dal.update_subscription_end_date(
                session, active_sub.subscription_id, new_end_date_obj
            )

            if (
                apply_main_traffic_limit
                and updated_sub_model
                and updated_sub_model.traffic_limit_bytes != self.settings.user_traffic_limit_bytes
            ):
                updated_sub_model = await subscription_dal.update_subscription(
                    session,
                    updated_sub_model.subscription_id,
                    {"traffic_limit_bytes": self.settings.user_traffic_limit_bytes},
                )

        if updated_sub_model:
            # Prepare panel update payload
            panel_update_payload = self._build_panel_update_payload(
                expire_at=new_end_date_obj,
                traffic_limit_bytes=(
                    self.settings.user_traffic_limit_bytes if apply_main_traffic_limit else None
                ),
                include_uuid=False,
            )

            panel_update_success = (
                await self.panel_service.update_user_details_on_panel(
                    panel_uuid,
                    panel_update_payload,
                )
            )
            if not panel_update_success:
                logging.warning(
                    f"Panel expiry update failed for {panel_uuid} after {reason} bonus. Local DB was updated to {new_end_date_obj}."
                )

            logging.info(
                f"Subscription for user {user_id} extended by {bonus_days} days ({reason}). New end date: {new_end_date_obj}."
            )
            return new_end_date_obj
        else:
            logging.error(
                f"Failed to update subscription end date locally for user {user_id}."
            )
            return None

    async def get_active_subscription_details(
        self, session: AsyncSession, user_id: int
    ) -> Optional[Dict[str, Any]]:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            logging.info(
                f"User {user_id} not found in DB or no panel_user_uuid for 'my_subscription'."
            )
            return None

        panel_user_uuid = db_user.panel_user_uuid
        local_active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, panel_user_uuid
        )
        panel_user_data = await self.panel_service.get_user_by_uuid(panel_user_uuid)

        if not panel_user_data:
            logging.warning(
                f"Panel user {panel_user_uuid} not found on panel for user {user_id}. Clearing local linkage."
            )
            await subscription_dal.deactivate_all_user_subscriptions(session, user_id)
            await user_dal.update_user(session, user_id, {"panel_user_uuid": None})
            return None

        panel_lifetime_used = self._extract_lifetime_used_traffic(panel_user_data)
        if (
            panel_lifetime_used is not None
            and db_user.lifetime_used_traffic_bytes != panel_lifetime_used
        ):
            await user_dal.update_user(
                session,
                user_id,
                {"lifetime_used_traffic_bytes": panel_lifetime_used},
            )

        if local_active_sub:
            update_payload_local = {}
            panel_status = panel_user_data.get("status", "UNKNOWN").upper()
            panel_expire_at_str = panel_user_data.get("expireAt")
            panel_traffic_used, panel_traffic_limit, _ = self._extract_panel_traffic_details(panel_user_data)
            panel_sub_uuid_from_panel = panel_user_data.get(
                "subscriptionUuid"
            ) or panel_user_data.get("shortUuid")

            if local_active_sub.status_from_panel != panel_status:
                update_payload_local["status_from_panel"] = panel_status
            if panel_expire_at_str:
                panel_expire_dt = datetime.fromisoformat(
                    panel_expire_at_str.replace("Z", "+00:00")
                )
                if local_active_sub.end_date.replace(
                    microsecond=0
                ) != panel_expire_dt.replace(microsecond=0):
                    update_payload_local["end_date"] = panel_expire_dt
                    update_payload_local["last_notification_sent"] = None
            if (
                panel_traffic_used is not None
                and local_active_sub.traffic_used_bytes != panel_traffic_used
            ):
                update_payload_local["traffic_used_bytes"] = panel_traffic_used
            if (
                panel_traffic_limit is not None
                and local_active_sub.traffic_limit_bytes != panel_traffic_limit
            ):
                update_payload_local["traffic_limit_bytes"] = panel_traffic_limit
            if (
                panel_sub_uuid_from_panel
                and local_active_sub.panel_subscription_uuid
                != panel_sub_uuid_from_panel
            ):
                update_payload_local["panel_subscription_uuid"] = (
                    panel_sub_uuid_from_panel
                )

            is_active_based_on_panel = panel_status == "ACTIVE" and (
                panel_expire_dt > datetime.now(timezone.utc)
                if panel_expire_dt
                else False
            )
            if local_active_sub.is_active != is_active_based_on_panel:
                update_payload_local["is_active"] = is_active_based_on_panel

            if update_payload_local:
                await subscription_dal.update_subscription(
                    session, local_active_sub.subscription_id, update_payload_local
                )

        panel_end_date = (
            datetime.fromisoformat(panel_user_data["expireAt"].replace("Z", "+00:00"))
            if panel_user_data.get("expireAt")
            else None
        )
        panel_traffic_used, panel_traffic_limit, panel_traffic_strategy = self._extract_panel_traffic_details(panel_user_data)
        config_link_raw = panel_user_data.get("subscriptionUrl")
        display_link, connect_button_url = await prepare_config_links(self.settings, config_link_raw)
        hwid_limit = panel_user_data.get("hwidDeviceLimit")
        if hwid_limit is None:
            hwid_limit = self.settings.USER_HWID_DEVICE_LIMIT
        tariff = None
        if local_active_sub and local_active_sub.tariff_key and self._tariffs_config():
            try:
                tariff = self._resolve_tariff(local_active_sub.tariff_key)
            except Exception:
                tariff = None
        billing_model_display = tariff.billing_model if tariff else ("traffic" if getattr(self.settings, "traffic_sale_mode", False) else "period")
        traffic_limit_strategy = panel_traffic_strategy

        return {
            "user_id": panel_user_data.get("uuid"),
            "end_date": panel_end_date,
            "status_from_panel": panel_user_data.get("status", "UNKNOWN").upper(),
            "config_link": display_link,
            "connect_button_url": connect_button_url,
            "traffic_limit_bytes": panel_traffic_limit,
            "traffic_used_bytes": panel_traffic_used,
            "traffic_limit_strategy": traffic_limit_strategy,
            "tariff_key": local_active_sub.tariff_key if local_active_sub else None,
            "tariff_name": tariff.name(db_user.language_code or self.settings.DEFAULT_LANGUAGE) if tariff else None,
            "tariff_description": tariff.description(db_user.language_code or self.settings.DEFAULT_LANGUAGE) if tariff else None,
            "billing_model": billing_model_display,
            "tier_baseline_bytes": local_active_sub.tier_baseline_bytes if local_active_sub else None,
            "topup_balance_bytes": local_active_sub.topup_balance_bytes if local_active_sub else 0,
            "period_start_at": local_active_sub.period_start_at if local_active_sub else None,
            "is_throttled": bool(local_active_sub.is_throttled) if local_active_sub else False,
            "user_bot_username": db_user.username,
            "is_panel_data": True,
            "max_devices": hwid_limit,
        }

    async def get_subscriptions_ending_soon(
        self, session: AsyncSession, days_threshold: int
    ) -> List[Dict[str, Any]]:
        subs_models_with_users = (
            await subscription_dal.get_subscriptions_near_expiration(
                session, days_threshold
            )
        )
        results = []
        for sub_model in subs_models_with_users:
            if (
                sub_model.user
                and sub_model.end_date
                and not sub_model.skip_notifications
            ):
                days_left = (
                    sub_model.end_date - datetime.now(timezone.utc)
                ).total_seconds() / (24 * 3600)
                results.append(
                    {
                        "user_id": sub_model.user_id,
                        "first_name": sub_model.user.first_name
                        or f"User {sub_model.user_id}",
                        "language_code": sub_model.user.language_code
                        or self.settings.DEFAULT_LANGUAGE,
                        "end_date_str": sub_model.end_date.strftime("%Y-%m-%d"),
                        "days_left": max(0, int(round(days_left))),
                        "subscription_end_date_iso_for_update": sub_model.end_date,
                    }
                )
        return results

    async def charge_subscription_renewal(
        self,
        session: AsyncSession,
        sub: Subscription,
    ) -> bool:
        """Attempt to charge user using saved payment method. Return True on initiated/handled, False on failure."""
        if getattr(self.settings, "traffic_sale_mode", False):
            logging.info("Auto-renew skipped: traffic sale mode enabled")
            return True
        if not sub.auto_renew_enabled:
            return True
        # If autopayments are disabled globally, skip charging attempts
        if not self.settings.yookassa_autopayments_active:
            return True
        if sub.provider != "yookassa":
            logging.info("Auto-renew skipped: provider %s does not support auto-renew", sub.provider)
            return True

        from db.dal.user_billing_dal import get_user_default_payment_method
        default_pm = await get_user_default_payment_method(session, sub.user_id)
        if not default_pm:
            logging.info(f"Auto-renew skipped: no saved payment method for user {sub.user_id}")
            return False

        try:
            from .yookassa_service import YooKassaService  # local import to avoid cycles
            yk: YooKassaService = self.yookassa_service  # type: ignore[attr-defined]
        except Exception:
            yk = None  # type: ignore
        if not yk or not getattr(yk, 'configured', False):
            logging.warning("YooKassa unavailable for auto-renew")
            return False

        months = sub.duration_months or 1
        amount = self.settings.subscription_options.get(months)
        if not amount:
            logging.error(f"Auto-renew price missing for {months} months")
            return False

        metadata = {
            "user_id": str(sub.user_id),
            "auto_renew_for_subscription_id": str(sub.subscription_id),
            "subscription_months": str(months),
        }
        resp = await yk.create_payment(
            amount=float(amount),
            currency="RUB",
            description=f"Auto-renewal for {months} months",
            metadata=metadata,
            payment_method_id=default_pm.provider_payment_method_id,
            save_payment_method=False,
            capture=True,
        )
        if not resp or resp.get("status") not in {"pending", "waiting_for_capture", "succeeded"}:
            logging.error(f"Auto-renew create_payment failed: {resp}")
            return False
        logging.info(f"Auto-renew initiated for user {sub.user_id} payment_id={resp.get('id')}")
        return True

    _PROVIDER_LABELS = {
        "yookassa": "YooKassa",
        "freekassa": "FreeKassa",
        "platega": "Platega",
        "severpay": "SeverPay",
        "cryptopay": "Crypto Pay",
        "crypto_pay": "Crypto Pay",
        "stars": "Telegram Stars",
        "tribute": "Tribute",
    }

    async def _send_payment_success_email(
        self,
        *,
        db_user: User,
        sale_mode: str,
        months: int,
        traffic_gb: Optional[float],
        payment_amount: float,
        end_date: Optional[datetime],
        provider: str,
    ) -> None:
        """Best-effort branded email confirming the payment. No-op if SMTP or
        the user's email aren't set. Failures are logged and swallowed so the
        payment flow is never blocked by mail delivery."""
        if not self.settings.email_auth_configured:
            return
        recipient = (db_user.email or "").strip() if db_user else ""
        if not recipient:
            return

        end_date_text = end_date.strftime("%Y-%m-%d") if end_date else ""
        provider_label = self._PROVIDER_LABELS.get((provider or "").lower())
        dashboard_url = (self.settings.SUBSCRIPTION_MINI_APP_URL or "").strip() or None

        try:
            content = render_payment_success(
                self.settings,
                language_code=db_user.language_code or self.settings.DEFAULT_LANGUAGE,
                sale_mode=sale_mode,
                months=int(months or 0),
                traffic_gb=traffic_gb,
                amount=float(payment_amount or 0),
                currency=self.settings.DEFAULT_CURRENCY_SYMBOL,
                end_date_text=end_date_text,
                dashboard_url=dashboard_url,
                provider_label=provider_label,
            )
            email_service = EmailAuthService(self.settings)
            await email_service.send_rendered_email(email=recipient, content=content)
        except Exception:
            logging.exception(
                "Failed to send payment success email to user %s", db_user.user_id
            )

    async def update_last_notification_sent(
        self, session: AsyncSession, user_id: int, subscription_end_date: datetime
    ):
        sub_to_update = (
            await subscription_dal.find_subscription_for_notification_update(
                session, user_id, subscription_end_date
            )
        )
        if sub_to_update:
            await subscription_dal.update_subscription_notification_time(
                session, sub_to_update.subscription_id, datetime.now(timezone.utc)
            )
            logging.info(
                f"Updated last_notification_sent for user {user_id}, sub_id {sub_to_update.subscription_id}"
            )
        else:
            logging.warning(
                f"Could not find subscription for user {user_id} ending at {subscription_end_date.isoformat()} to update notification time."
            )

    # Helpers
    def _build_panel_update_payload(
        self,
        *,
        panel_user_uuid: Optional[str] = None,
        expire_at: Optional[datetime] = None,
        status: Optional[str] = None,
        traffic_limit_bytes: Optional[int] = None,
        include_uuid: bool = True,
        traffic_limit_strategy: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if include_uuid and panel_user_uuid:
            payload["uuid"] = panel_user_uuid
        if expire_at is not None:
            payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if status is not None:
            payload["status"] = status
        if traffic_limit_bytes is not None:
            payload["trafficLimitBytes"] = traffic_limit_bytes
            payload["trafficLimitStrategy"] = traffic_limit_strategy or self.settings.USER_TRAFFIC_STRATEGY
        if self.settings.parsed_user_squad_uuids:
            payload["activeInternalSquads"] = self.settings.parsed_user_squad_uuids
        if self.settings.parsed_user_external_squad_uuid:
            payload["externalSquadUuid"] = self.settings.parsed_user_external_squad_uuid
        return payload
