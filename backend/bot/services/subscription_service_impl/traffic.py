import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.grants import GrantContext, resolve_effective_grant
from bot.services.payment_promo import consume_payment_promo, load_payment_promo_effects
from config.tariffs_config import Tariff
from db.dal import payment_dal, subscription_dal, tariff_dal, user_dal
from db.models import Subscription

from ._typing import SubscriptionServiceMixinContract
from .hwid_limits import HwidDeviceLimits


class TrafficMixin(SubscriptionServiceMixinContract):
    async def _resolve_hwid_device_limits(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff: Tariff | None,
    ) -> HwidDeviceLimits:
        base = (
            int(sub.hwid_device_limit)
            if sub.hwid_device_limit is not None
            else self._base_hwid_limit_for_tariff(tariff)
        )
        extra = await self._active_hwid_extra_devices_for_sub(session, sub)
        effective = self._effective_hwid_limit(base, extra)
        return HwidDeviceLimits(base=base, extra=extra, effective=effective)

    async def _activate_traffic_package(
        self,
        session: AsyncSession,
        user_id: int,
        traffic_gb: float,
        payment_amount: float,
        payment_db_id: int,
        provider: str = "yookassa",
        tariff_key: str | None = None,
        sale_mode: str = "traffic",
        promo_code_id_from_payment: int | None = None,
    ) -> dict[str, Any] | None:
        """Activate or extend a traffic-based package instead of a time-based subscription."""
        tariff = self._resolve_tariff(tariff_key, "traffic") if self._tariffs_config() else None
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
                        sale_mode_base=sale_mode,
                        tariff_key=tariff.key if tariff else tariff_key,
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
                    sale_mode_base=sale_mode,
                    months=None,
                    traffic_gb=charged_gb,
                    granted_gb=quoted_granted_gb,
                )
                if consumed:
                    granted_gb = quoted_granted_gb

        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode=sale_mode,
            tariff_key=tariff.key if tariff else tariff_key,
            purchased_gb=float(granted_gb),
        )
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error("User %s not found for traffic package activation", user_id)
            return None

        (
            panel_user_uuid,
            panel_sub_link_id,
            panel_short_uuid,
            _,
        ) = await self._get_or_create_panel_user_link_details(session, user_id, db_user)

        if not panel_user_uuid or not panel_sub_link_id:
            logging.error(
                "Failed to ensure panel linkage for user %s during traffic activation", user_id
            )
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

        purchase_bytes = self.gb_to_bytes(granted_gb)
        extra_hwid_devices = (
            await self._active_hwid_extra_devices_for_sub(session, active_sub) if active_sub else 0
        )
        base_hwid_limit = self._base_hwid_limit_for_tariff(tariff)
        effective_hwid_limit = self._effective_hwid_limit(base_hwid_limit, extra_hwid_devices)
        remaining_bytes = max(0, int(current_limit or 0) - int(current_used or 0))
        new_balance = remaining_bytes + purchase_bytes
        new_limit = int(current_used or 0) + new_balance

        start_date = datetime.now(UTC)
        # Set a far-future expiry to satisfy panel requirements; keep the latest known expiry if it's further.  # noqa: E501
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
            "premium_baseline_bytes": self._premium_limit_for_tariff(tariff, 0),
            "premium_topup_balance_bytes": 0,
            "premium_topup_used_bytes": 0,
            "premium_used_bytes": 0,
            "premium_is_limited": False,
            "premium_period_start_at": None,
            "period_start_at": None,
            "is_throttled": False,
            "effective_monthly_price_rub": None,
            "hwid_device_limit": base_hwid_limit,
            "extra_hwid_devices": extra_hwid_devices,
        }

        try:
            new_or_updated_sub = await subscription_dal.upsert_subscription(session, sub_payload)
        except Exception as exc:
            logging.error(
                "Failed to upsert traffic subscription for user %s: %s", user_id, exc, exc_info=True
            )
            return None

        panel_update_payload = self._build_panel_update_payload(
            panel_user_uuid=panel_user_uuid,
            expire_at=final_end_date,
            status="ACTIVE",
            traffic_limit_bytes=new_limit,
            traffic_limit_strategy="NO_RESET",
            hwid_device_limit=effective_hwid_limit,
        )
        if tariff:
            panel_update_payload["activeInternalSquads"] = self._panel_squads_for_tariff(tariff)

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
            traffic_gb=float(granted_gb),
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
            "traffic_gb": float(granted_gb),
            "traffic_limit_bytes": new_limit,
            "tariff_key": tariff.key if tariff else None,
        }

    async def sync_premium_squad_access_to_panel(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> None:
        """Recompute premium quota flags from DB and push internal squads to Remnawave.

        Used when admin overrides change without going through the traffic worker
        (Telegram/Web admin premium bonus / unlimited).
        """
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return
        tariff = self._resolve_tariff(sub.tariff_key) if sub.tariff_key else None
        if not tariff or not getattr(tariff, "premium_squad_uuids", None):
            return

        premium_baseline = int(tariff.premium_monthly_bytes or sub.premium_baseline_bytes or 0)
        premium_bonus = max(0, int(getattr(sub, "premium_bonus_bytes", 0) or 0))
        premium_topup_balance = int(sub.premium_topup_balance_bytes or 0)
        premium_topup_used = int(getattr(sub, "premium_topup_used_bytes", 0) or 0)
        premium_used = int(sub.premium_used_bytes or 0)
        premium_limit = self._premium_effective_limit_bytes(
            premium_baseline,
            premium_topup_balance,
            premium_topup_used,
            premium_bonus,
        )
        premium_unlimited = bool(getattr(sub, "premium_unlimited_override", False))
        premium_is_limited = (
            not premium_unlimited and premium_limit > 0 and premium_used >= premium_limit
        )

        if bool(getattr(sub, "premium_is_limited", False)) != premium_is_limited:
            await subscription_dal.update_subscription(
                session,
                sub.subscription_id,
                {"premium_is_limited": premium_is_limited},
            )

        squads = self._panel_squads_for_tariff(tariff, include_premium=not premium_is_limited)
        try:
            panel_updated = await self._sync_panel_squads_if_needed(
                db_user.panel_user_uuid,
                squads,
                user_id=user_id,
                source="admin_premium_override",
            )
            if not panel_updated:
                logging.warning(
                    "sync_premium_squad_access_to_panel: panel update failed for user %s",
                    user_id,
                )
        except Exception:
            logging.exception(
                "sync_premium_squad_access_to_panel: failed to push squads for user %s", user_id
            )

    async def sync_main_traffic_limit_to_panel(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> None:
        """Recompute main traffic limit from tier + topups + regular_bonus_bytes and push to panel."""  # noqa: E501
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return
        tariff = self._resolve_tariff(sub.tariff_key) if sub.tariff_key else None
        baseline = int(sub.tier_baseline_bytes or (tariff.monthly_bytes if tariff else 0) or 0)
        rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
        runl = bool(getattr(sub, "regular_unlimited_override", False))
        used_now = int(getattr(sub, "traffic_used_bytes", 0) or 0)
        new_limit = self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline,
            topup_balance_bytes=int(sub.topup_balance_bytes or 0),
            regular_bonus_bytes=rb,
            regular_unlimited_override=runl,
            traffic_used_bytes=used_now,
        )
        sub.traffic_limit_bytes = new_limit
        if runl:
            sub.is_throttled = False
        hwid_limits = await self._resolve_hwid_device_limits(session, sub, tariff)
        extra_hwid_devices = hwid_limits.extra
        sub.extra_hwid_devices = extra_hwid_devices
        effective_hwid_limit = hwid_limits.effective
        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=sub.end_date,
            status="ACTIVE",
            traffic_limit_bytes=new_limit,
            hwid_device_limit=effective_hwid_limit,
        )
        if tariff is not None:
            panel_payload["activeInternalSquads"] = self._panel_squads_for_tariff(
                tariff,
                include_premium=not bool(getattr(sub, "premium_is_limited", False)),
            )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        try:
            await self.panel_service.update_user_details_on_panel(
                db_user.panel_user_uuid, panel_payload
            )
        except Exception:
            logging.exception("sync_main_traffic_limit_to_panel failed for user %s", user_id)
