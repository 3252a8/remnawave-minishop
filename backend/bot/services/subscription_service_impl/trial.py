import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import TrialActivatedPayload
from db.dal import subscription_dal, user_dal

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


class TrialSubscriptionMixin(SubscriptionServiceMixinContract):
    async def activate_trial_subscription(
        self, session: AsyncSession, user_id: int
    ) -> dict[str, Any] | None:
        if not self.settings.TRIAL_ENABLED or self.settings.TRIAL_DURATION_DAYS <= 0:
            return {
                "eligible": False,
                "activated": False,
                "message_key": "trial_feature_disabled",
            }

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logger.error("User %s not found in DB, cannot activate trial.", user_id)
            return {
                "eligible": False,
                "activated": False,
                "message_key": "user_not_found_for_trial",
            }

        if await self.has_trial_blocking_subscription(session, user_id):
            return {
                "eligible": False,
                "activated": False,
                "message_key": "trial_already_had_subscription_or_trial",
            }

        (
            panel_user_uuid,
            panel_sub_link_id,
            panel_short_uuid,
            _panel_user_created_now,
        ) = await self._get_or_create_panel_user_link_details(session, user_id, db_user)

        if not panel_user_uuid or not panel_sub_link_id:
            logger.error("Failed to get panel link details for trial user %s.", user_id)
            return {
                "eligible": True,
                "activated": False,
                "message_key": "trial_activation_failed_panel_link",
            }

        start_date = datetime.now(UTC)
        end_date = start_date + timedelta(days=self.settings.TRIAL_DURATION_DAYS)

        await subscription_dal.deactivate_other_active_subscriptions(
            session, panel_user_uuid, panel_sub_link_id
        )

        trial_premium_baseline_bytes = self._trial_premium_baseline_bytes()
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
            "premium_baseline_bytes": trial_premium_baseline_bytes,
            "premium_topup_balance_bytes": 0,
            "premium_topup_used_bytes": 0,
            "premium_used_bytes": 0,
            "premium_is_limited": False,
            "auto_renew_enabled": False,
            "provider": "trial",
            # Short trial: only warn a few hours before it ends, not days ahead.
            "suppress_early_expiry_notifications": True,
        }
        try:
            await subscription_dal.upsert_subscription(session, trial_sub_data)
        except Exception as e_upsert:
            logger.exception(
                "Failed to upsert trial subscription for user %s: %s", user_id, e_upsert
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
            traffic_limit_strategy=self.settings.TRIAL_TRAFFIC_STRATEGY,
            include_default_squads=False,
        )
        trial_squads = self._trial_all_panel_squad_uuids()
        panel_update_payload.update(
            await self.build_effective_panel_squad_fields(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                managed_internal_squads=trial_squads,
                include_internal_squads=bool(trial_squads),
                source="trial_activation",
            )
        )
        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))

        try:
            updated_panel_user = await self.panel_service.update_user_details_on_panel(
                panel_user_uuid, panel_update_payload
            )
        except Exception as exc:
            logger.exception(
                "Panel user details update raised for trial user %s: %s",
                panel_user_uuid,
                exc,
            )
            await session.rollback()
            return {
                "eligible": True,
                "activated": False,
                "message_key": "trial_activation_failed_panel_update",
            }
        if not updated_panel_user or updated_panel_user.get("error"):
            logger.warning(
                "Panel user details update FAILED for trial user %s. Response: %s",
                panel_user_uuid,
                updated_panel_user,
            )
            await session.rollback()
            return {
                "eligible": True,
                "activated": False,
                "message_key": "trial_activation_failed_panel_update",
            }

        await session.commit()

        await events.emit_model(
            TrialActivatedPayload(
                user_id=user_id,
                end_date=end_date,
                days=self.settings.TRIAL_DURATION_DAYS,
                traffic_gb=self.settings.TRIAL_TRAFFIC_LIMIT_GB,
            )
        )

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
