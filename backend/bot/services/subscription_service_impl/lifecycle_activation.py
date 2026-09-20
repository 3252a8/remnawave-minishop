from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.grants import GrantContext, resolve_effective_grant
from bot.services import subscription_order_terms as order_terms
from bot.services.checkout_addons import checkout_addon_grants
from bot.services.gift_purchase import gift_activation_bonuses
from bot.services.panel_activity import record_subscription_panel_activity
from bot.services.payment_promo import (
    PaymentPromoRedemptionError,
    consume_payment_promo,
    load_payment_promo_effects,
)
from bot.services.trial_days import paid_subscription_period_start
from bot.utils.date_utils import add_months
from config.subscription_periods import (
    add_period_days,
    days_to_legacy_months,
    legacy_months_to_days,
    positive_period,
)
from db.dal import (
    payment_dal,
    subscription_dal,
    tariff_dal,
    user_billing_dal,
    user_dal,
)

from . import entitlement_helpers
from ._typing import SubscriptionServiceMixinContract
from .activation_topups import record_activation_topups
from .entitlement_helpers import active_subscription_tariff_key as active_tariff_key
from .sale_mode import parse_sale_mode_context
from .traffic import resolve_main_traffic_baseline

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
        authoritative_end_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        sale_mode_context = parse_sale_mode_context(sale_mode, tariff_key)
        sale_mode_base = sale_mode_context.base
        tariff_key = sale_mode_context.tariff_key
        tariffs_config = self._tariffs_config()
        period_payment = (
            await payment_dal.get_payment_by_db_id(session, payment_db_id)
            if sale_mode_base == "subscription"
            else None
        )
        frozen_terms = order_terms.read_subscription_terms(period_payment)
        frozen_tariff = frozen_terms.tariff if frozen_terms else None
        if tariff_key and not tariffs_config and frozen_tariff is None:
            logger.error(
                "Tariff-scoped %s activation requires an available tariff catalog "
                "for user %s (tariff=%s).",
                sale_mode_base,
                user_id,
                tariff_key,
            )
            return None
        if tariffs_config and tariff_key:
            resolved_tariff = frozen_tariff or tariffs_config.get(tariff_key)
            if resolved_tariff is None:
                logger.error(
                    "Tariff-scoped %s activation references unknown tariff %s for user %s.",
                    sale_mode_base,
                    tariff_key,
                    user_id,
                )
                return None
            tariff_key = resolved_tariff.key
        if (
            tariffs_config
            and sale_mode_base == "subscription"
            and not tariff_key
            and frozen_terms is None
        ):
            logger.error(
                "Paid subscription activation requires tariff_key when the tariff catalog "
                "is enabled for user %s.",
                user_id,
            )
            return None
        if sale_mode_base in {"traffic", "traffic_package"} or (
            getattr(self.settings, "traffic_sale_mode", False)
            and not tariffs_config
            and frozen_terms is None
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

        tariff = (
            frozen_terms.tariff
            if frozen_terms
            else (self._resolve_tariff(tariff_key, "period") if tariffs_config else None)
        )
        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode=sale_mode,
            tariff_key=tariff.key if tariff else tariff_key,
            purchased_gb=None,
        )
        payment = period_payment
        fixed_duration_days = (
            positive_period(payment.subscription_duration_days)
            if payment is not None and getattr(payment, "period_semantics", None) == "fixed_days"
            else None
        )
        checkout_grants = checkout_addon_grants(
            getattr(payment, "checkout_bundle_snapshot", None) if payment else None
        )
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
            months_int = (
                days_to_legacy_months(fixed_duration_days) or 0
                if fixed_duration_days
                else positive_period(
                    getattr(payment, "subscription_duration_months", None) or months
                )
            )
        except (ValueError, TypeError):
            logger.error("Missing billing period for payment %s", payment_db_id)
            return None
        expected_tariff_key = tariff.key if tariff else tariff_key
        if checkout_grants.has_addons and (
            checkout_grants.tariff_key != expected_tariff_key
            or (
                checkout_grants.duration_days != fixed_duration_days
                if checkout_grants.duration_days is not None
                else checkout_grants.months != months_int
            )
        ):
            logger.error(
                "Checkout add-on snapshot mismatch for payment %s: tariff=%s/%s months=%s/%s",
                payment_db_id,
                checkout_grants.tariff_key,
                expected_tariff_key,
                checkout_grants.months,
                months_int,
            )
            return None

        if checkout_grants.has_addons:
            current_active_sub = (
                await subscription_dal.get_active_subscription_by_user_id_for_update(
                    session, user_id
                )
            )
        else:
            current_active_sub = await subscription_dal.get_active_subscription_by_user_id(
                session, user_id
            )
        current_active_is_trial = entitlement_helpers.subscription_is_trial(current_active_sub)
        if checkout_grants.active_context_present:
            current_subscription_id = (
                int(current_active_sub.subscription_id) if current_active_sub is not None else None
            )
            current_end_at = self._as_aware_utc(
                getattr(current_active_sub, "end_date", None) if current_active_sub else None
            )
            if (
                current_subscription_id != checkout_grants.active_subscription_id
                or current_end_at != checkout_grants.active_end_at
            ):
                logger.error(
                    "Checkout quote became stale for payment %s: subscription=%s/%s end=%s/%s",
                    payment_db_id,
                    checkout_grants.active_subscription_id,
                    current_subscription_id,
                    checkout_grants.active_end_at,
                    current_end_at,
                )
                return None
        if (
            checkout_grants.has_addons
            and current_active_sub
            and tariff
            and not current_active_is_trial
        ):
            active_key = str(getattr(current_active_sub, "tariff_key", "") or "").strip()
            active_tariff = (
                tariff
                if active_key == tariff.key
                else (self._resolve_tariff(active_key) if active_key else None)
            )
            if active_tariff is None or active_tariff.key != tariff.key:
                logger.error(
                    "Subscription checkout cannot switch tariff for payment %s: %s -> %s",
                    payment_db_id,
                    active_key,
                    tariff.key,
                )
                return None
        previous_squad_subscription = current_active_sub
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
        activation_at = datetime.now(UTC)
        # Keep the paid period boundary separate from immutable entitlement history.
        period_start_date = paid_subscription_period_start(
            activation_at,
            current_active_sub,
            current_billing_model,
            current_active_is_trial,
            checkout_grants.trial_days_strategy,
        )
        if fixed_duration_days is not None:
            period_start_date = period_start_date.astimezone(UTC)
        subscription_start_date = entitlement_helpers.immutable_subscription_start(
            current_active_sub if current_billing_model != "traffic" else None,
            now=activation_at,
        )

        end_after_months = (
            add_period_days(period_start_date, fixed_duration_days)
            if fixed_duration_days is not None
            else add_months(period_start_date, months_int)
        )
        base_period_days = (end_after_months - period_start_date).days
        (
            applied_promo_bonus_days,
            applied_promo_regular_traffic_gb,
            applied_promo_premium_traffic_gb,
        ) = await gift_activation_bonuses(session, payment_db_id, user_id, provider)
        duration_days_total = base_period_days + applied_promo_bonus_days
        if provider == "gift":
            promo_code_id_from_payment = None

        if promo_code_id_from_payment:
            promo_model, promo_effects = await load_payment_promo_effects(
                session,
                payment or promo_code_id_from_payment,
            )
            if promo_model is not None and promo_effects is not None:
                if promo_effects.premium_traffic_gb > 0 and (
                    tariff is None or not tariff.premium_squad_uuids
                ):
                    raise PaymentPromoRedemptionError(
                        "Premium promo traffic requires a premium-enabled tariff"
                    )
                grant = resolve_effective_grant(
                    GrantContext(
                        sale_mode_base="subscription",
                        tariff_key=tariff.key if tariff else tariff_key,
                        base_period_days=base_period_days,
                        months=months_int,
                        charged_gb=None,
                        scope="regular",
                        promo=promo_effects,
                        period_start=period_start_date,
                        base_period_end=end_after_months,
                        duration_days=fixed_duration_days,
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
                    granted_regular_traffic_gb=promo_effects.regular_traffic_gb or None,
                    granted_premium_traffic_gb=promo_effects.premium_traffic_gb or None,
                )
                if consumed:
                    applied_promo_bonus_days = grant.extra_days
                    applied_promo_regular_traffic_gb = promo_effects.regular_traffic_gb
                    applied_promo_premium_traffic_gb = promo_effects.premium_traffic_gb
                    duration_days_total = base_period_days + applied_promo_bonus_days
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

        final_end_date = order_terms.paid_period_end(
            period_start_date,
            duration_days_total,
            self._as_aware_utc(authoritative_end_at),
            applied_promo_bonus_days,
        )
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
                    subscription_end_before=period_start_date,
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
        promo_regular_traffic_bytes = self.gb_to_bytes(applied_promo_regular_traffic_gb)
        legacy_checkout_regular_bytes = self.gb_to_bytes(checkout_grants.legacy_regular_topup_gb)
        topup_balance_bytes += promo_regular_traffic_bytes + legacy_checkout_regular_bytes
        extra_hwid_devices = 0
        hwid_traffic_bonus_bytes = 0
        hwid_devices_valid_until = None
        if current_active_sub:
            try:
                hwid_summary = await tariff_dal.get_hwid_device_entitlement_summary(
                    session,
                    subscription_id=current_active_sub.subscription_id,
                    at=datetime.now(UTC),
                )
                extra_hwid_devices = int(hwid_summary.get("active_devices") or 0)
                hwid_traffic_bonus_bytes = self._hwid_traffic_bonus_bytes_from_summary(hwid_summary)
                hwid_devices_valid_until = hwid_summary.get("active_until")
            except Exception:
                logger.exception(
                    "Failed to recalculate active HWID devices for renewal of user %s",
                    user_id,
                )
                raise
        premium_topup_balance_bytes = int(
            getattr(current_active_sub, "premium_topup_balance_bytes", 0) or 0
        )
        promo_premium_traffic_bytes = self.gb_to_bytes(applied_promo_premium_traffic_gb)
        legacy_checkout_premium_bytes = self.gb_to_bytes(checkout_grants.legacy_premium_topup_gb)
        premium_topup_balance_bytes += promo_premium_traffic_bytes + legacy_checkout_premium_bytes
        premium_topup_used_bytes = int(
            getattr(current_active_sub, "premium_topup_used_bytes", 0) or 0
        )
        premium_used_bytes = int(getattr(current_active_sub, "premium_used_bytes", 0) or 0)
        premium_period_start_at = getattr(current_active_sub, "premium_period_start_at", None)
        base_tier_bytes, ordered_hwid_limit = order_terms.subscription_limits(
            frozen_terms, tariff, self.settings
        )
        base_premium_bytes = tariff.premium_monthly_bytes if tariff else 0
        if current_active_is_trial:
            current_tier_bytes = int(base_tier_bytes or 0)
        elif current_active_sub is not None and tariff is not None:
            current_tier_bytes = await resolve_main_traffic_baseline(
                session,
                current_active_sub,
                tariff,
                at=activation_at,
            )
        else:
            current_tier_bytes = int(
                getattr(current_active_sub, "tier_baseline_bytes", 0) or base_tier_bytes or 0
            )
        current_premium_bytes = (
            int(base_premium_bytes or 0)
            if current_active_is_trial
            else int(
                getattr(current_active_sub, "premium_baseline_bytes", 0) or base_premium_bytes or 0
            )
        )
        selected_tier_bytes = (
            self.gb_to_bytes(checkout_grants.regular_limit_gb)
            if checkout_grants.regular_limit_gb is not None
            else None
        )
        selected_premium_bytes = (
            self.gb_to_bytes(checkout_grants.premium_limit_gb)
            if checkout_grants.premium_limit_gb is not None
            else None
        )
        tier_baseline_bytes = current_tier_bytes
        premium_baseline_bytes = current_premium_bytes
        if selected_tier_bytes is not None and (
            current_active_sub is None or selected_tier_bytes > current_tier_bytes
        ):
            tier_baseline_bytes = selected_tier_bytes
        if selected_premium_bytes is not None and (
            current_active_sub is None or selected_premium_bytes > current_premium_bytes
        ):
            premium_baseline_bytes = selected_premium_bytes
        premium_bonus_carry = int(getattr(current_active_sub, "premium_bonus_bytes", 0) or 0)
        if promo_premium_traffic_bytes > 0 or legacy_checkout_premium_bytes > 0:
            premium_overflow_to_cover = max(
                0,
                premium_used_bytes
                - premium_baseline_bytes
                - premium_topup_used_bytes
                - premium_bonus_carry,
            )
            premium_consume_now = min(premium_topup_balance_bytes, premium_overflow_to_cover)
            premium_topup_balance_bytes -= premium_consume_now
            premium_topup_used_bytes += premium_consume_now
        premium_limit_bytes = self._premium_effective_limit_bytes(
            premium_baseline_bytes,
            premium_topup_balance_bytes,
            premium_topup_used_bytes,
            premium_bonus_carry,
        )
        subscription_bundle_amount = max(0.0, float(payment_amount) - hwid_renewal_price)
        subscription_amount_for_pricing = subscription_bundle_amount
        if checkout_grants.base_subscription_amount is not None:
            snapshot_total = (
                checkout_grants.base_subscription_amount + checkout_grants.addons_amount
            )
            if snapshot_total > 0:
                subscription_amount_for_pricing = max(
                    0.0,
                    subscription_bundle_amount
                    * checkout_grants.base_subscription_amount
                    / snapshot_total,
                )
        effective_monthly_price = (
            subscription_amount_for_pricing * 30 / fixed_duration_days
            if fixed_duration_days is not None
            else subscription_amount_for_pricing / max(1, months_int)
        )
        regular_bonus_carry = int(getattr(current_active_sub, "regular_bonus_bytes", 0) or 0)
        regular_unl_carry = bool(getattr(current_active_sub, "regular_unlimited_override", False))
        premium_unl_carry = bool(getattr(current_active_sub, "premium_unlimited_override", False))
        traffic_limit_bytes = self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=tier_baseline_bytes,
            topup_balance_bytes=topup_balance_bytes,
            regular_bonus_bytes=regular_bonus_carry,
            regular_unlimited_override=regular_unl_carry,
            traffic_used_bytes=0,
            hwid_device_bonus_bytes=hwid_traffic_bonus_bytes,
        )
        base_hwid_limit = ordered_hwid_limit
        checkout_devices_active_now = 0
        checkout_device_bonus_bytes = self.gb_to_bytes(checkout_grants.device_traffic_bonus_gb)
        checkout_device_bonus_active_now = 0
        if checkout_grants.device_count > 0:
            if current_active_sub is None or period_start_date <= activation_at:
                checkout_devices_active_now = checkout_grants.device_count
                checkout_device_bonus_active_now = checkout_device_bonus_bytes
            elif checkout_grants.device_count > extra_hwid_devices:
                checkout_devices_active_now = checkout_grants.device_count - extra_hwid_devices
                checkout_device_bonus_active_now = max(
                    0,
                    checkout_device_bonus_bytes - hwid_traffic_bonus_bytes,
                )
        if checkout_devices_active_now:
            extra_hwid_devices += checkout_devices_active_now
            hwid_traffic_bonus_bytes += checkout_device_bonus_active_now
            traffic_limit_bytes = self._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=tier_baseline_bytes,
                topup_balance_bytes=topup_balance_bytes,
                regular_bonus_bytes=regular_bonus_carry,
                regular_unlimited_override=regular_unl_carry,
                traffic_used_bytes=0,
                hwid_device_bonus_bytes=hwid_traffic_bonus_bytes,
            )
        effective_hwid_limit = self._effective_hwid_limit(base_hwid_limit, extra_hwid_devices)
        premium_is_limited = self._premium_access_should_be_limited(
            tariff,
            premium_limit_bytes=premium_limit_bytes,
            premium_used_bytes=premium_used_bytes,
            premium_unlimited_override=premium_unl_carry,
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
                tariff.key if tariff else None,
            ),
        )
        if not panel_user_uuid or not panel_sub_link_id:
            logger.error("Failed to ensure panel user for TG %s during paid subscription.", user_id)
            return None

        if previous_squad_subscription is None and not panel_user_created_now:
            previous_squad_subscription = (
                await subscription_dal.get_subscription_by_panel_subscription_uuid(
                    session,
                    panel_sub_link_id,
                )
            )
        previous_managed_squads: list[str] = []
        if previous_squad_subscription is not None:
            previous_managed_squads, _ = self._managed_panel_squad_uuids_for_subscription(
                previous_squad_subscription
            )
        override_detection_managed_squads = list(
            dict.fromkeys([*previous_managed_squads, *(managed_squads or [])])
        )
        # Older releases could persist trial squads as panel-discovered manual
        # overrides during this transition. Remove only those automatic rows;
        # explicit admin overrides remain active.
        await self.deactivate_panel_managed_internal_overrides(
            session,
            user_id=user_id,
            panel_user_uuid=panel_user_uuid,
            managed_internal_squads=previous_managed_squads,
        )

        await subscription_dal.deactivate_other_active_subscriptions(
            session, panel_user_uuid, panel_sub_link_id
        )
        sub_payload = {
            "user_id": user_id,
            "panel_user_uuid": panel_user_uuid,
            "panel_subscription_uuid": panel_sub_link_id,
            "start_date": subscription_start_date,
            "end_date": final_end_date,
            "duration_months": days_to_legacy_months(fixed_duration_days)
            if fixed_duration_days is not None
            else months_int,
            "period_semantics": "fixed_days"
            if fixed_duration_days is not None
            else "calendar_months",
            "duration_days": fixed_duration_days
            if fixed_duration_days is not None
            else legacy_months_to_days(months_int),
            "is_active": True,
            "status_from_panel": "ACTIVE",
            "traffic_limit_bytes": traffic_limit_bytes,
            "provider": provider,
            "gift_terms_snapshot": order_terms.gift_entitlement_snapshot(provider, payment),
            "skip_notifications": False,
            # A real payment restores the full reminder spectrum, clearing any
            # trial/bonus suppression carried over on this panel subscription.
            "suppress_early_expiry_notifications": False,
            "auto_renew_enabled": auto_renew_should_enable,
            "tariff_key": tariff.key if tariff else None,
            "tariff_binding_source": "payment" if tariff else None,
            "tariff_bound_at": datetime.now(UTC) if tariff else None,
            "tariff_binding_note": (f"paid_activation:{provider}" if tariff else None),
            "tier_baseline_bytes": tier_baseline_bytes,
            "topup_balance_bytes": topup_balance_bytes,
            "regular_bonus_bytes": regular_bonus_carry,
            "regular_unlimited_override": regular_unl_carry,
            "premium_baseline_bytes": premium_baseline_bytes,
            "premium_topup_balance_bytes": premium_topup_balance_bytes,
            "premium_topup_used_bytes": premium_topup_used_bytes,
            "premium_used_bytes": premium_used_bytes,
            "premium_bonus_bytes": premium_bonus_carry,
            "premium_unlimited_override": premium_unl_carry,
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
                    traffic_bonus_bytes=getattr(payment, "hwid_traffic_bonus_bytes", None),
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

        if (
            checkout_devices_active_now > 0
            and current_active_sub is not None
            and activation_at < period_start_date
        ):
            await tariff_dal.create_hwid_device_purchase(
                session,
                subscription_id=new_or_updated_sub.subscription_id,
                payment_id=payment_db_id,
                purchased_devices=checkout_devices_active_now,
                traffic_bonus_bytes=checkout_device_bonus_active_now,
                valid_from=activation_at,
                valid_until=period_start_date,
            )

        if checkout_grants.device_count > 0:
            await tariff_dal.create_hwid_device_purchase(
                session,
                subscription_id=new_or_updated_sub.subscription_id,
                payment_id=payment_db_id,
                purchased_devices=checkout_grants.device_count,
                traffic_bonus_bytes=self.gb_to_bytes(checkout_grants.device_traffic_bonus_gb),
                valid_from=period_start_date,
                valid_until=final_end_date,
            )

        for kind, selected_bytes, monthly_amount, monthly_stars, immediate_applies in (
            (
                "traffic",
                selected_tier_bytes,
                checkout_grants.regular_monthly_amount,
                checkout_grants.regular_monthly_stars,
                checkout_grants.regular_immediate_applies,
            ),
            (
                "premium_traffic",
                selected_premium_bytes,
                checkout_grants.premium_monthly_amount,
                checkout_grants.premium_monthly_stars,
                checkout_grants.premium_immediate_applies,
            ),
        ):
            if selected_bytes is None or tariff is None:
                continue
            current_bytes = current_tier_bytes if kind == "traffic" else current_premium_bytes
            if (
                current_active_sub is not None
                and (immediate_applies or selected_bytes > current_bytes)
                and activation_at < period_start_date
            ):
                await tariff_dal.create_flexible_traffic_limit(
                    session,
                    subscription_id=new_or_updated_sub.subscription_id,
                    payment_id=payment_db_id,
                    kind=kind,
                    tariff_key=tariff.key,
                    limit_bytes=selected_bytes,
                    valid_from=activation_at,
                    valid_until=period_start_date,
                    monthly_amount=monthly_amount,
                    monthly_stars_amount=monthly_stars,
                )
            await tariff_dal.create_flexible_traffic_limit(
                session,
                subscription_id=new_or_updated_sub.subscription_id,
                payment_id=payment_db_id,
                kind=kind,
                tariff_key=tariff.key,
                limit_bytes=selected_bytes,
                valid_from=period_start_date,
                valid_until=final_end_date,
                monthly_amount=monthly_amount,
                monthly_stars_amount=monthly_stars,
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
                override_detection_managed_internal_squads=(override_detection_managed_squads),
                include_internal_squads=bool(tariff or managed_squads),
                source="paid_activation",
            )
        )

        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))
        panel_user_for_tag = self._take_panel_user_link_snapshot(panel_user_uuid)
        tariff_tag_plan = (
            self._plan_panel_tariff_tag(
                db_user,
                panel_user_for_tag,
                tariff.key if tariff else None,
                source="paid_activation",
            )
            if panel_user_for_tag is not None
            else None
        )
        if tariff_tag_plan is not None:
            panel_update_payload.update(tariff_tag_plan.verification_payload)

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
        if tariff_tag_plan is not None:
            self._remember_confirmed_panel_tariff_tag(
                db_user,
                tariff_tag_plan,
                updated_panel_user,
            )

        await record_activation_topups(
            session,
            subscription_id=new_or_updated_sub.subscription_id,
            payment_id=payment_db_id,
            promo_regular_bytes=promo_regular_traffic_bytes,
            promo_premium_bytes=promo_premium_traffic_bytes,
            checkout_regular_bytes=legacy_checkout_regular_bytes,
            checkout_premium_bytes=legacy_checkout_premium_bytes,
        )

        final_subscription_url = updated_panel_user.get("subscriptionUrl")
        final_panel_short_uuid = updated_panel_user.get("shortUuid", panel_short_uuid)
        await self._send_payment_success_email(
            db_user=db_user,
            sale_mode="subscription",
            months=months_int,
            duration_days=fixed_duration_days,
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
            "applied_promo_regular_traffic_gb": applied_promo_regular_traffic_gb,
            "applied_promo_premium_traffic_gb": applied_promo_premium_traffic_gb,
            "tariff_key": tariff.key if tariff else None,
            "duration_days": fixed_duration_days,
            "was_extension": current_active_sub is not None,
            "hwid_devices_renewal_recommended_count": 0
            if hwid_devices_renewed_count
            else extra_hwid_devices,
            "hwid_devices_valid_until": hwid_devices_renewed_until or hwid_devices_valid_until,
            "hwid_devices_renewed_count": hwid_devices_renewed_count,
            "hwid_devices_renewed_until": hwid_devices_renewed_until,
            "checkout_addon_devices": checkout_grants.device_count,
            "checkout_addon_regular_limit_gb": checkout_grants.regular_limit_gb,
            "checkout_addon_premium_limit_gb": checkout_grants.premium_limit_gb,
        }
