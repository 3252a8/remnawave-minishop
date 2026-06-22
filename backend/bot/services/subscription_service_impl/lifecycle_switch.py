from ._runtime import (
    Any,
    AsyncSession,
    Dict,
    Optional,
    Subscription,
    SubscriptionServiceMixinContract,
    User,
    datetime,
    default_currency_key_for_settings,
    logging,
    prepare_config_links,
    subscription_dal,
    tariff_dal,
    timedelta,
    timezone,
    user_dal,
)


class SubscriptionLifecycleSwitchMixin(SubscriptionServiceMixinContract):
    async def _local_active_subscription_details_fallback(
        self,
        db_user: User,
        local_active_sub: Subscription,
    ) -> Dict[str, Any]:
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
            "traffic_limit_strategy": "",
            "tariff_key": local_active_sub.tariff_key,
            "tariff_name": tariff.name(language) if tariff else None,
            "tariff_description": tariff.description(language) if tariff else None,
            "premium_title": tariff.premium_name(language) if tariff else None,
            "billing_model": tariff.billing_model
            if tariff
            else ("traffic" if getattr(self.settings, "traffic_sale_mode", False) else "period"),
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
            "premium_unlimited_override": bool(
                getattr(local_active_sub, "premium_unlimited_override", False)
            ),
            "premium_limit_bytes": self._premium_effective_limit_bytes(
                premium_baseline,
                premium_topup_balance,
                premium_topup_used,
                premium_bonus_bytes,
            ),
            "premium_is_limited": bool(local_active_sub.premium_is_limited),
            "premium_period_start_at": getattr(local_active_sub, "premium_period_start_at", None),
            "premium_squad_labels": premium_access.get("squad_labels") or [],
            "premium_node_labels": premium_access.get("node_labels") or [],
            "period_start_at": local_active_sub.period_start_at,
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
        payment_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
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
        now = datetime.now(timezone.utc)
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
        update_data: Dict[str, Any] = {
            "tariff_key": target.key,
            "is_throttled": False,
            "premium_baseline_bytes": premium_baseline,
            "premium_topup_balance_bytes": premium_topup_balance,
            "premium_topup_used_bytes": premium_topup_used,
            "premium_is_limited": bool(premium_limit > 0 and premium_used >= premium_limit),
        }
        converted_bytes = None
        base_hwid_limit = self._base_hwid_limit_for_tariff(target)
        try:
            extra_hwid_devices = await tariff_dal.sum_active_hwid_devices(
                session,
                subscription_id=sub.subscription_id,
                at=now,
            )
        except Exception:
            logging.exception(
                "Failed to recalculate HWID devices during tariff switch for user %s",
                user_id,
            )
            extra_hwid_devices = int(sub.extra_hwid_devices or 0)
        update_data["hwid_device_limit"] = base_hwid_limit
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
            traffic_limit_strategy="NO_RESET" if target.billing_model == "traffic" else "MONTH",
            hwid_device_limit=self._effective_hwid_limit(base_hwid_limit, extra_hwid_devices),
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
            logging.warning(
                "Panel user details update FAILED for tariff switch user %s -> %s. Response: %s",
                user_id,
                target.key,
                updated_panel,
            )
            return None
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
