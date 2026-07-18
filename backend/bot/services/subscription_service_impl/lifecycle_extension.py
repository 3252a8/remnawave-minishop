from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config.tariffs_config import default_currency_key_for_settings
from db.dal import subscription_dal, tariff_dal, user_dal

from . import entitlement_helpers
from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


class SubscriptionLifecycleExtensionMixin(SubscriptionServiceMixinContract):
    async def extend_active_subscription_days(
        self,
        session: AsyncSession,
        user_id: int,
        bonus_days: int,
        reason: str = "bonus",
        extend_hwid_devices: bool = True,
        tariff_key: str | None = None,
        apply_tariff_hwid_limit: bool = False,
    ) -> datetime | None:
        reason_lower = (reason or "").lower()
        apply_main_traffic_limit = any(
            keyword in reason_lower for keyword in ("admin", "promo code", "referral", "bonus")
        )

        user = await user_dal.get_user_by_id(session, user_id)
        if not user:
            logger.warning("Cannot extend subscription for user %s: user not found.", user_id)
            return None

        previous_panel_user_uuid = getattr(user, "panel_user_uuid", None)
        active_sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
        rollback_payload: dict[str, Any] | None = None
        hwid_extension_context: tuple[int, datetime, datetime] | None = None
        pending_tariff_change_payload: dict[str, Any] | None = None
        requested_tariff = None
        if tariff_key and self._tariffs_config():
            try:
                requested_tariff = self._resolve_tariff(tariff_key, "period")
            except Exception:
                logger.warning(
                    "Unable to resolve requested tariff %s for %s extension of user %s.",
                    tariff_key,
                    reason,
                    user_id,
                    exc_info=True,
                )
                if "admin" in reason_lower:
                    return None

        admin_tariff = requested_tariff if active_sub and "admin" in reason_lower else None
        preserve_tariff_limits = bool(
            active_sub and active_sub.tariff_key and self._tariffs_config() and not admin_tariff
        )
        bonus_tariff = None
        if not active_sub and requested_tariff:
            bonus_tariff = requested_tariff
        now_utc = datetime.now(UTC)
        created_new_subscription = not active_sub or not active_sub.end_date
        if created_new_subscription:
            start_date = now_utc
            new_end_date_obj = start_date + timedelta(days=bonus_days)
            initial_traffic_limit = (
                self._traffic_limit_for_period_tariff(bonus_tariff)
                if bonus_tariff
                else self.settings.user_traffic_limit_bytes
                if apply_main_traffic_limit
                else self.settings.trial_traffic_limit_bytes
            )
            initial_hwid_limit = (
                self._base_hwid_limit_for_tariff(bonus_tariff) if bonus_tariff else None
            )
            initial_tariff = bonus_tariff
        else:
            current_end_date = active_sub.end_date
            start_point_for_bonus = current_end_date if current_end_date > now_utc else now_utc
            new_end_date_obj = start_point_for_bonus + timedelta(days=bonus_days)
            initial_traffic_limit = int(active_sub.traffic_limit_bytes or 0)
            initial_hwid_limit = self._effective_hwid_limit(
                getattr(active_sub, "hwid_device_limit", None),
                int(getattr(active_sub, "extra_hwid_devices", 0) or 0),
            )
            initial_tariff = admin_tariff
            if initial_tariff is None and active_sub.tariff_key and self._tariffs_config():
                try:
                    initial_tariff = self._resolve_tariff(active_sub.tariff_key, "period")
                except Exception:
                    logger.warning(
                        "Unable to resolve active tariff %s while extending user %s.",
                        active_sub.tariff_key,
                        user_id,
                    )

        initial_squads = self._panel_squads_for_tariff(initial_tariff)
        create_options = entitlement_helpers.panel_user_create_options(
            new_end_date_obj,
            initial_traffic_limit,
            self._period_tariff_traffic_strategy(initial_tariff),
            initial_hwid_limit,
            initial_squads,
            self.settings.parsed_user_external_squad_uuid,
        )
        (
            panel_uuid,
            panel_sub_uuid,
            _,
            panel_user_created_now,
        ) = await self._get_or_create_panel_user_link_details(
            session,
            user_id,
            user,
            create_options=create_options,
        )
        if not panel_uuid or not panel_sub_uuid:
            logger.error(
                "Failed to ensure panel user for subscription extension of user %s.", user_id
            )
            return None

        if not active_sub or not active_sub.end_date:
            logger.info(
                "No active subscription found for user %s. Creating new one for %s days.",
                user_id,
                bonus_days,
            )
            # Apply main traffic limit for admin/referral/promo bonuses, fallback to trial limit otherwise  # noqa: E501
            traffic_limit = initial_traffic_limit
            premium_baseline_bytes = bonus_tariff.premium_monthly_bytes if bonus_tariff else 0
            base_hwid_limit = (
                self._base_hwid_limit_for_tariff(bonus_tariff) if bonus_tariff else None
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
                "provider": entitlement_helpers.bonus_provider_for_reason(reason_lower),
                "auto_renew_enabled": False,
                "tariff_key": bonus_tariff.key if bonus_tariff else None,
                "tier_baseline_bytes": bonus_tariff.monthly_bytes if bonus_tariff else None,
                "topup_balance_bytes": 0,
                "regular_bonus_bytes": 0,
                "regular_unlimited_override": False,
                "premium_baseline_bytes": premium_baseline_bytes,
                "premium_topup_balance_bytes": 0,
                "premium_topup_used_bytes": 0,
                "premium_used_bytes": 0,
                "premium_is_limited": False,
                "premium_period_start_at": None,
                "period_start_at": None,
                "is_throttled": False,
                "hwid_device_limit": base_hwid_limit,
                "extra_hwid_devices": 0,
                # Registration/referral bonus grants are short-lived, like a
                # trial: only warn a few hours before they end, not days ahead.
                "suppress_early_expiry_notifications": True,
            }
            await subscription_dal.deactivate_other_active_subscriptions(
                session, panel_uuid, panel_sub_uuid
            )
            updated_sub_model = await subscription_dal.upsert_subscription(
                session, bonus_sub_payload
            )
            rollback_payload = {
                "is_active": False,
                "status_from_panel": "PANEL_UPDATE_FAILED",
                "last_notification_sent": None,
            }
        else:
            current_end_date = active_sub.end_date
            rollback_payload = {
                "end_date": current_end_date,
                "last_notification_sent": getattr(active_sub, "last_notification_sent", None),
                "is_active": getattr(active_sub, "is_active", True),
                "status_from_panel": getattr(active_sub, "status_from_panel", None),
            }
            for attr in (
                "tariff_key",
                "tier_baseline_bytes",
                "topup_balance_bytes",
                "regular_bonus_bytes",
                "regular_unlimited_override",
                "traffic_limit_bytes",
                "premium_baseline_bytes",
                "premium_topup_balance_bytes",
                "premium_topup_used_bytes",
                "premium_used_bytes",
                "premium_bonus_bytes",
                "premium_is_limited",
                "premium_period_start_at",
                "period_start_at",
                "is_throttled",
                "effective_monthly_price_rub",
                "hwid_device_limit",
                "extra_hwid_devices",
            ):
                if hasattr(active_sub, attr):
                    rollback_payload[attr] = getattr(active_sub, attr)

            updated_sub_model = await subscription_dal.update_subscription_end_date(
                session, active_sub.subscription_id, new_end_date_obj
            )
            if updated_sub_model and extend_hwid_devices:
                hwid_extension_context = (
                    active_sub.subscription_id,
                    now_utc,
                    current_end_date,
                )

            if admin_tariff and updated_sub_model:
                try:
                    extra_hwid_devices = await tariff_dal.sum_active_hwid_devices(
                        session,
                        subscription_id=active_sub.subscription_id,
                        at=now_utc,
                    )
                except Exception:
                    logger.exception(
                        "Failed to recalculate HWID devices during admin tariff assignment "
                        "for user %s",
                        user_id,
                    )
                    extra_hwid_devices = int(getattr(active_sub, "extra_hwid_devices", 0) or 0)

                premium_topup_balance = int(
                    getattr(active_sub, "premium_topup_balance_bytes", 0) or 0
                )
                premium_topup_used = int(getattr(active_sub, "premium_topup_used_bytes", 0) or 0)
                premium_bonus_bytes = int(getattr(active_sub, "premium_bonus_bytes", 0) or 0)
                premium_baseline = admin_tariff.premium_monthly_bytes
                premium_limit = self._premium_effective_limit_bytes(
                    premium_baseline,
                    premium_topup_balance,
                    premium_topup_used,
                    premium_bonus_bytes,
                )
                premium_used = int(getattr(active_sub, "premium_used_bytes", 0) or 0)
                rb = int(getattr(active_sub, "regular_bonus_bytes", 0) or 0)
                runl = bool(getattr(active_sub, "regular_unlimited_override", False))
                used_sub = int(getattr(active_sub, "traffic_used_bytes", 0) or 0)
                target_monthly_price = self._tariff_effective_monthly_price(
                    admin_tariff,
                    default_currency_key_for_settings(self.settings),
                )
                local_hwid_base_limit, _ = self._transition_hwid_base_limits(
                    getattr(active_sub, "hwid_device_limit", None),
                    admin_tariff,
                    apply_tariff_hwid_limit=apply_tariff_hwid_limit,
                )
                admin_update_data: dict[str, Any] = {
                    "tariff_key": admin_tariff.key,
                    "tier_baseline_bytes": admin_tariff.monthly_bytes,
                    "traffic_limit_bytes": self._compute_main_traffic_limit_bytes(
                        tier_baseline_bytes=admin_tariff.monthly_bytes,
                        topup_balance_bytes=int(getattr(active_sub, "topup_balance_bytes", 0) or 0),
                        regular_bonus_bytes=rb,
                        regular_unlimited_override=runl,
                        traffic_used_bytes=used_sub,
                        hwid_device_bonus_bytes=(
                            await self._hwid_device_traffic_bonus_bytes_for_sub(session, active_sub)
                        ),
                    ),
                    "premium_baseline_bytes": premium_baseline,
                    "premium_topup_balance_bytes": premium_topup_balance,
                    "premium_topup_used_bytes": premium_topup_used,
                    "premium_is_limited": bool(premium_limit > 0 and premium_used >= premium_limit),
                    "period_start_at": None,
                    "is_throttled": False,
                    "effective_monthly_price_rub": target_monthly_price,
                    "hwid_device_limit": local_hwid_base_limit,
                    "extra_hwid_devices": extra_hwid_devices,
                }
                updated_sub_model = await subscription_dal.update_subscription(
                    session,
                    updated_sub_model.subscription_id,
                    admin_update_data,
                )
                if updated_sub_model and active_sub.tariff_key != admin_tariff.key:
                    pending_tariff_change_payload = {
                        "subscription_id": updated_sub_model.subscription_id,
                        "from_tariff_key": active_sub.tariff_key,
                        "to_tariff_key": admin_tariff.key,
                        "mode": "admin_assign",
                        "payment_id": None,
                        "days_before": max(0, (current_end_date - now_utc).days)
                        if current_end_date
                        else None,
                        "days_after": max(0, (new_end_date_obj - now_utc).days)
                        if new_end_date_obj
                        else None,
                        "converted_bytes": None,
                        "converted_hwid_value_rub": None,
                        "converted_hwid_days": None,
                        "eff_price_before": active_sub.effective_monthly_price_rub,
                        "eff_price_after": target_monthly_price,
                    }

            if (
                apply_main_traffic_limit
                and not preserve_tariff_limits
                and not admin_tariff
                and updated_sub_model
                and updated_sub_model.traffic_limit_bytes != self.settings.user_traffic_limit_bytes
            ):
                updated_sub_model = await subscription_dal.update_subscription(
                    session,
                    updated_sub_model.subscription_id,
                    {"traffic_limit_bytes": self.settings.user_traffic_limit_bytes},
                )

        if updated_sub_model:
            panel_tariff = admin_tariff or bonus_tariff
            panel_hwid_base_limit = None
            if panel_tariff:
                _, panel_hwid_base_limit = self._transition_hwid_base_limits(
                    getattr(updated_sub_model, "hwid_device_limit", None),
                    panel_tariff,
                    apply_tariff_hwid_limit=False,
                )
            panel_update_payload = self._build_panel_update_payload(
                expire_at=new_end_date_obj,
                status="ACTIVE" if panel_tariff else None,
                traffic_limit_bytes=(
                    updated_sub_model.traffic_limit_bytes
                    if panel_tariff
                    else self.settings.user_traffic_limit_bytes
                    if apply_main_traffic_limit and not preserve_tariff_limits
                    else None
                ),
                traffic_limit_strategy=(
                    self._period_tariff_traffic_strategy(panel_tariff) if panel_tariff else None
                ),
                hwid_device_limit=(
                    self._effective_hwid_limit(
                        panel_hwid_base_limit,
                        int(getattr(updated_sub_model, "extra_hwid_devices", 0) or 0),
                    )
                    if panel_tariff
                    else None
                ),
                include_uuid=False,
                include_default_squads=False,
            )
            if panel_tariff:
                managed_squads = self._panel_squads_for_tariff(
                    panel_tariff,
                    include_premium=not bool(
                        getattr(updated_sub_model, "premium_is_limited", False)
                    ),
                )
                panel_update_payload.update(
                    await self.build_effective_panel_squad_fields(
                        session,
                        user_id=user_id,
                        panel_user_uuid=panel_uuid,
                        managed_internal_squads=managed_squads,
                        include_internal_squads=True,
                        source="admin_extend",
                    )
                )

            if (
                created_new_subscription
                and panel_user_created_now
                and previous_panel_user_uuid is None
            ):
                # Confirm the persisted CREATE result through an uncached GET.
                panel_update_result = None
                expected_panel_payload = self._build_panel_update_payload(
                    panel_user_uuid=panel_uuid,
                    expire_at=new_end_date_obj,
                    status="ACTIVE",
                    traffic_limit_bytes=create_options.default_traffic_limit_bytes,
                    traffic_limit_strategy=create_options.default_traffic_limit_strategy,
                    hwid_device_limit=(
                        create_options.hwid_device_limit
                        if create_options.hwid_device_limit is not None
                        else getattr(self.settings, "USER_HWID_DEVICE_LIMIT", None)
                    ),
                    include_default_squads=False,
                )
                expected_panel_payload["activeInternalSquads"] = list(
                    create_options.specific_squad_uuids
                )
                if create_options.external_squad_uuid:
                    expected_panel_payload["externalSquadUuid"] = create_options.external_squad_uuid
            else:
                panel_update_result = await self.panel_service.update_user_details_on_panel(
                    panel_uuid,
                    panel_update_payload,
                )
                expected_panel_payload = panel_update_payload
            confirmed_panel_user = await self._confirmed_panel_entitlement(
                panel_uuid,
                panel_update_result,
                expected_panel_payload,
                source="subscription_bonus",
            )
            if confirmed_panel_user is None:
                logger.warning(
                    "Panel expiry update failed for user %s panel_uuid=%s after %s bonus. "
                    "requested_expire_at=%s panel_response=%s. Reverting local bonus update.",
                    user_id,
                    panel_uuid,
                    reason,
                    new_end_date_obj.isoformat(),
                    panel_update_result,
                )
                if created_new_subscription:
                    try:
                        await session.delete(updated_sub_model)
                        await session.flush()
                    except Exception:
                        logger.exception(
                            "Failed to delete rejected bonus subscription for user %s.",
                            user_id,
                        )
                    await self._compensate_failed_panel_user_creation(
                        session,
                        user_id=user_id,
                        panel_user_uuid=panel_uuid,
                        previous_panel_user_uuid=previous_panel_user_uuid,
                        panel_user_created_now=panel_user_created_now,
                        source="bonus panel update",
                    )
                elif rollback_payload:
                    try:
                        await subscription_dal.update_subscription(
                            session,
                            updated_sub_model.subscription_id,
                            rollback_payload,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to revert local subscription update for user %s after "
                            "panel expiry update failure.",
                            user_id,
                        )
                return None

            if pending_tariff_change_payload:
                await entitlement_helpers.record_tariff_change_best_effort(
                    session,
                    pending_tariff_change_payload,
                    user_id=user_id,
                )

            if hwid_extension_context:
                try:
                    subscription_id, hwid_now, previous_end_date = hwid_extension_context
                    await tariff_dal.extend_hwid_device_purchases_for_subscription_bonus(
                        session,
                        subscription_id=subscription_id,
                        at=hwid_now,
                        subscription_end_before=previous_end_date,
                        delta=timedelta(days=bonus_days),
                    )
                except Exception:
                    logger.exception(
                        "Failed to extend HWID device purchases for %s bonus of user %s",
                        reason,
                        user_id,
                    )

            logger.info(
                "Subscription for user %s extended by %s days (%s). New end date: %s.",
                user_id,
                bonus_days,
                reason,
                new_end_date_obj,
            )
            return new_end_date_obj
        else:
            logger.error("Failed to update subscription end date locally for user %s.", user_id)
            return None
