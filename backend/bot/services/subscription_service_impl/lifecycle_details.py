import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.config_link import prepare_config_links
from bot.utils.traffic_reset import (
    next_traffic_reset_after,
    panel_next_traffic_reset_at,
    traffic_accounting_period_start,
)
from db.dal import subscription_dal, tariff_dal, user_dal

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


class SubscriptionLifecycleDetailsMixin(SubscriptionServiceMixinContract):
    async def get_active_subscription_details(
        self, session: AsyncSession, user_id: int
    ) -> dict[str, Any] | None:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            logger.info(
                "User %s not found in DB or no panel_user_uuid for 'my_subscription'.", user_id
            )
            return None

        panel_user_uuid = db_user.panel_user_uuid
        local_active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, panel_user_uuid
        )
        (
            panel_user_data,
            panel_user_confirmed_absent,
            panel_lookup_failure_reason,
        ) = await self._lookup_panel_user_for_subscription_details(panel_user_uuid)
        now = datetime.now(UTC)

        if not panel_user_data:
            if panel_user_confirmed_absent:
                logger.warning(
                    "Panel user %s confirmed absent on panel for user %s. "
                    "Clearing local linkage. reason=%s",
                    panel_user_uuid,
                    user_id,
                    panel_lookup_failure_reason,
                )
                await subscription_dal.deactivate_all_user_subscriptions(session, user_id)
                await user_dal.update_user(session, user_id, {"panel_user_uuid": None})
                return None
            logger.warning(
                "Panel user %s lookup failed for user %s; treating it as a panel access/API "
                "problem and preserving local linkage/subscription. reason=%s",
                panel_user_uuid,
                user_id,
                panel_lookup_failure_reason,
            )
            if local_active_sub:
                fallback = await self._local_active_subscription_details_fallback(
                    db_user,
                    local_active_sub,
                )
                return fallback if isinstance(fallback, dict) else None
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
            panel_traffic_used, panel_traffic_limit, _ = self._extract_panel_traffic_details(
                panel_user_data
            )
            panel_sub_uuid_from_panel = panel_user_data.get(
                "subscriptionUuid"
            ) or panel_user_data.get("shortUuid")

            if local_active_sub.status_from_panel != panel_status:
                update_payload_local["status_from_panel"] = panel_status
            if panel_expire_at_str:
                panel_expire_dt = datetime.fromisoformat(panel_expire_at_str.replace("Z", "+00:00"))
                if local_active_sub.end_date.replace(microsecond=0) != panel_expire_dt.replace(
                    microsecond=0
                ):
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
                and local_active_sub.panel_subscription_uuid != panel_sub_uuid_from_panel
            ):
                update_payload_local["panel_subscription_uuid"] = panel_sub_uuid_from_panel

            is_active_based_on_panel = panel_status == "ACTIVE" and (
                panel_expire_dt > now if panel_expire_dt else False
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
        panel_traffic_used, panel_traffic_limit, panel_traffic_strategy = (
            self._extract_panel_traffic_details(panel_user_data)
        )
        config_link_raw = panel_user_data.get("subscriptionUrl")
        display_link, connect_button_url = await prepare_config_links(
            self.settings, config_link_raw
        )
        hwid_limit = panel_user_data.get("hwidDeviceLimit")
        if hwid_limit is None:
            if local_active_sub and local_active_sub.hwid_device_limit is not None:
                hwid_limit = self._effective_hwid_limit(
                    local_active_sub.hwid_device_limit,
                    int(local_active_sub.extra_hwid_devices or 0),
                )
            else:
                hwid_limit = self.settings.USER_HWID_DEVICE_LIMIT
        tariff = None
        if local_active_sub and local_active_sub.tariff_key and self._tariffs_config():
            try:
                tariff = self._resolve_tariff(local_active_sub.tariff_key)
            except Exception:
                tariff = None
        billing_model_display = (
            tariff.billing_model
            if tariff
            else ("traffic" if getattr(self.settings, "traffic_sale_mode", False) else "period")
        )
        traffic_limit_strategy = panel_traffic_strategy
        if not traffic_limit_strategy:
            traffic_limit_strategy = (
                self._period_tariff_traffic_strategy()
                if billing_model_display == "period"
                else "NO_RESET"
            )
        premium_access = (
            await self.premium_access_for_tariff(tariff)
            if tariff
            else {
                "squad_uuids": [],
                "squad_labels": [],
                "node_labels": [],
            }
        )
        premium_baseline = (
            int(local_active_sub.premium_baseline_bytes or 0) if local_active_sub else 0
        )
        premium_topup_balance = (
            int(local_active_sub.premium_topup_balance_bytes or 0) if local_active_sub else 0
        )
        premium_topup_used = (
            int(getattr(local_active_sub, "premium_topup_used_bytes", 0) or 0)
            if local_active_sub
            else 0
        )
        premium_bonus_bytes = (
            int(getattr(local_active_sub, "premium_bonus_bytes", 0) or 0) if local_active_sub else 0
        )
        premium_unlimited_override = (
            bool(getattr(local_active_sub, "premium_unlimited_override", False))
            if local_active_sub
            else False
        )
        regular_bonus_bytes = (
            int(getattr(local_active_sub, "regular_bonus_bytes", 0) or 0) if local_active_sub else 0
        )
        regular_unlimited_override = (
            bool(getattr(local_active_sub, "regular_unlimited_override", False))
            if local_active_sub
            else False
        )
        hwid_entitlement_summary: dict[str, Any] = {}
        active_extra_hwid_devices = (
            int(local_active_sub.extra_hwid_devices or 0) if local_active_sub else 0
        )
        if local_active_sub:
            try:
                hwid_entitlement_summary = await tariff_dal.get_hwid_device_entitlement_summary(
                    session,
                    subscription_id=local_active_sub.subscription_id,
                    at=now,
                )
                active_extra_hwid_devices = int(hwid_entitlement_summary.get("active_devices") or 0)
                if active_extra_hwid_devices != int(local_active_sub.extra_hwid_devices or 0):
                    await subscription_dal.update_subscription(
                        session,
                        local_active_sub.subscription_id,
                        {"extra_hwid_devices": active_extra_hwid_devices},
                    )
                    local_active_sub.extra_hwid_devices = active_extra_hwid_devices
            except Exception:
                logger.exception(
                    "Failed to load HWID entitlement summary for subscription %s",
                    local_active_sub.subscription_id,
                )
            base_hwid_limit_for_payload = (
                local_active_sub.hwid_device_limit
                if local_active_sub.hwid_device_limit is not None
                else self._base_hwid_limit_for_tariff(tariff)
            )
            expected_hwid_limit = self._effective_hwid_limit(
                base_hwid_limit_for_payload,
                active_extra_hwid_devices,
            )
            if expected_hwid_limit is not None:
                hwid_limit = expected_hwid_limit

        extra_hwid_valid_until = hwid_entitlement_summary.get("active_until")
        extra_hwid_next_valid_from = hwid_entitlement_summary.get("next_valid_from")
        device_topup_renewal_available = self._device_topup_renewal_available(
            active_extra_hwid_devices,
            extra_hwid_valid_until,
            panel_end_date,
        )
        effective_traffic_strategy = str(traffic_limit_strategy or "")
        traffic_period_start_at = None
        traffic_next_reset_at = None
        if local_active_sub and billing_model_display == "period":
            traffic_period_start_at = traffic_accounting_period_start(
                effective_traffic_strategy,
                now,
                subscription_start_at=getattr(local_active_sub, "start_date", None),
                previous_period_start_at=getattr(local_active_sub, "period_start_at", None),
                panel_user_data=panel_user_data,
            )
            traffic_next_reset_at = panel_next_traffic_reset_at(
                panel_user_data,
                fallback_strategy=effective_traffic_strategy,
                now=now,
            ) or next_traffic_reset_after(
                traffic_period_start_at,
                effective_traffic_strategy,
                now=now,
            )

        premium_limit_bytes = self._premium_effective_limit_bytes(
            premium_baseline,
            premium_topup_balance,
            premium_topup_used,
            premium_bonus_bytes,
        )
        premium_period_start_at = (
            self._premium_accounting_period_start(
                local_active_sub,
                now,
                panel_user_data=panel_user_data,
            )
            if local_active_sub
            else None
        )
        premium_next_reset_at = None
        if local_active_sub and premium_limit_bytes > 0 and not premium_unlimited_override:
            premium_next_reset_at = next_traffic_reset_after(
                premium_period_start_at,
                self._period_tariff_traffic_strategy(),
                now=now,
            )

        return {
            "user_id": panel_user_data.get("uuid"),
            "panel_subscription_uuid": panel_user_data.get("subscriptionUuid")
            or panel_user_data.get("shortUuid")
            or (local_active_sub.panel_subscription_uuid if local_active_sub else None),
            "panel_short_uuid": panel_user_data.get("shortUuid"),
            "end_date": panel_end_date,
            "status_from_panel": panel_user_data.get("status", "UNKNOWN").upper(),
            "config_link": display_link,
            "connect_button_url": connect_button_url,
            "traffic_limit_bytes": panel_traffic_limit,
            "traffic_used_bytes": panel_traffic_used,
            "traffic_limit_strategy": traffic_limit_strategy,
            "tariff_key": local_active_sub.tariff_key if local_active_sub else None,
            "tariff_name": tariff.name(db_user.language_code or self.settings.DEFAULT_LANGUAGE)
            if tariff
            else None,
            "tariff_description": tariff.description(
                db_user.language_code or self.settings.DEFAULT_LANGUAGE
            )
            if tariff
            else None,
            "premium_title": tariff.premium_name(
                db_user.language_code or self.settings.DEFAULT_LANGUAGE
            )
            if tariff
            else None,
            "billing_model": billing_model_display,
            "tier_baseline_bytes": local_active_sub.tier_baseline_bytes
            if local_active_sub
            else None,
            "topup_balance_bytes": local_active_sub.topup_balance_bytes if local_active_sub else 0,
            "regular_bonus_bytes": regular_bonus_bytes,
            "regular_unlimited_override": regular_unlimited_override,
            "premium_baseline_bytes": premium_baseline,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "premium_used_bytes": local_active_sub.premium_used_bytes if local_active_sub else 0,
            "premium_bonus_bytes": premium_bonus_bytes,
            "premium_unlimited_override": premium_unlimited_override,
            "premium_limit_bytes": premium_limit_bytes,
            "premium_is_limited": bool(local_active_sub.premium_is_limited)
            if local_active_sub
            else False,
            "premium_period_start_at": premium_period_start_at,
            "premium_next_reset_at": premium_next_reset_at,
            "premium_squad_labels": premium_access.get("squad_labels") or [],
            "premium_node_labels": premium_access.get("node_labels") or [],
            "period_start_at": traffic_period_start_at
            or (local_active_sub.period_start_at if local_active_sub else None),
            "traffic_next_reset_at": traffic_next_reset_at,
            "is_throttled": bool(local_active_sub.is_throttled) if local_active_sub else False,
            "base_hwid_device_limit": local_active_sub.hwid_device_limit
            if local_active_sub
            else None,
            "extra_hwid_devices": active_extra_hwid_devices,
            "extra_hwid_devices_valid_until": extra_hwid_valid_until,
            "extra_hwid_devices_valid_until_text": self._display_datetime_text(
                extra_hwid_valid_until
            ),
            "extra_hwid_devices_next_valid_from": extra_hwid_next_valid_from,
            "device_topup_renewal_available": device_topup_renewal_available,
            "user_bot_username": db_user.username,
            "is_panel_data": True,
            "max_devices": hwid_limit,
        }

    async def get_subscriptions_ending_soon(
        self, session: AsyncSession, days_threshold: int
    ) -> list[dict[str, Any]]:
        subs_models_with_users = await subscription_dal.get_subscriptions_near_expiration(
            session, days_threshold
        )
        results = []
        for sub_model in subs_models_with_users:
            if sub_model.user and sub_model.end_date and not sub_model.skip_notifications:
                days_left = (sub_model.end_date - datetime.now(UTC)).total_seconds() / (24 * 3600)
                results.append(
                    {
                        "user_id": sub_model.user_id,
                        "first_name": sub_model.user.first_name or f"User {sub_model.user_id}",
                        "language_code": sub_model.user.language_code
                        or self.settings.DEFAULT_LANGUAGE,
                        "end_date_str": sub_model.end_date.strftime("%Y-%m-%d"),
                        "days_left": max(0, round(days_left)),
                        "subscription_end_date_iso_for_update": sub_model.end_date,
                    }
                )
        return results
