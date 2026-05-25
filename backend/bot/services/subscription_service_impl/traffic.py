# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


class TrafficMixin:
    async def _activate_traffic_package(
        self,
        session: AsyncSession,
        user_id: int,
        traffic_gb: float,
        payment_amount: float,
        payment_db_id: int,
        provider: str = "yookassa",
        tariff_key: Optional[str] = None,
        sale_mode: str = "traffic",
    ) -> Optional[Dict[str, Any]]:
        """Activate or extend a traffic-based package instead of a time-based subscription."""
        tariff = self._resolve_tariff(tariff_key, "traffic") if self._tariffs_config() else None
        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode=sale_mode,
            tariff_key=tariff.key if tariff else tariff_key,
            purchased_gb=float(traffic_gb),
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

        purchase_bytes = self.gb_to_bytes(traffic_gb)
        extra_hwid_devices = int(getattr(active_sub, "extra_hwid_devices", 0) or 0)
        base_hwid_limit = self._base_hwid_limit_for_tariff(tariff)
        effective_hwid_limit = self._effective_hwid_limit(base_hwid_limit, extra_hwid_devices)
        remaining_bytes = max(0, int(current_limit or 0) - int(current_used or 0))
        new_balance = remaining_bytes + purchase_bytes
        new_limit = int(current_used or 0) + new_balance

        start_date = datetime.now(timezone.utc)
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
            traffic_gb=float(traffic_gb),
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
            "traffic_limit_bytes": new_limit,
            "tariff_key": tariff.key if tariff else None,
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
            )

        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode="topup",
            tariff_key=tariff.key,
            purchased_gb=float(traffic_gb),
        )
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None

        purchase_bytes = self.gb_to_bytes(traffic_gb)
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
        base_hwid_limit = (
            int(sub.hwid_device_limit)
            if sub.hwid_device_limit is not None
            else self._base_hwid_limit_for_tariff(tariff)
        )
        effective_hwid_limit = self._effective_hwid_limit(
            base_hwid_limit,
            int(sub.extra_hwid_devices or 0),
        )
        updated_sub = await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "topup_balance_bytes": new_topup_balance,
                "traffic_limit_bytes": new_limit,
                "is_throttled": False,
                "tariff_key": tariff.key,
                "hwid_device_limit": base_hwid_limit,
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
            # Otherwise the user pays for top-up bytes that are recorded locally
            # but never reach Remnawave — they cannot actually use the traffic.
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
        return {
            "subscription_id": sub.subscription_id,
            "traffic_limit_bytes": new_limit,
            "topup_balance_bytes": new_topup_balance,
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
    ) -> Optional[Dict[str, Any]]:
        tariff = self._resolve_tariff(tariff_key)
        if not tariff or not tariff.premium_squad_uuids:
            logging.error(
                "Premium top-up requires a tariff with premium squads for user %s", user_id
            )
            return None

        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode="premium_topup",
            tariff_key=tariff.key,
            purchased_gb=float(traffic_gb),
        )
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None

        purchase_bytes = self.gb_to_bytes(traffic_gb)
        now = datetime.now(timezone.utc)
        premium_period_start = month_start(now)
        current_period_start = getattr(sub, "premium_period_start_at", None)
        same_period = bool(current_period_start and current_period_start == premium_period_start)
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
            # Otherwise the user pays for premium top-up but the panel never
            # re-grants premium squad access (the most common case here is
            # transitioning from premium_is_limited=True back to False).
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
        return {
            "subscription_id": sub.subscription_id,
            "premium_limit_bytes": premium_limit,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "premium_is_limited": premium_is_limited,
            "tariff_key": tariff.key,
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

    async def admin_grant_topup(
        self,
        session: AsyncSession,
        user_id: int,
        traffic_gb: float,
    ) -> Optional[Dict[str, Any]]:
        """Credit regular traffic to a user as if they purchased a top-up.

        Mirrors :meth:`activate_topup` but skips payment context and tariff
        resolution: the grant simply increases ``topup_balance_bytes`` and
        recomputes ``traffic_limit_bytes`` from the subscription's current
        tier baseline. The audit row in ``traffic_topups`` is stored with
        ``kind="admin_topup"`` and ``payment_id=NULL`` so reports stay clean.
        """
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
        base_hwid_limit = (
            int(sub.hwid_device_limit)
            if sub.hwid_device_limit is not None
            else self._base_hwid_limit_for_tariff(tariff)
        )
        effective_hwid_limit = self._effective_hwid_limit(
            base_hwid_limit,
            int(sub.extra_hwid_devices or 0),
        )
        updated_sub = await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "topup_balance_bytes": new_topup_balance,
                "traffic_limit_bytes": new_limit,
                "is_throttled": False,
                "hwid_device_limit": base_hwid_limit,
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
        base_hwid_limit = (
            int(sub.hwid_device_limit)
            if sub.hwid_device_limit is not None
            else self._base_hwid_limit_for_tariff(tariff)
        )
        effective_hwid_limit = self._effective_hwid_limit(
            base_hwid_limit,
            int(sub.extra_hwid_devices or 0),
        )
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

    async def admin_grant_premium_topup(
        self,
        session: AsyncSession,
        user_id: int,
        traffic_gb: float,
    ) -> Optional[Dict[str, Any]]:
        """Credit premium-squad traffic to a user as if they purchased a premium top-up.

        Mirrors :meth:`activate_premium_topup` but skips payment context.
        Requires the user's current tariff to expose premium squads. The
        balance is absorbed into ``premium_topup_balance_bytes`` (backfilling
        any current overuse first), ``premium_is_limited`` is recomputed and,
        if access becomes available again, the premium squads are returned to
        the user on the panel. The audit row in ``traffic_topups`` is stored
        with ``kind="admin_premium_topup"`` and ``payment_id=NULL``.
        """
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
        premium_period_start = month_start(now)
        current_period_start = getattr(sub, "premium_period_start_at", None)
        same_period = bool(current_period_start and current_period_start == premium_period_start)
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
    def _panel_squad_uuid_set(raw) -> set[str]:
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
