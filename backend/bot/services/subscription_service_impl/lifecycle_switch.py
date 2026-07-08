import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.config_link import prepare_config_links
from bot.utils.traffic_reset import next_traffic_reset_after, traffic_accounting_period_start
from config.tariffs_config import default_currency_key_for_settings
from db.dal import subscription_dal, tariff_dal, user_dal
from db.models import Subscription, User

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


class SubscriptionLifecycleSwitchMixin(SubscriptionServiceMixinContract):
    async def _local_active_subscription_details_fallback(
        self,
        db_user: User,
        local_active_sub: Subscription,
    ) -> dict[str, Any]:
        panel_sub_id = str(local_active_sub.panel_subscription_uuid or "").strip()
        config_link_raw = (
            await self.panel_service.get_subscription_link(panel_sub_id) if panel_sub_id else None
        )
        display_link, connect_button_url = await prepare_config_links(
            self.settings,
            config_link_raw,
        )
        tariff = None
        if local_active_sub.tariff_key and self._tariffs_config():
            try:
                tariff = self._resolve_tariff(local_active_sub.tariff_key)
            except Exception:
                tariff = None
        language = db_user.language_code or self.settings.DEFAULT_LANGUAGE
        premium_access = (
            await self.premium_access_for_tariff(tariff)
            if tariff
            else {"squad_uuids": [], "squad_labels": [], "node_labels": []}
        )
        premium_baseline = int(local_active_sub.premium_baseline_bytes or 0)
        premium_topup_balance = int(local_active_sub.premium_topup_balance_bytes or 0)
        premium_topup_used = int(getattr(local_active_sub, "premium_topup_used_bytes", 0) or 0)
        premium_bonus_bytes = int(getattr(local_active_sub, "premium_bonus_bytes", 0) or 0)
        premium_unlimited_override = bool(
            getattr(local_active_sub, "premium_unlimited_override", False)
        )
        premium_limit_bytes = self._premium_effective_limit_bytes(
            premium_baseline,
            premium_topup_balance,
            premium_topup_used,
            premium_bonus_bytes,
        )
        billing_model_display = (
            tariff.billing_model
            if tariff
            else ("traffic" if getattr(self.settings, "traffic_sale_mode", False) else "period")
        )
        now = datetime.now(UTC)
        traffic_limit_strategy = (
            self._period_tariff_traffic_strategy()
            if billing_model_display == "period"
            else "NO_RESET"
        )
        traffic_period_start_at = getattr(local_active_sub, "period_start_at", None)
        traffic_next_reset_at = None
        if billing_model_display == "period":
            traffic_period_start_at = traffic_accounting_period_start(
                traffic_limit_strategy,
                now,
                subscription_start_at=getattr(local_active_sub, "start_date", None),
                previous_period_start_at=getattr(local_active_sub, "period_start_at", None),
            )
            traffic_next_reset_at = next_traffic_reset_after(
                traffic_period_start_at,
                traffic_limit_strategy,
                now=now,
            )
        premium_period_start_at = self._premium_accounting_period_start(local_active_sub, now)
        premium_next_reset_at = None
        if premium_limit_bytes > 0 and not premium_unlimited_override:
            premium_next_reset_at = next_traffic_reset_after(
                premium_period_start_at,
                self._period_tariff_traffic_strategy(),
                now=now,
            )
        return {
            "user_id": db_user.panel_user_uuid,
            "panel_subscription_uuid": local_active_sub.panel_subscription_uuid,
            "panel_short_uuid": local_active_sub.panel_subscription_uuid,
            "end_date": local_active_sub.end_date,
            "status_from_panel": local_active_sub.status_from_panel or "LOCAL_CACHE",
            "config_link": display_link,
            "connect_button_url": connect_button_url,
            "traffic_limit_bytes": local_active_sub.traffic_limit_bytes,
            "traffic_used_bytes": local_active_sub.traffic_used_bytes,
            "traffic_limit_strategy": traffic_limit_strategy,
            "tariff_key": local_active_sub.tariff_key,
            "tariff_name": tariff.name(language) if tariff else None,
            "tariff_description": tariff.description(language) if tariff else None,
            "premium_title": tariff.premium_name(language) if tariff else None,
            "billing_model": billing_model_display,
            "tier_baseline_bytes": local_active_sub.tier_baseline_bytes,
            "topup_balance_bytes": local_active_sub.topup_balance_bytes,
            "regular_bonus_bytes": int(getattr(local_active_sub, "regular_bonus_bytes", 0) or 0),
            "regular_unlimited_override": bool(
                getattr(local_active_sub, "regular_unlimited_override", False)
            ),
            "premium_baseline_bytes": premium_baseline,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "premium_used_bytes": local_active_sub.premium_used_bytes,
            "premium_bonus_bytes": premium_bonus_bytes,
            "premium_unlimited_override": premium_unlimited_override,
            "premium_limit_bytes": premium_limit_bytes,
            "premium_is_limited": bool(local_active_sub.premium_is_limited),
            "premium_period_start_at": premium_period_start_at,
            "premium_next_reset_at": premium_next_reset_at,
            "premium_squad_labels": premium_access.get("squad_labels") or [],
            "premium_node_labels": premium_access.get("node_labels") or [],
            "period_start_at": traffic_period_start_at,
            "traffic_next_reset_at": traffic_next_reset_at,
            "is_throttled": bool(local_active_sub.is_throttled),
            "base_hwid_device_limit": local_active_sub.hwid_device_limit,
            "extra_hwid_devices": int(local_active_sub.extra_hwid_devices or 0),
            "extra_hwid_devices_valid_until": None,
            "extra_hwid_devices_valid_until_text": None,
            "extra_hwid_devices_next_valid_from": None,
            "device_topup_renewal_available": False,
            "user_bot_username": db_user.username,
            "is_panel_data": False,
            "max_devices": self._effective_hwid_limit(
                local_active_sub.hwid_device_limit,
                int(local_active_sub.extra_hwid_devices or 0),
            ),
        }

    async def switch_tariff_without_payment(
        self,
        session: AsyncSession,
        user_id: int,
        target_tariff_key: str,
        mode: str,
        payment_id: int | None = None,
        apply_tariff_hwid_limit: bool = False,
    ) -> dict[str, Any] | None:
        config = self._tariffs_config()
        if not config:
            return None
        target = config.require(target_tariff_key)
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None
        before_tariff_key = sub.tariff_key
        now = datetime.now(UTC)
        trial_provider = str(getattr(sub, "provider", "") or "").strip().lower() == "trial"
        trial_status = str(getattr(sub, "status_from_panel", "") or "").strip().upper() == "TRIAL"
        convert_trial_admin_assignment = mode == "admin_assign" and (trial_provider or trial_status)
        if mode == "admin_assign":
            options = dict(self.calculate_tariff_switch_options(sub, target))
        else:
            options = await self.calculate_tariff_switch_options_with_hwid(session, sub, target)
        converted_hwid_purchase_ids = list(options.get("convertible_hwid_purchase_ids") or [])
        if converted_hwid_purchase_ids:
            await tariff_dal.expire_hwid_device_purchases(
                session,
                purchase_ids=converted_hwid_purchase_ids,
                at=now,
            )
        premium_topup_balance = int(sub.premium_topup_balance_bytes or 0)
        premium_topup_used = int(getattr(sub, "premium_topup_used_bytes", 0) or 0)
        premium_baseline = target.premium_monthly_bytes
        premium_limit = self._premium_effective_limit_bytes(
            premium_baseline,
            premium_topup_balance,
            premium_topup_used,
        )
        premium_used = int(sub.premium_used_bytes or 0)
        update_data: dict[str, Any] = {
            "tariff_key": target.key,
            "is_throttled": False,
            "premium_baseline_bytes": premium_baseline,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "premium_is_limited": bool(premium_limit > 0 and premium_used >= premium_limit),
        }
        if convert_trial_admin_assignment:
            update_data.update(
                {
                    "provider": "admin",
                    "status_from_panel": "ACTIVE",
                    "skip_notifications": False,
                    "suppress_early_expiry_notifications": False,
                }
            )
        converted_bytes = None
        local_hwid_base_limit, panel_hwid_base_limit = self._transition_hwid_base_limits(
            getattr(sub, "hwid_device_limit", None),
            target,
            apply_tariff_hwid_limit=apply_tariff_hwid_limit,
        )
        try:
            extra_hwid_devices = await tariff_dal.sum_active_hwid_devices(
                session,
                subscription_id=sub.subscription_id,
                at=now,
            )
        except Exception:
            logger.exception(
                "Failed to recalculate HWID devices during tariff switch for user %s",
                user_id,
            )
            extra_hwid_devices = int(sub.extra_hwid_devices or 0)
        update_data["hwid_device_limit"] = local_hwid_base_limit
        update_data["extra_hwid_devices"] = extra_hwid_devices

        if target.billing_model == "period":
            update_data["tier_baseline_bytes"] = target.monthly_bytes
            rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
            runl = bool(getattr(sub, "regular_unlimited_override", False))
            used_sub = int(sub.traffic_used_bytes or 0)
            update_data["traffic_limit_bytes"] = self._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=target.monthly_bytes,
                topup_balance_bytes=int(sub.topup_balance_bytes or 0),
                regular_bonus_bytes=rb,
                regular_unlimited_override=runl,
                traffic_used_bytes=used_sub,
            )
            update_data["period_start_at"] = None
            update_data["effective_monthly_price_rub"] = target.period_price(
                1, default_currency_key_for_settings(self.settings)
            ) or target.min_period_price(default_currency_key_for_settings(self.settings))
            if convert_trial_admin_assignment and not getattr(sub, "duration_months", None):
                update_data["duration_months"] = 1
            if mode == "recalc_days" and options.get("recalc_days") is not None:
                update_data["end_date"] = now + timedelta(days=int(options["recalc_days"]))
        else:
            converted_gb = float(options.get("converted_gb", 0))
            converted_bytes = self.gb_to_bytes(converted_gb)
            old_topup = int(sub.topup_balance_bytes or 0)
            new_balance = old_topup + converted_bytes
            rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
            runl = bool(getattr(sub, "regular_unlimited_override", False))
            panel_user = (
                await self.panel_service.get_user_by_uuid(
                    db_user.panel_user_uuid, log_response=False
                )
                or {}
            )
            current_used, _, _ = self._extract_panel_traffic_details(panel_user)
            cur_used_int = int(current_used or 0)
            update_data.update(
                {
                    "end_date": self._far_future(),
                    "period_start_at": None,
                    "tier_baseline_bytes": 0,
                    "topup_balance_bytes": new_balance,
                    "traffic_limit_bytes": self._compute_main_traffic_limit_bytes(
                        tier_baseline_bytes=0,
                        topup_balance_bytes=new_balance,
                        regular_bonus_bytes=rb,
                        regular_unlimited_override=runl,
                        traffic_used_bytes=cur_used_int,
                    ),
                    "traffic_used_bytes": current_used,
                    "effective_monthly_price_rub": None,
                    "auto_renew_enabled": False,
                    "skip_notifications": True,
                }
            )
            if convert_trial_admin_assignment:
                update_data["duration_months"] = None

        updated = await subscription_dal.update_subscription(
            session, sub.subscription_id, update_data
        )
        if not updated:
            return None
        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=updated.end_date,
            status="ACTIVE",
            traffic_limit_bytes=updated.traffic_limit_bytes,
            traffic_limit_strategy=(
                "NO_RESET"
                if target.billing_model == "traffic"
                else self._period_tariff_traffic_strategy()
            ),
            hwid_device_limit=self._effective_hwid_limit(
                panel_hwid_base_limit,
                extra_hwid_devices,
            ),
        )
        panel_payload["activeInternalSquads"] = self._panel_squads_for_tariff(
            target,
            include_premium=not bool(updated.premium_is_limited),
        )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        updated_panel = await self.panel_service.update_user_details_on_panel(
            db_user.panel_user_uuid, panel_payload
        )
        if not updated_panel or updated_panel.get("error"):
            # The tariff row is already swapped locally; if the panel rejects
            # the squad/limit update the user sees the new tariff in the app
            # but stays on the old squads on Remnawave. Surface the failure
            # so the caller can roll back.
            logger.warning(
                "Panel user details update FAILED for tariff switch user %s -> %s. Response: %s",
                user_id,
                target.key,
                updated_panel,
            )
            return None
        panel_subscription_uuid = str(getattr(updated, "panel_subscription_uuid", "") or "").strip()
        if panel_subscription_uuid:
            await subscription_dal.deactivate_other_active_subscriptions(
                session,
                db_user.panel_user_uuid,
                panel_subscription_uuid,
            )
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
                "payment_id": payment_id,
                "days_before": options.get("remaining_days"),
                "days_after": (updated.end_date - now).days
                if updated.end_date and target.billing_model == "period"
                else None,
                "converted_bytes": converted_bytes,
                "converted_hwid_value_rub": options.get("converted_hwid_value_rub"),
                "converted_hwid_days": options.get("converted_hwid_days"),
                "eff_price_before": sub.effective_monthly_price_rub,
                "eff_price_after": updated.effective_monthly_price_rub,
            },
        )
        return {"subscription_id": updated.subscription_id, "tariff_key": target.key}
