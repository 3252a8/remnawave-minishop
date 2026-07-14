from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.grants import GrantContext, resolve_effective_grant
from bot.services.panel_activity import record_subscription_panel_activity
from bot.services.payment_promo import consume_payment_promo, load_payment_promo_effects
from bot.utils.date_utils import add_months
from config.tariffs_config import default_currency_key_for_settings
from db.dal import (
    payment_dal,
    subscription_dal,
    tariff_dal,
    user_billing_dal,
    user_dal,
)

from . import entitlement_helpers
from ._typing import SubscriptionServiceMixinContract
from .entitlement_helpers import active_subscription_tariff_key as active_tariff_key
from .sale_mode import parse_sale_mode_context

logger = logging.getLogger(__name__)


class SubscriptionLifecycleActivationMixin(SubscriptionServiceMixinContract):
    async def activate_subscription(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        payment_amount: float,
        payment_db_id: int,
        promo_code_id_from_payment: int | None = None,
        provider: str = "yookassa",
        sale_mode: str = "subscription",
        traffic_gb: float | None = None,
        tariff_key: str | None = None,
    ) -> dict[str, Any] | None:

        sale_mode_context = parse_sale_mode_context(sale_mode, tariff_key)
        sale_mode_base = sale_mode_context.base
        tariff_key = sale_mode_context.tariff_key
        if sale_mode_base in {"traffic", "traffic_package"} or (
            getattr(self.settings, "traffic_sale_mode", False) and not self._tariffs_config()
        ):
            target_gb = traffic_gb if traffic_gb is not None else float(months)
            result = await self._activate_traffic_package(
                session=session,
                user_id=user_id,
                traffic_gb=target_gb,
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                tariff_key=tariff_key,
                sale_mode="traffic_package" if self._tariffs_config() else "traffic",
                promo_code_id_from_payment=promo_code_id_from_payment,
            )
            return result if isinstance(result, dict) else None
        if sale_mode_base == "topup":
            if not tariff_key:
                tariff_key = await active_tariff_key(session, user_id)
            if not tariff_key:
                logger.error("Top-up activation requires tariff_key for user %s", user_id)
                return None
            result = await self.activate_topup(
                session=session,
                user_id=user_id,
                tariff_key=tariff_key,
                traffic_gb=traffic_gb if traffic_gb is not None else float(months),
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                promo_code_id_from_payment=promo_code_id_from_payment,
            )
            return result if isinstance(result, dict) else None
        if sale_mode_base == "premium_topup":
            if not tariff_key:
                tariff_key = await active_tariff_key(session, user_id)
            if not tariff_key:
                logger.error("Premium top-up activation requires tariff_key for user %s", user_id)
                return None
            result = await self.activate_premium_topup(
                session=session,
                user_id=user_id,
                tariff_key=tariff_key,
                traffic_gb=traffic_gb if traffic_gb is not None else float(months),
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                promo_code_id_from_payment=promo_code_id_from_payment,
            )
            return result if isinstance(result, dict) else None
        if sale_mode_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
            target_devices = int(traffic_gb if traffic_gb is not None else months)
            result = await self.activate_hwid_device_topup(
                session=session,
                user_id=user_id,
                device_count=target_devices,
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                tariff_key=tariff_key,
                renewal=sale_mode_base == "hwid_devices_renewal",
            )
            return result if isinstance(result, dict) else None
        if sale_mode_base == "tariff_upgrade":
            if not tariff_key:
                logger.error("Tariff upgrade activation requires tariff_key for user %s", user_id)
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
                payment_id=payment_db_id,
            )
            if result:
                sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
                if sub:
                    result["end_date"] = sub.end_date
                    result["is_active"] = sub.is_active
                    db_user = await user_dal.get_user_by_id(session, user_id)
                    if db_user:
                        await self._send_payment_success_email(
                            db_user=db_user,
                            sale_mode="tariff_upgrade",
                            months=0,
                            traffic_gb=None,
                            payment_amount=payment_amount,
                            end_date=sub.end_date,
                            provider=provider,
                        )
            return result if isinstance(result, dict) else None

        tariff = self._resolve_tariff(tariff_key, "period") if self._tariffs_config() else None
        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode=sale_mode,
            tariff_key=tariff.key if tariff else tariff_key,
            purchased_gb=None,
        )
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        try:
            hwid_renewal_devices = int(getattr(payment, "purchased_hwid_devices", 0) or 0)
        except (TypeError, ValueError):
            hwid_renewal_devices = 0
        try:
            hwid_renewal_price = (
                float(getattr(payment, "hwid_full_price", 0) or 0)
                if hwid_renewal_devices > 0
                else 0.0
            )
        except (TypeError, ValueError):
            hwid_renewal_price = 0.0
        hwid_renewal_valid_from = self._as_aware_utc(
            getattr(payment, "hwid_valid_from", None) if payment else None
        )
        hwid_renewal_valid_until = self._as_aware_utc(
            getattr(payment, "hwid_valid_until", None) if payment else None
        )

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logger.error("User %s not found in DB for paid subscription activation.", user_id)
            return None

        previous_panel_user_uuid = getattr(db_user, "panel_user_uuid", None)

        try:
            months_int = int(months)
        except Exception:
            months_int = 1

        current_active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id
        )
        current_billing_model = self._subscription_billing_model(current_active_sub)
        current_panel_used = getattr(current_active_sub, "traffic_used_bytes", None)
        current_panel_limit = getattr(current_active_sub, "traffic_limit_bytes", None)
        if current_active_sub and current_billing_model == "traffic":
            try:
                panel_user_data = (
                    await self.panel_service.get_user_by_uuid(
                        current_active_sub.panel_user_uuid,
                        log_response=False,
                    )
                    or {}
                )
            except Exception:
                logger.exception(
                    "Failed to fetch panel traffic state before period activation for user %s",
                    user_id,
                )
                panel_user_data = {}
            if panel_user_data:
                await record_subscription_panel_activity(
                    session,
                    current_active_sub,
                    panel_user_data,
                )
                current_panel_used, current_panel_limit, _ = self._extract_panel_traffic_details(
                    panel_user_data
                )
            if current_panel_used is None:
                current_panel_used = getattr(current_active_sub, "traffic_used_bytes", None)
            if current_panel_limit is None:
                current_panel_limit = getattr(current_active_sub, "traffic_limit_bytes", None)
        start_date = datetime.now(UTC)
        if (
            current_active_sub
            and current_billing_model != "traffic"
            and current_active_sub.end_date
            and current_active_sub.end_date > start_date
        ):
            start_date = current_active_sub.end_date

        end_after_months = add_months(start_date, months_int)
        base_period_days = (end_after_months - start_date).days
        duration_days_total = base_period_days
        applied_promo_bonus_days = 0

        if promo_code_id_from_payment:
            promo_model, promo_effects = await load_payment_promo_effects(
                session,
                payment or promo_code_id_from_payment,
            )
            if promo_model is not None and promo_effects is not None:
                grant = resolve_effective_grant(
                    GrantContext(
                        sale_mode_base="subscription",
                        tariff_key=tariff.key if tariff else tariff_key,
                        base_period_days=base_period_days,
                        months=months_int,
                        charged_gb=None,
                        scope="regular",
                        promo=promo_effects,
                        period_start=start_date,
                        base_period_end=end_after_months,
                    )
                )
                consumed = await consume_payment_promo(
                    session=session,
                    user_id=user_id,
                    promo_model=promo_model,
                    effects=promo_effects,
                    payment_id=payment_db_id,
                    payment=payment,
                    sale_mode_base="subscription",
                    months=months_int,
                    traffic_gb=None,
                    granted_days=grant.extra_days,
                )
                if consumed:
                    applied_promo_bonus_days = grant.extra_days
                    duration_days_total += applied_promo_bonus_days
                else:
                    logger.warning(
                        "Attached code %s was not consumed for subscription payment %s.",
                        promo_code_id_from_payment,
                        payment_db_id,
                    )
            else:
                logger.warning(
                    "Promo code ID %s (from payment) not found or invalid.",
                    promo_code_id_from_payment,
                )
                promo_code_id_from_payment = None

        final_end_date = start_date + timedelta(days=duration_days_total)
        if hwid_renewal_devices > 0 and hwid_renewal_valid_until and applied_promo_bonus_days:
            hwid_renewal_valid_until = hwid_renewal_valid_until + timedelta(
                days=applied_promo_bonus_days
            )
            if payment:
                payment.hwid_valid_until = hwid_renewal_valid_until
        elif applied_promo_bonus_days > 0 and current_active_sub:
            try:
                await tariff_dal.extend_hwid_device_purchases_for_subscription_bonus(
                    session,
                    subscription_id=current_active_sub.subscription_id,
                    at=datetime.now(UTC),
                    subscription_end_before=start_date,
                    delta=timedelta(days=applied_promo_bonus_days),
                )
            except Exception:
                logger.exception(
                    "Failed to extend HWID device purchases for promo payment bonus of user %s",
                    user_id,
                )
        auto_renew_should_enable = False
        try:
            from bot.payment_providers import provider_supports_recurring
            from bot.payment_providers.shared import service_supports_recurring

            provider_key = str(provider or "").strip().lower()
            recurring_service_for = getattr(self, "recurring_service_for", None)
            recurring_service = (
                recurring_service_for(provider_key) if callable(recurring_service_for) else None
            )
            if provider_supports_recurring(provider_key) and service_supports_recurring(
                recurring_service
            ):
                auto_renew_should_enable = await user_billing_dal.user_has_saved_payment_method(
                    session, user_id, provider=provider_key
                )
        except Exception:
            logger.exception("Failed to evaluate auto-renew availability for user %s", user_id)

        if current_active_sub and current_billing_model == "traffic":
            topup_balance_bytes = self._traffic_package_carryover_bytes(
                current_active_sub,
                limit_bytes=current_panel_limit,
                used_bytes=current_panel_used,
            )
        else:
            topup_balance_bytes = int(getattr(current_active_sub, "topup_balance_bytes", 0) or 0)
        extra_hwid_devices = 0
        hwid_devices_valid_until = None
        if current_active_sub:
            try:
                hwid_summary = await tariff_dal.get_hwid_device_entitlement_summary(
                    session,
                    subscription_id=current_active_sub.subscription_id,
                    at=datetime.now(UTC),
                )
                extra_hwid_devices = int(hwid_summary.get("active_devices") or 0)
                hwid_devices_valid_until = hwid_summary.get("active_until")
            except Exception:
                logger.exception(
                    "Failed to recalculate active HWID devices for renewal of user %s",
                    user_id,
                )
                extra_hwid_devices = int(getattr(current_active_sub, "extra_hwid_devices", 0) or 0)
        premium_topup_balance_bytes = int(
            getattr(current_active_sub, "premium_topup_balance_bytes", 0) or 0
        )
        premium_topup_used_bytes = int(
            getattr(current_active_sub, "premium_topup_used_bytes", 0) or 0
        )
        premium_used_bytes = int(getattr(current_active_sub, "premium_used_bytes", 0) or 0)
        premium_period_start_at = getattr(current_active_sub, "premium_period_start_at", None)
        tier_baseline_bytes = (
            tariff.monthly_bytes if tariff else self.settings.user_traffic_limit_bytes
        )
        premium_baseline_bytes = tariff.premium_monthly_bytes if tariff else 0
        premium_limit_bytes = self._premium_effective_limit_bytes(
            premium_baseline_bytes,
            premium_topup_balance_bytes,
            premium_topup_used_bytes,
        )
        subscription_amount_for_pricing = max(0.0, float(payment_amount) - hwid_renewal_price)
        effective_monthly_price = subscription_amount_for_pricing / max(1, months_int)
        regular_bonus_carry = int(getattr(current_active_sub, "regular_bonus_bytes", 0) or 0)
        regular_unl_carry = bool(getattr(current_active_sub, "regular_unlimited_override", False))
        traffic_limit_bytes = self._traffic_limit_for_period_tariff(
            tariff,
            topup_balance_bytes,
            regular_bonus_carry,
            regular_unlimited_override=regular_unl_carry,
            traffic_used_bytes=0,
        )
        base_hwid_limit = self._base_hwid_limit_for_tariff(tariff)
        effective_hwid_limit = self._effective_hwid_limit(base_hwid_limit, extra_hwid_devices)
        premium_is_limited = bool(
            premium_limit_bytes > 0 and premium_used_bytes >= premium_limit_bytes
        )
        managed_squads = self._panel_squads_for_tariff(
            tariff,
            include_premium=not premium_is_limited,
        )
        (
            panel_user_uuid,
            panel_sub_link_id,
            panel_short_uuid,
            panel_user_created_now,
        ) = await self._get_or_create_panel_user_link_details(
            session,
            user_id,
            db_user,
            create_options=entitlement_helpers.panel_user_create_options(
                final_end_date,
                traffic_limit_bytes,
                self._period_tariff_traffic_strategy(),
                effective_hwid_limit,
                managed_squads,
                self.settings.parsed_user_external_squad_uuid,
            ),
        )
        if not panel_user_uuid or not panel_sub_link_id:
            logger.error("Failed to ensure panel user for TG %s during paid subscription.", user_id)
            return None

        await subscription_dal.deactivate_other_active_subscriptions(
            session, panel_user_uuid, panel_sub_link_id
        )
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
            # A real payment restores the full reminder spectrum, clearing any
            # trial/bonus suppression carried over on this panel subscription.
            "suppress_early_expiry_notifications": False,
            "auto_renew_enabled": auto_renew_should_enable,
            "tariff_key": tariff.key if tariff else None,
            "tier_baseline_bytes": tier_baseline_bytes,
            "topup_balance_bytes": topup_balance_bytes,
            "regular_bonus_bytes": regular_bonus_carry,
            "regular_unlimited_override": regular_unl_carry,
            "premium_baseline_bytes": premium_baseline_bytes,
            "premium_topup_balance_bytes": premium_topup_balance_bytes,
            "premium_topup_used_bytes": premium_topup_used_bytes,
            "premium_used_bytes": premium_used_bytes,
            "premium_is_limited": premium_is_limited,
            "premium_period_start_at": premium_period_start_at,
            "period_start_at": None,
            "is_throttled": False,
            "effective_monthly_price_rub": effective_monthly_price,
            "hwid_device_limit": base_hwid_limit,
            "extra_hwid_devices": extra_hwid_devices,
        }
        try:
            new_or_updated_sub = await subscription_dal.upsert_subscription(session, sub_payload)
        except Exception as e_upsert_sub:
            logger.exception(
                "Failed to upsert paid subscription for user %s: %s", user_id, e_upsert_sub
            )
            await self._compensate_failed_panel_user_creation(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                previous_panel_user_uuid=previous_panel_user_uuid,
                panel_user_created_now=panel_user_created_now,
                source="paid subscription DB write",
            )
            return None

        hwid_devices_renewed_count = 0
        hwid_devices_renewed_until = None
        if hwid_renewal_devices > 0:
            if (
                hwid_renewal_valid_from
                and hwid_renewal_valid_until
                and hwid_renewal_valid_from < hwid_renewal_valid_until
            ):
                await tariff_dal.create_hwid_device_purchase(
                    session,
                    subscription_id=new_or_updated_sub.subscription_id,
                    payment_id=payment_db_id,
                    purchased_devices=hwid_renewal_devices,
                    valid_from=hwid_renewal_valid_from,
                    valid_until=hwid_renewal_valid_until,
                )
                hwid_devices_renewed_count = hwid_renewal_devices
                hwid_devices_renewed_until = hwid_renewal_valid_until
            else:
                logger.warning(
                    "Skipping HWID renewal purchase for payment %s: invalid window %s -> %s",
                    payment_db_id,
                    hwid_renewal_valid_from,
                    hwid_renewal_valid_until,
                )

        panel_update_payload = self._build_panel_update_payload(
            panel_user_uuid=panel_user_uuid,
            expire_at=final_end_date,
            status="ACTIVE",
            traffic_limit_bytes=traffic_limit_bytes,
            traffic_limit_strategy=self._period_tariff_traffic_strategy(),
            hwid_device_limit=effective_hwid_limit,
            include_default_squads=False,
        )
        panel_update_payload.update(
            await self.build_effective_panel_squad_fields(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                managed_internal_squads=managed_squads,
                include_internal_squads=bool(tariff or managed_squads),
                source="paid_activation",
            )
        )

        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))

        if panel_user_created_now and previous_panel_user_uuid is None and not current_active_sub:
            # CREATE already requested the exact entitlement. Verify it with an
            # uncached GET instead of fabricating a successful PATCH response.
            panel_update_result = None
        else:
            panel_update_result = await self.panel_service.update_user_details_on_panel(
                panel_user_uuid, panel_update_payload
            )
        updated_panel_user = await self._confirmed_panel_entitlement(
            panel_user_uuid,
            panel_update_result,
            panel_update_payload,
            source="paid_activation",
        )
        if updated_panel_user is None:
            logger.warning(
                "Panel entitlement verification FAILED for paid sub user %s. Response: %s",
                panel_user_uuid,
                panel_update_result,
            )
            await self._compensate_failed_panel_user_creation(
                session,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                previous_panel_user_uuid=previous_panel_user_uuid,
                panel_user_created_now=panel_user_created_now,
                source="paid entitlement verification",
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
            "was_extension": current_active_sub is not None,
            "hwid_devices_renewal_recommended_count": 0
            if hwid_devices_renewed_count
            else extra_hwid_devices,
            "hwid_devices_valid_until": hwid_devices_renewed_until or hwid_devices_valid_until,
            "hwid_devices_renewed_count": hwid_devices_renewed_count,
            "hwid_devices_renewed_until": hwid_devices_renewed_until,
        }

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
            self._period_tariff_traffic_strategy(),
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
                    self._period_tariff_traffic_strategy() if panel_tariff else None
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
                if panel_tariff and "admin" in reason_lower:
                    return None
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
