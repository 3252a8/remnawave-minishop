import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.grants import GrantContext, resolve_effective_grant
from bot.services.payment_promo import consume_payment_promo, load_payment_promo_effects
from db.dal import payment_dal, subscription_dal, tariff_dal, user_dal

from ._typing import SubscriptionServiceMixinContract


class TopupMixin(SubscriptionServiceMixinContract):
    async def activate_topup(
        self,
        session: AsyncSession,
        user_id: int,
        tariff_key: str,
        traffic_gb: float,
        payment_amount: float,
        payment_db_id: int,
        provider: str = "yookassa",
        promo_code_id_from_payment: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
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
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None

        purchase_bytes = self.gb_to_bytes(granted_gb)
        new_topup_balance = int(sub.topup_balance_bytes or 0) + purchase_bytes
        baseline = int(sub.tier_baseline_bytes or tariff.monthly_bytes)
        rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
        runl = bool(getattr(sub, "regular_unlimited_override", False))
        used_for_lim = int(getattr(sub, "traffic_used_bytes", 0) or 0)
        new_limit = self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline,
            topup_balance_bytes=new_topup_balance,
            regular_bonus_bytes=rb,
            regular_unlimited_override=runl,
            traffic_used_bytes=used_for_lim,
        )
        hwid_limits = await self._resolve_hwid_device_limits(session, sub, tariff)
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
        )
        panel_payload["activeInternalSquads"] = self._panel_squads_for_tariff(
            tariff,
            include_premium=not bool(getattr(updated_sub, "premium_is_limited", False)),
        )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        updated_panel = await self.panel_service.update_user_details_on_panel(
            db_user.panel_user_uuid, panel_payload
        )
        if not updated_panel or updated_panel.get("error"):
            logging.warning(
                "Panel user details update FAILED for traffic top-up user %s. Response: %s",
                user_id,
                updated_panel,
            )
            return None
        await tariff_dal.create_traffic_topup(
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
        promo_code_id_from_payment: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        tariff = self._resolve_tariff(tariff_key)
        if not tariff or not tariff.premium_squad_uuids:
            logging.error(
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
        now = datetime.now(timezone.utc)
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
        premium_unlimited = bool(getattr(sub, "premium_unlimited_override", False))
        premium_is_limited = (
            not premium_unlimited and premium_limit > 0 and premium_used >= premium_limit
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
        )
        if not panel_updated:
            logging.warning(
                "Panel user details update FAILED for premium top-up user %s.",
                user_id,
            )
            return None
        await tariff_dal.create_traffic_topup(
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
    ) -> Optional[Dict[str, Any]]:
        """Credit regular traffic to a user as if they purchased a top-up."""
        try:
            gb_value = float(traffic_gb)
        except (TypeError, ValueError):
            logging.error("admin_grant_topup: invalid traffic_gb=%r", traffic_gb)
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

        tariff = self._resolve_tariff(sub.tariff_key) if sub.tariff_key else None
        purchase_bytes = self.gb_to_bytes(gb_value)
        baseline_bytes = int(
            sub.tier_baseline_bytes or (tariff.monthly_bytes if tariff else 0) or 0
        )
        new_topup_balance = int(sub.topup_balance_bytes or 0) + purchase_bytes
        rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
        runl = bool(getattr(sub, "regular_unlimited_override", False))
        used_for_lim = int(getattr(sub, "traffic_used_bytes", 0) or 0)
        new_limit = self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline_bytes,
            topup_balance_bytes=new_topup_balance,
            regular_bonus_bytes=rb,
            regular_unlimited_override=runl,
            traffic_used_bytes=used_for_lim,
        )
        hwid_limits = await self._resolve_hwid_device_limits(session, sub, tariff)
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
        )
        if tariff is not None:
            panel_payload["activeInternalSquads"] = self._panel_squads_for_tariff(
                tariff,
                include_premium=not bool(getattr(updated_sub, "premium_is_limited", False)),
            )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        try:
            await self.panel_service.update_user_details_on_panel(
                db_user.panel_user_uuid, panel_payload
            )
        except Exception:
            logging.exception("admin_grant_topup: failed to push panel update for user %s", user_id)
        await tariff_dal.create_traffic_topup(
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
    ) -> Optional[Dict[str, Any]]:
        """Credit premium-squad traffic to a user as if they purchased a premium top-up."""
        try:
            gb_value = float(traffic_gb)
        except (TypeError, ValueError):
            logging.error("admin_grant_premium_topup: invalid traffic_gb=%r", traffic_gb)
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
        tariff = self._resolve_tariff(sub.tariff_key) if sub.tariff_key else None
        if not tariff or not tariff.premium_squad_uuids:
            logging.error(
                "admin_grant_premium_topup: tariff %s has no premium squads (user %s)",
                getattr(tariff, "key", None),
                user_id,
            )
            return None

        purchase_bytes = self.gb_to_bytes(gb_value)
        now = datetime.now(timezone.utc)
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
        premium_unlimited = bool(getattr(sub, "premium_unlimited_override", False))
        premium_is_limited = (
            not premium_unlimited and premium_limit > 0 and premium_used >= premium_limit
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
            )
            if not panel_updated:
                logging.warning(
                    "admin_grant_premium_topup: panel update failed for user %s",
                    user_id,
                )
        except Exception:
            logging.exception(
                "admin_grant_premium_topup: failed to push panel update for user %s",
                user_id,
            )
        await tariff_dal.create_traffic_topup(
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

    async def _sync_panel_squads_if_needed(
        self,
        panel_user_uuid: str,
        desired_squads: List[str],
        *,
        user_id: int,
        source: str,
    ) -> bool:
        match, current_set = await self._panel_squads_match(panel_user_uuid, desired_squads)
        if match is True:
            return True

        desired_set = self._panel_squad_uuid_set(desired_squads)
        self._log_panel_squad_patch(
            source=source,
            user_id=user_id,
            panel_uuid=panel_user_uuid,
            current_set=current_set,
            desired_set=desired_set,
        )
        updated_panel = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid,
            {"uuid": panel_user_uuid, "activeInternalSquads": desired_squads},
            log_response=False,
        )
        if not updated_panel:
            return False
        return not (isinstance(updated_panel, dict) and updated_panel.get("error"))

    async def _panel_squads_match(
        self,
        panel_user_uuid: str,
        desired_squads: List[str],
    ) -> tuple[Optional[bool], Optional[set[str]]]:
        try:
            panel_user = await self.panel_service.get_user_by_uuid(
                panel_user_uuid,
                log_response=False,
            )
        except Exception:
            logging.exception(
                "Failed to fetch panel user %s before premium squad update",
                panel_user_uuid,
            )
            return None, None
        current_known, current_set = self._panel_active_squad_uuid_set(panel_user)
        if not current_known:
            return None, current_set
        return current_set == self._panel_squad_uuid_set(desired_squads), current_set

    @classmethod
    def _panel_active_squad_uuid_set(
        cls,
        panel_user: Optional[dict],
    ) -> tuple[bool, set[str]]:
        if not isinstance(panel_user, dict):
            return False, set()
        for key in (
            "activeInternalSquads",
            "active_internal_squads",
            "activeInternalSquadUuids",
            "active_internal_squad_uuids",
        ):
            if key in panel_user:
                return True, cls._panel_squad_uuid_set(panel_user.get(key))
        return False, set()

    @staticmethod
    def _panel_squad_uuid_set(raw: object) -> set[str]:
        if not isinstance(raw, (list, tuple, set)):
            return set()
        out: set[str] = set()
        for item in raw:
            if isinstance(item, dict):
                nested_squad = item.get("internalSquad") or item.get("squad")
                if not isinstance(nested_squad, dict):
                    nested_squad = {}
                squad_uuid = (
                    item.get("uuid")
                    or item.get("internalSquadUuid")
                    or item.get("squadUuid")
                    or nested_squad.get("uuid")
                )
                if squad_uuid:
                    out.add(str(squad_uuid))
            elif item:
                out.add(str(item))
        return out

    def _log_panel_squad_patch(
        self,
        *,
        source: str,
        user_id: int,
        panel_uuid: str,
        current_set: Optional[set[str]],
        desired_set: set[str],
    ) -> None:
        logging.info(
            "Sync panel PATCH: source=%s user_id=%s telegram_id=%s panel_uuid=%s "
            "panel_view=full_fetch reasons=activeInternalSquads_mismatch "
            "fields=activeInternalSquads payload_fields=activeInternalSquads changes=%s",
            source,
            user_id,
            user_id,
            panel_uuid,
            "activeInternalSquads:%s->%s"
            % (
                self._format_panel_squad_set(current_set),
                self._format_panel_squad_set(desired_set),
            ),
        )

    @staticmethod
    def _format_panel_squad_set(value: Optional[set[str]]) -> str:
        if value is None:
            return "missing"
        values = sorted(str(item) for item in value)
        preview = ",".join(values[:4])
        suffix = ",..." if len(values) > 4 else ""
        text = f"[{len(values)}:{preview}{suffix}]"
        if len(text) > 96:
            return f"{text[:93]}..."
        return text
