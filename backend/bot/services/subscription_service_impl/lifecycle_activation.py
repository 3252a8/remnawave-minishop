from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.grants import GrantContext, resolve_effective_grant
from bot.services.panel_activity import record_subscription_panel_activity
from bot.services.payment_promo import consume_payment_promo, load_payment_promo_effects
from bot.utils.date_utils import add_months
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
        tariffs_config = self._tariffs_config()
        if tariffs_config and tariff_key:
            resolved_tariff = tariffs_config.get(tariff_key)
            if resolved_tariff is not None:
                tariff_key = resolved_tariff.key
        if sale_mode_base in {"traffic", "traffic_package"} or (
            getattr(self.settings, "traffic_sale_mode", False) and not tariffs_config
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
            hwid_device_bonus_bytes=self._hwid_device_traffic_bonus_bytes(extra_hwid_devices),
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
                self._period_tariff_traffic_strategy(tariff),
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
            traffic_limit_strategy=self._period_tariff_traffic_strategy(tariff),
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
