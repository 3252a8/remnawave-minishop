import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.grants import GrantContext, resolve_effective_grant
from bot.services.payment_promo import consume_payment_promo, load_payment_promo_effects
from bot.services.subscription_order_terms import gift_tariff
from db.dal import payment_dal, subscription_dal, tariff_dal, user_dal

from ._typing import SubscriptionServiceMixinContract
from .entitlement_helpers import record_traffic_topup_best_effort
from .panel_squad_sync import PanelSquadSyncMixin

logger = logging.getLogger(__name__)


class TopupMixin(PanelSquadSyncMixin, SubscriptionServiceMixinContract):
    async def grant_promo_entitlements(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        bonus_days: int = 0,
        regular_traffic_gb: float = 0,
        premium_traffic_gb: float = 0,
    ) -> dict[str, Any] | None:
        """Grant one standalone promo atomically to an existing subscription.

        Traffic is credited to the same carry-over balances as paid top-ups, so
        unused bytes survive accounting-period resets until they are consumed.
        """

        days = max(0, int(bonus_days or 0))
        regular_gb = float(regular_traffic_gb or 0)
        premium_gb = float(premium_traffic_gb or 0)
        if regular_gb < 0 or premium_gb < 0 or (days == 0 and regular_gb == premium_gb == 0):
            return None

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id_for_update(session, user_id)
        if not sub:
            return None
        tariff = (
            (gift_tariff(sub) or self._resolve_tariff(sub.tariff_key)) if sub.tariff_key else None
        )
        if premium_gb > 0 and (tariff is None or not tariff.premium_squad_uuids):
            return None

        now = datetime.now(UTC)
        previous_end_date = sub.end_date
        new_end_date = (
            max(previous_end_date, now) + timedelta(days=days) if days > 0 else previous_end_date
        )
        regular_bytes = self.gb_to_bytes(regular_gb)
        premium_bytes = self.gb_to_bytes(premium_gb)
        previous_values: dict[str, Any] = {
            "end_date": previous_end_date,
            "topup_balance_bytes": int(sub.topup_balance_bytes or 0),
            "traffic_limit_bytes": int(sub.traffic_limit_bytes or 0),
            "premium_baseline_bytes": int(sub.premium_baseline_bytes or 0),
            "premium_topup_balance_bytes": int(sub.premium_topup_balance_bytes or 0),
            "premium_topup_used_bytes": int(sub.premium_topup_used_bytes or 0),
            "premium_used_bytes": int(sub.premium_used_bytes or 0),
            "premium_is_limited": bool(sub.premium_is_limited),
            "premium_period_start_at": sub.premium_period_start_at,
            "is_throttled": bool(sub.is_throttled),
            "last_notification_sent": sub.last_notification_sent,
            "hwid_device_limit": sub.hwid_device_limit,
            "extra_hwid_devices": int(sub.extra_hwid_devices or 0),
        }

        new_topup_balance = previous_values["topup_balance_bytes"] + regular_bytes
        new_regular_limit = previous_values["traffic_limit_bytes"]
        hwid_base_limit = previous_values["hwid_device_limit"]
        hwid_extra = previous_values["extra_hwid_devices"]
        hwid_effective_limit = self._effective_hwid_limit(hwid_base_limit, hwid_extra)
        if regular_bytes > 0:
            baseline = int(sub.tier_baseline_bytes or (tariff.monthly_bytes if tariff else 0) or 0)
            regular_bonus = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
            regular_unlimited = bool(getattr(sub, "regular_unlimited_override", False))
            traffic_used = int(getattr(sub, "traffic_used_bytes", 0) or 0)
            hwid_limits = await self._resolve_hwid_device_limits(session, sub, tariff)
            hwid_base_limit = hwid_limits.base
            hwid_extra = hwid_limits.extra
            hwid_effective_limit = hwid_limits.effective
            new_regular_limit = self._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=baseline,
                topup_balance_bytes=new_topup_balance,
                regular_bonus_bytes=regular_bonus,
                regular_unlimited_override=regular_unlimited,
                traffic_used_bytes=traffic_used,
                hwid_device_bonus_bytes=await self._hwid_device_traffic_bonus_bytes_for_sub(
                    session, sub, active_devices=hwid_extra
                ),
            )

        premium_period_start = previous_values["premium_period_start_at"]
        premium_topup_used = previous_values["premium_topup_used_bytes"]
        premium_used = previous_values["premium_used_bytes"]
        premium_baseline = previous_values["premium_baseline_bytes"]
        premium_topup_balance = previous_values["premium_topup_balance_bytes"]
        premium_is_limited = previous_values["premium_is_limited"]
        if premium_bytes > 0:
            premium_period_start = self._premium_accounting_period_start(sub, now)
            same_period = self._same_premium_accounting_period(sub, premium_period_start, now)
            premium_topup_used = int(sub.premium_topup_used_bytes or 0) if same_period else 0
            premium_used = int(sub.premium_used_bytes or 0) if same_period else 0
            premium_baseline = int(
                (tariff.premium_monthly_bytes if tariff else 0) or sub.premium_baseline_bytes or 0
            )
            premium_bonus = max(0, int(getattr(sub, "premium_bonus_bytes", 0) or 0))
            premium_topup_balance = int(sub.premium_topup_balance_bytes or 0) + premium_bytes
            overflow_to_cover = max(
                0, premium_used - premium_baseline - premium_topup_used - premium_bonus
            )
            consume_now = min(premium_topup_balance, overflow_to_cover)
            premium_topup_balance -= consume_now
            premium_topup_used += consume_now
            premium_limit = self._premium_effective_limit_bytes(
                premium_baseline,
                premium_topup_balance,
                premium_topup_used,
                premium_bonus,
            )
            premium_is_limited = self._premium_access_should_be_limited(
                tariff,
                premium_limit_bytes=premium_limit,
                premium_used_bytes=premium_used,
                premium_unlimited_override=bool(getattr(sub, "premium_unlimited_override", False)),
            )
        update_data: dict[str, Any] = {
            "end_date": new_end_date,
            "last_notification_sent": None if days > 0 else sub.last_notification_sent,
        }
        if regular_bytes > 0:
            update_data.update(
                {
                    "topup_balance_bytes": new_topup_balance,
                    "traffic_limit_bytes": new_regular_limit,
                    "is_throttled": False,
                    "hwid_device_limit": hwid_base_limit,
                    "extra_hwid_devices": hwid_extra,
                }
            )
        if premium_bytes > 0:
            update_data.update(
                {
                    "premium_baseline_bytes": premium_baseline,
                    "premium_topup_balance_bytes": premium_topup_balance,
                    "premium_topup_used_bytes": premium_topup_used,
                    "premium_used_bytes": premium_used,
                    "premium_is_limited": premium_is_limited,
                    "premium_period_start_at": premium_period_start,
                }
            )
        updated_sub = await subscription_dal.update_subscription(
            session, sub.subscription_id, update_data
        )
        managed_squads = self._panel_squads_for_tariff(
            tariff,
            include_premium=not premium_is_limited,
        )
        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=new_end_date,
            status="ACTIVE",
            traffic_limit_bytes=new_regular_limit,
            hwid_device_limit=hwid_effective_limit,
            include_default_squads=False,
        )
        panel_payload.update(
            await self.build_effective_panel_squad_fields(
                session,
                user_id=user_id,
                panel_user_uuid=db_user.panel_user_uuid,
                managed_internal_squads=managed_squads,
                include_internal_squads=True,
                source="promo_grant",
            )
        )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        try:
            panel_result = await self.panel_service.update_user_details_on_panel(
                db_user.panel_user_uuid, panel_payload
            )
            confirmed = await self._confirmed_panel_entitlement(
                db_user.panel_user_uuid,
                panel_result,
                panel_payload,
                source="promo_grant",
            )
        except Exception:
            logger.exception("Failed to push promo grant for user %s", user_id)
            confirmed = None
        if confirmed is None:
            await subscription_dal.update_subscription(
                session, sub.subscription_id, previous_values
            )
            rollback_squads = self._panel_squads_for_tariff(
                tariff,
                include_premium=not previous_values["premium_is_limited"],
            )
            rollback_panel_payload = self._build_panel_update_payload(
                panel_user_uuid=db_user.panel_user_uuid,
                expire_at=previous_end_date,
                status="ACTIVE",
                traffic_limit_bytes=previous_values["traffic_limit_bytes"],
                hwid_device_limit=self._effective_hwid_limit(
                    previous_values["hwid_device_limit"],
                    previous_values["extra_hwid_devices"],
                ),
                include_default_squads=False,
            )
            rollback_panel_payload.update(
                await self.build_effective_panel_squad_fields(
                    session,
                    user_id=user_id,
                    panel_user_uuid=db_user.panel_user_uuid,
                    managed_internal_squads=rollback_squads,
                    include_internal_squads=True,
                    source="promo_grant_rollback",
                )
            )
            rollback_panel_payload.update(self._panel_identity_payload_for_user(db_user))
            try:
                await self.panel_service.update_user_details_on_panel(
                    db_user.panel_user_uuid, rollback_panel_payload
                )
            except Exception:
                logger.exception("Failed to compensate promo grant for user %s", user_id)
            return None

        if days > 0:
            try:
                await tariff_dal.extend_hwid_device_purchases_for_subscription_bonus(
                    session,
                    subscription_id=sub.subscription_id,
                    at=now,
                    subscription_end_before=previous_end_date,
                    delta=timedelta(days=days),
                )
            except Exception:
                logger.exception(
                    "Failed to extend HWID purchases for promo grant of user %s", user_id
                )
        if regular_bytes > 0:
            await record_traffic_topup_best_effort(
                session,
                subscription_id=sub.subscription_id,
                payment_id=None,
                purchased_bytes=regular_bytes,
                kind="promo_topup",
            )
        if premium_bytes > 0:
            await record_traffic_topup_best_effort(
                session,
                subscription_id=sub.subscription_id,
                payment_id=None,
                purchased_bytes=premium_bytes,
                kind="promo_premium_topup",
            )
        return {
            "subscription_id": updated_sub.subscription_id,
            "end_date": new_end_date,
            "topup_balance_bytes": new_topup_balance,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "granted_regular_bytes": regular_bytes,
            "granted_premium_bytes": premium_bytes,
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
        promo_code_id_from_payment: int | None = None,
    ) -> dict[str, Any] | None:
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
                promo_code_id_from_payment=promo_code_id_from_payment,
            )

        charged_gb = float(traffic_gb)
        granted_gb = charged_gb
        if promo_code_id_from_payment:
            payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            promo_model, promo_effects = await load_payment_promo_effects(
                session,
                payment or promo_code_id_from_payment,
            )
            if promo_model is not None and promo_effects is not None:
                grant = resolve_effective_grant(
                    GrantContext(
                        sale_mode_base="topup",
                        tariff_key=tariff.key,
                        base_period_days=0,
                        months=None,
                        charged_gb=charged_gb,
                        scope="regular",
                        promo=promo_effects,
                    )
                )
                quoted_granted_gb = charged_gb * grant.traffic_multiplier
                consumed = await consume_payment_promo(
                    session=session,
                    user_id=user_id,
                    promo_model=promo_model,
                    effects=promo_effects,
                    payment_id=payment_db_id,
                    payment=payment,
                    sale_mode_base="topup",
                    months=None,
                    traffic_gb=charged_gb,
                    granted_gb=quoted_granted_gb,
                )
                if consumed:
                    granted_gb = quoted_granted_gb

        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode="topup",
            tariff_key=tariff.key,
            purchased_gb=float(granted_gb),
        )
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            logger.error(
                "Traffic top-up activation has no panel identity"
                " (payment_id=%s user_id=%s tariff_key=%s granted_gb=%s).",
                payment_db_id,
                user_id,
                tariff.key,
                granted_gb,
            )
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            logger.error(
                "Traffic top-up activation found no active subscription"
                " (payment_id=%s user_id=%s panel_user_uuid=%s tariff_key=%s granted_gb=%s).",
                payment_db_id,
                user_id,
                db_user.panel_user_uuid,
                tariff.key,
                granted_gb,
            )
            return None

        purchase_bytes = self.gb_to_bytes(granted_gb)
        new_topup_balance = int(sub.topup_balance_bytes or 0) + purchase_bytes
        baseline = int(sub.tier_baseline_bytes or tariff.monthly_bytes)
        rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
        runl = bool(getattr(sub, "regular_unlimited_override", False))
        used_for_lim = int(getattr(sub, "traffic_used_bytes", 0) or 0)
        hwid_limits = await self._resolve_hwid_device_limits(session, sub, tariff)
        new_limit = self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline,
            topup_balance_bytes=new_topup_balance,
            regular_bonus_bytes=rb,
            regular_unlimited_override=runl,
            traffic_used_bytes=used_for_lim,
            hwid_device_bonus_bytes=await self._hwid_device_traffic_bonus_bytes_for_sub(
                session, sub, active_devices=hwid_limits.extra
            ),
        )
        base_hwid_limit = hwid_limits.base
        extra_hwid_devices = hwid_limits.extra
        effective_hwid_limit = hwid_limits.effective
        updated_sub = await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "topup_balance_bytes": new_topup_balance,
                "traffic_limit_bytes": new_limit,
                "is_throttled": False,
                "tariff_key": tariff.key,
                "hwid_device_limit": base_hwid_limit,
                "extra_hwid_devices": extra_hwid_devices,
            },
        )
        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=updated_sub.end_date,
            status="ACTIVE",
            traffic_limit_bytes=new_limit,
            hwid_device_limit=effective_hwid_limit,
            include_default_squads=False,
        )
        managed_squads = self._panel_squads_for_tariff(
            tariff,
            include_premium=not bool(getattr(updated_sub, "premium_is_limited", False)),
        )
        panel_payload.update(
            await self.build_effective_panel_squad_fields(
                session,
                user_id=user_id,
                panel_user_uuid=db_user.panel_user_uuid,
                managed_internal_squads=managed_squads,
                include_internal_squads=True,
                source="regular_topup",
            )
        )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        panel_update_result = await self.panel_service.update_user_details_on_panel(
            db_user.panel_user_uuid, panel_payload
        )
        confirmed_panel_user = await self._confirmed_panel_entitlement(
            db_user.panel_user_uuid,
            panel_update_result,
            panel_payload,
            source="regular_topup",
        )
        if confirmed_panel_user is None:
            logger.warning(
                "Panel user details update FAILED for traffic top-up user %s. Response: %s",
                user_id,
                panel_update_result,
            )
            return None
        await record_traffic_topup_best_effort(
            session,
            subscription_id=sub.subscription_id,
            payment_id=payment_db_id,
            purchased_bytes=purchase_bytes,
            kind="topup",
        )
        await self._send_payment_success_email(
            db_user=db_user,
            sale_mode="topup",
            months=0,
            traffic_gb=float(granted_gb),
            payment_amount=payment_amount,
            end_date=getattr(updated_sub, "end_date", None),
            provider=provider,
        )
        return {
            "subscription_id": sub.subscription_id,
            "traffic_limit_bytes": new_limit,
            "topup_balance_bytes": new_topup_balance,
            "traffic_gb": float(granted_gb),
            "tariff_key": tariff.key,
        }

    async def activate_premium_topup(
        self,
        session: AsyncSession,
        user_id: int,
        tariff_key: str,
        traffic_gb: float,
        payment_amount: float,
        payment_db_id: int,
        provider: str = "yookassa",
        promo_code_id_from_payment: int | None = None,
    ) -> dict[str, Any] | None:
        tariff = self._resolve_tariff(tariff_key)
        if not tariff or not tariff.premium_squad_uuids:
            logger.error(
                "Premium top-up requires a tariff with premium squads for user %s", user_id
            )
            return None

        charged_gb = float(traffic_gb)
        granted_gb = charged_gb
        if promo_code_id_from_payment:
            payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
            promo_model, promo_effects = await load_payment_promo_effects(
                session,
                payment or promo_code_id_from_payment,
            )
            if promo_model is not None and promo_effects is not None:
                grant = resolve_effective_grant(
                    GrantContext(
                        sale_mode_base="premium_topup",
                        tariff_key=tariff.key,
                        base_period_days=0,
                        months=None,
                        charged_gb=charged_gb,
                        scope="premium",
                        promo=promo_effects,
                    )
                )
                quoted_granted_gb = charged_gb * grant.traffic_multiplier
                consumed = await consume_payment_promo(
                    session=session,
                    user_id=user_id,
                    promo_model=promo_model,
                    effects=promo_effects,
                    payment_id=payment_db_id,
                    payment=payment,
                    sale_mode_base="premium_topup",
                    months=None,
                    traffic_gb=charged_gb,
                    granted_gb=quoted_granted_gb,
                )
                if consumed:
                    granted_gb = quoted_granted_gb

        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode="premium_topup",
            tariff_key=tariff.key,
            purchased_gb=float(granted_gb),
        )
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None

        purchase_bytes = self.gb_to_bytes(granted_gb)
        now = datetime.now(UTC)
        premium_period_start = self._premium_accounting_period_start(sub, now)
        same_period = self._same_premium_accounting_period(sub, premium_period_start, now)
        previous_topup_used = int(sub.premium_topup_used_bytes or 0) if same_period else 0
        premium_used = int(sub.premium_used_bytes or 0) if same_period else 0
        premium_baseline = int(tariff.premium_monthly_bytes or sub.premium_baseline_bytes or 0)
        premium_bonus = max(0, int(getattr(sub, "premium_bonus_bytes", 0) or 0))
        premium_topup_balance = int(sub.premium_topup_balance_bytes or 0) + purchase_bytes
        overflow_to_cover = max(
            0, premium_used - premium_baseline - previous_topup_used - premium_bonus
        )
        consume_now = min(premium_topup_balance, overflow_to_cover)
        premium_topup_balance -= consume_now
        premium_topup_used = previous_topup_used + consume_now
        premium_limit = self._premium_effective_limit_bytes(
            premium_baseline,
            premium_topup_balance,
            premium_topup_used,
            premium_bonus,
        )
        premium_unlimited_override = bool(getattr(sub, "premium_unlimited_override", False))
        premium_is_limited = self._premium_access_should_be_limited(
            tariff,
            premium_limit_bytes=premium_limit,
            premium_used_bytes=premium_used,
            premium_unlimited_override=premium_unlimited_override,
        )

        await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "premium_baseline_bytes": premium_baseline,
                "premium_topup_balance_bytes": premium_topup_balance,
                "premium_topup_used_bytes": premium_topup_used,
                "premium_used_bytes": premium_used,
                "premium_is_limited": premium_is_limited,
                "premium_period_start_at": premium_period_start,
                "tariff_key": tariff.key,
            },
        )
        desired_squads = self._panel_squads_for_tariff(
            tariff,
            include_premium=not premium_is_limited,
        )
        panel_updated = await self._sync_panel_squads_if_needed(
            db_user.panel_user_uuid,
            desired_squads,
            user_id=user_id,
            source="premium_topup",
            session=session,
        )
        if not panel_updated:
            logger.warning(
                "Panel user details update FAILED for premium top-up user %s.",
                user_id,
            )
            return None
        await record_traffic_topup_best_effort(
            session,
            subscription_id=sub.subscription_id,
            payment_id=payment_db_id,
            purchased_bytes=purchase_bytes,
            kind="premium_topup",
        )
        await self._send_payment_success_email(
            db_user=db_user,
            sale_mode="premium_topup",
            months=0,
            traffic_gb=float(granted_gb),
            payment_amount=payment_amount,
            end_date=getattr(sub, "end_date", None),
            provider=provider,
        )
        return {
            "subscription_id": sub.subscription_id,
            "premium_limit_bytes": premium_limit,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "premium_is_limited": premium_is_limited,
            "traffic_gb": float(granted_gb),
            "tariff_key": tariff.key,
        }

    async def admin_grant_topup(
        self,
        session: AsyncSession,
        user_id: int,
        traffic_gb: float,
    ) -> dict[str, Any] | None:
        """Credit regular traffic to a user as if they purchased a top-up."""
        try:
            gb_value = float(traffic_gb)
        except (TypeError, ValueError):
            logger.error("admin_grant_topup: invalid traffic_gb=%r", traffic_gb)
            return None
        if gb_value <= 0:
            return None

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None

        tariff = (
            (gift_tariff(sub) or self._resolve_tariff(sub.tariff_key)) if sub.tariff_key else None
        )
        purchase_bytes = self.gb_to_bytes(gb_value)
        baseline_bytes = int(
            sub.tier_baseline_bytes or (tariff.monthly_bytes if tariff else 0) or 0
        )
        new_topup_balance = int(sub.topup_balance_bytes or 0) + purchase_bytes
        rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
        runl = bool(getattr(sub, "regular_unlimited_override", False))
        used_for_lim = int(getattr(sub, "traffic_used_bytes", 0) or 0)
        hwid_limits = await self._resolve_hwid_device_limits(session, sub, tariff)
        new_limit = self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline_bytes,
            topup_balance_bytes=new_topup_balance,
            regular_bonus_bytes=rb,
            regular_unlimited_override=runl,
            traffic_used_bytes=used_for_lim,
            hwid_device_bonus_bytes=await self._hwid_device_traffic_bonus_bytes_for_sub(
                session, sub, active_devices=hwid_limits.extra
            ),
        )
        base_hwid_limit = hwid_limits.base
        extra_hwid_devices = hwid_limits.extra
        effective_hwid_limit = hwid_limits.effective
        updated_sub = await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "topup_balance_bytes": new_topup_balance,
                "traffic_limit_bytes": new_limit,
                "is_throttled": False,
                "hwid_device_limit": base_hwid_limit,
                "extra_hwid_devices": extra_hwid_devices,
            },
        )
        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=updated_sub.end_date,
            status="ACTIVE",
            traffic_limit_bytes=new_limit,
            hwid_device_limit=effective_hwid_limit,
            include_default_squads=False,
        )
        if tariff is not None:
            managed_squads = self._panel_squads_for_tariff(
                tariff,
                include_premium=not bool(getattr(updated_sub, "premium_is_limited", False)),
            )
            panel_payload.update(
                await self.build_effective_panel_squad_fields(
                    session,
                    user_id=user_id,
                    panel_user_uuid=db_user.panel_user_uuid,
                    managed_internal_squads=managed_squads,
                    include_internal_squads=True,
                    source="admin_regular_topup",
                )
            )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        try:
            updated_panel = await self.panel_service.update_user_details_on_panel(
                db_user.panel_user_uuid, panel_payload
            )
        except Exception:
            logger.exception("admin_grant_topup: failed to push panel update for user %s", user_id)
            return None
        confirmed_panel_user = await self._confirmed_panel_entitlement(
            db_user.panel_user_uuid,
            updated_panel,
            panel_payload,
            source="admin_regular_topup",
        )
        if confirmed_panel_user is None:
            logger.warning(
                "admin_grant_topup: panel verification failed for user %s. Response: %s",
                user_id,
                updated_panel,
            )
            return None
        await record_traffic_topup_best_effort(
            session,
            subscription_id=sub.subscription_id,
            payment_id=None,
            purchased_bytes=purchase_bytes,
            kind="admin_topup",
        )
        return {
            "subscription_id": sub.subscription_id,
            "traffic_limit_bytes": new_limit,
            "topup_balance_bytes": new_topup_balance,
            "granted_bytes": purchase_bytes,
        }

    async def admin_grant_premium_topup(
        self,
        session: AsyncSession,
        user_id: int,
        traffic_gb: float,
    ) -> dict[str, Any] | None:
        """Credit premium-squad traffic to a user as if they purchased a premium top-up."""
        try:
            gb_value = float(traffic_gb)
        except (TypeError, ValueError):
            logger.error("admin_grant_premium_topup: invalid traffic_gb=%r", traffic_gb)
            return None
        if gb_value <= 0:
            return None

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None
        tariff = (
            (gift_tariff(sub) or self._resolve_tariff(sub.tariff_key)) if sub.tariff_key else None
        )
        if not tariff or not tariff.premium_squad_uuids:
            logger.error(
                "admin_grant_premium_topup: tariff %s has no premium squads (user %s)",
                getattr(tariff, "key", None),
                user_id,
            )
            return None

        purchase_bytes = self.gb_to_bytes(gb_value)
        now = datetime.now(UTC)
        premium_period_start = self._premium_accounting_period_start(sub, now)
        same_period = self._same_premium_accounting_period(sub, premium_period_start, now)
        previous_topup_used = int(sub.premium_topup_used_bytes or 0) if same_period else 0
        premium_used = int(sub.premium_used_bytes or 0) if same_period else 0
        premium_baseline = int(tariff.premium_monthly_bytes or sub.premium_baseline_bytes or 0)
        premium_bonus = max(0, int(getattr(sub, "premium_bonus_bytes", 0) or 0))
        premium_topup_balance = int(sub.premium_topup_balance_bytes or 0) + purchase_bytes
        overflow_to_cover = max(
            0, premium_used - premium_baseline - previous_topup_used - premium_bonus
        )
        consume_now = min(premium_topup_balance, overflow_to_cover)
        premium_topup_balance -= consume_now
        premium_topup_used = previous_topup_used + consume_now
        premium_limit = self._premium_effective_limit_bytes(
            premium_baseline,
            premium_topup_balance,
            premium_topup_used,
            premium_bonus,
        )
        premium_unlimited_override = bool(getattr(sub, "premium_unlimited_override", False))
        premium_is_limited = self._premium_access_should_be_limited(
            tariff,
            premium_limit_bytes=premium_limit,
            premium_used_bytes=premium_used,
            premium_unlimited_override=premium_unlimited_override,
        )

        await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "premium_baseline_bytes": premium_baseline,
                "premium_topup_balance_bytes": premium_topup_balance,
                "premium_topup_used_bytes": premium_topup_used,
                "premium_used_bytes": premium_used,
                "premium_is_limited": premium_is_limited,
                "premium_period_start_at": premium_period_start,
            },
        )
        desired_squads = self._panel_squads_for_tariff(
            tariff,
            include_premium=not premium_is_limited,
        )
        try:
            panel_updated = await self._sync_panel_squads_if_needed(
                db_user.panel_user_uuid,
                desired_squads,
                user_id=user_id,
                source="admin_premium_topup",
                session=session,
            )
            if not panel_updated:
                logger.warning(
                    "admin_grant_premium_topup: panel update failed for user %s",
                    user_id,
                )
                return None
        except Exception:
            logger.exception(
                "admin_grant_premium_topup: failed to push panel update for user %s",
                user_id,
            )
            return None
        await record_traffic_topup_best_effort(
            session,
            subscription_id=sub.subscription_id,
            payment_id=None,
            purchased_bytes=purchase_bytes,
            kind="admin_premium_topup",
        )
        return {
            "subscription_id": sub.subscription_id,
            "premium_limit_bytes": premium_limit,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "premium_is_limited": premium_is_limited,
            "granted_bytes": purchase_bytes,
        }
