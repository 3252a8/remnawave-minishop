from bot.infra import events
from bot.infra.event_payloads import TrialActivatedPayload

from ._runtime import (
    Any,
    AsyncSession,
    Dict,
    Optional,
    SubscriptionServiceMixinContract,
    datetime,
    logging,
    subscription_dal,
    timedelta,
    timezone,
    user_dal,
)


class TrialSubscriptionMixin(SubscriptionServiceMixinContract):
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
            panel_user_created_now,
        ) = await self._get_or_create_panel_user_link_details(session, user_id, db_user)

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
            traffic_limit_strategy=self.settings.TRIAL_TRAFFIC_STRATEGY,
            include_default_squads=False,
        )
        trial_squads = self._trial_all_panel_squad_uuids()
        if trial_squads:
            panel_update_payload["activeInternalSquads"] = trial_squads
        if self.settings.parsed_user_external_squad_uuid:
            panel_update_payload["externalSquadUuid"] = (
                self.settings.parsed_user_external_squad_uuid
            )

        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))

        updated_panel_user = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid, panel_update_payload
        )
        if not updated_panel_user or updated_panel_user.get("error"):
            logging.warning(
                f"Panel user details update FAILED for trial user {panel_user_uuid}. Response: {updated_panel_user}"  # noqa: E501
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
