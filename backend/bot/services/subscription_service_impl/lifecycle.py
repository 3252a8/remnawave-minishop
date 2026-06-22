from ._runtime import (
    Any,
    AsyncSession,
    Dict,
    List,
    Optional,
    Subscription,
    Tuple,
    User,
    add_months,
    datetime,
    default_currency_key_for_settings,
    logging,
    payment_dal,
    prepare_config_links,
    promo_code_dal,
    subscription_dal,
    tariff_dal,
    timedelta,
    timezone,
    user_billing_dal,
    user_dal,
)


class SubscriptionLifecycleMixin:
    async def _lookup_panel_user_for_subscription_details(
        self,
        panel_user_uuid: str,
    ) -> Tuple[Optional[Dict[str, Any]], bool, str]:
        lookup_method = getattr(self.panel_service, "get_user_by_uuid_lookup", None)
        if callable(lookup_method):
            try:
                lookup = await lookup_method(panel_user_uuid, log_response=False)
            except TypeError:
                try:
                    lookup = await lookup_method(panel_user_uuid)
                except Exception as exc:
                    logging.exception(
                        "Failed to fetch panel user %s for subscription details",
                        panel_user_uuid,
                    )
                    return None, False, self._panel_lookup_exception_reason(exc)
            except Exception as exc:
                logging.exception(
                    "Failed to fetch panel user %s for subscription details",
                    panel_user_uuid,
                )
                return None, False, self._panel_lookup_exception_reason(exc)

            if isinstance(lookup, dict) and ("ok" in lookup or "not_found" in lookup):
                user = lookup.get("user")
                if lookup.get("ok") and isinstance(user, dict):
                    return user, False, ""
                reason = str(lookup.get("failure_reason") or "classification=panel_lookup_failed")
                return None, bool(lookup.get("not_found")), reason

        try:
            panel_user = await self.panel_service.get_user_by_uuid(panel_user_uuid)
        except Exception as exc:
            logging.exception(
                "Failed to fetch panel user %s for subscription details",
                panel_user_uuid,
            )
            return None, False, self._panel_lookup_exception_reason(exc)
        return (panel_user if isinstance(panel_user, dict) else None), False, ""

    @staticmethod
    def _panel_lookup_exception_reason(exc: Exception) -> str:
        message = str(exc).replace("\n", " ").strip()
        if len(message) > 300:
            message = f"{message[:300]}..."
        reason = f"classification=panel_lookup_failed exception={type(exc).__name__}"
        if message:
            reason = f"{reason} message={message}"
        return reason

    @staticmethod
    def _display_datetime_text(value: Optional[Any]) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return normalized.strftime("%d.%m.%Y %H:%M")
        return str(value)

    @staticmethod
    def _panel_expiry_matches(raw_expire_at: Optional[Any], expected_expire_at: datetime) -> bool:
        if not raw_expire_at:
            return False
        try:
            panel_expire_at = datetime.fromisoformat(str(raw_expire_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            logging.warning(
                "Panel update returned unparsable expireAt=%r for expected expiry %s.",
                raw_expire_at,
                expected_expire_at.isoformat(),
            )
            return False
        expected = (
            expected_expire_at
            if expected_expire_at.tzinfo
            else expected_expire_at.replace(tzinfo=timezone.utc)
        )
        actual = (
            panel_expire_at
            if panel_expire_at.tzinfo
            else panel_expire_at.replace(tzinfo=timezone.utc)
        )
        return abs((actual - expected).total_seconds()) <= 1

    async def _panel_update_confirms_expiry(
        self,
        panel_user_uuid: str,
        panel_update_result: Optional[Dict[str, Any]],
        expected_expire_at: datetime,
    ) -> bool:
        if not panel_update_result:
            return False
        if isinstance(panel_update_result, dict):
            if panel_update_result.get("error"):
                return False
            raw_expire_at = panel_update_result.get("expireAt")
            if raw_expire_at and self._panel_expiry_matches(raw_expire_at, expected_expire_at):
                return True

            if raw_expire_at:
                logging.warning(
                    "Panel update response expiry mismatch for user %s: expireAt=%r "
                    "expected=%s. Fetching panel user to verify persisted state.",
                    panel_user_uuid,
                    raw_expire_at,
                    expected_expire_at.isoformat(),
                )
            else:
                logging.info(
                    "Panel update response for user %s did not include expireAt. "
                    "Fetching panel user to verify persisted state.",
                    panel_user_uuid,
                )
        else:
            logging.warning(
                "Panel update response for user %s had unexpected type %s. "
                "Fetching panel user to verify persisted state.",
                panel_user_uuid,
                type(panel_update_result).__name__,
            )

        try:
            try:
                panel_user = await self.panel_service.get_user_by_uuid(
                    panel_user_uuid,
                    log_response=False,
                )
            except TypeError:
                panel_user = await self.panel_service.get_user_by_uuid(panel_user_uuid)
        except Exception:
            logging.exception(
                "Failed to verify panel expiry for user %s after update.",
                panel_user_uuid,
            )
            return False

        if not isinstance(panel_user, dict):
            logging.warning(
                "Panel expiry verification for user %s returned unexpected payload: %r",
                panel_user_uuid,
                panel_user,
            )
            return False
        return self._panel_expiry_matches(panel_user.get("expireAt"), expected_expire_at)

    @staticmethod
    def _device_topup_renewal_available(
        extra_hwid_devices: int,
        extra_hwid_valid_until: Optional[Any],
        subscription_end_date: Optional[Any],
    ) -> bool:
        if not isinstance(extra_hwid_valid_until, datetime) or not isinstance(
            subscription_end_date, datetime
        ):
            return False
        valid_until = (
            extra_hwid_valid_until
            if extra_hwid_valid_until.tzinfo
            else extra_hwid_valid_until.replace(tzinfo=timezone.utc)
        )
        end_date = (
            subscription_end_date
            if subscription_end_date.tzinfo
            else subscription_end_date.replace(tzinfo=timezone.utc)
        )
        return bool(int(extra_hwid_devices or 0) > 0 and valid_until < end_date)

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

    async def activate_subscription(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        payment_amount: float,
        payment_db_id: int,
        promo_code_id_from_payment: Optional[int] = None,
        provider: str = "yookassa",
        sale_mode: str = "subscription",
        traffic_gb: Optional[float] = None,
        tariff_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        sale_mode_base, sale_mode_tariff_key = self._parse_sale_mode_context(sale_mode, tariff_key)
        tariff_key = sale_mode_tariff_key
        if sale_mode_base in {"traffic", "traffic_package"} or (
            getattr(self.settings, "traffic_sale_mode", False) and not self._tariffs_config()
        ):
            target_gb = traffic_gb if traffic_gb is not None else float(months)
            return await self._activate_traffic_package(
                session=session,
                user_id=user_id,
                traffic_gb=target_gb,
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                tariff_key=tariff_key,
                sale_mode="traffic_package" if self._tariffs_config() else "traffic",
            )
        if sale_mode_base == "topup":
            if not tariff_key:
                active_user = await user_dal.get_user_by_id(session, user_id)
                active_sub = (
                    await subscription_dal.get_active_subscription_by_user_id(
                        session, user_id, active_user.panel_user_uuid
                    )
                    if active_user and active_user.panel_user_uuid
                    else None
                )
                tariff_key = active_sub.tariff_key if active_sub else None
            if not tariff_key:
                logging.error("Top-up activation requires tariff_key for user %s", user_id)
                return None
            return await self.activate_topup(
                session=session,
                user_id=user_id,
                tariff_key=tariff_key,
                traffic_gb=traffic_gb if traffic_gb is not None else float(months),
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
            )
        if sale_mode_base == "premium_topup":
            if not tariff_key:
                active_user = await user_dal.get_user_by_id(session, user_id)
                active_sub = (
                    await subscription_dal.get_active_subscription_by_user_id(
                        session, user_id, active_user.panel_user_uuid
                    )
                    if active_user and active_user.panel_user_uuid
                    else None
                )
                tariff_key = active_sub.tariff_key if active_sub else None
            if not tariff_key:
                logging.error("Premium top-up activation requires tariff_key for user %s", user_id)
                return None
            return await self.activate_premium_topup(
                session=session,
                user_id=user_id,
                tariff_key=tariff_key,
                traffic_gb=traffic_gb if traffic_gb is not None else float(months),
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
            )
        if sale_mode_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
            target_devices = int(traffic_gb if traffic_gb is not None else months)
            return await self.activate_hwid_device_topup(
                session=session,
                user_id=user_id,
                device_count=target_devices,
                payment_amount=payment_amount,
                payment_db_id=payment_db_id,
                provider=provider,
                tariff_key=tariff_key,
                renewal=sale_mode_base == "hwid_devices_renewal",
            )
        if sale_mode_base == "tariff_upgrade":
            if not tariff_key:
                logging.error("Tariff upgrade activation requires tariff_key for user %s", user_id)
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
            return result

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
            logging.error(f"User {user_id} not found in DB for paid subscription activation.")
            return None

        (
            panel_user_uuid,
            panel_sub_link_id,
            panel_short_uuid,
            panel_user_created_now,
        ) = await self._get_or_create_panel_user_link_details(session, user_id, db_user)

        if not panel_user_uuid or not panel_sub_link_id:
            logging.error(f"Failed to ensure panel user for TG {user_id} during paid subscription.")
            return None

        try:
            months_int = int(months)
        except Exception:
            months_int = 1

        current_active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, panel_user_uuid
        )
        start_date = datetime.now(timezone.utc)
        if (
            current_active_sub
            and current_active_sub.end_date
            and current_active_sub.end_date > start_date
        ):
            start_date = current_active_sub.end_date

        # base duration by months
        end_after_months = add_months(start_date, months_int)
        duration_days_total = (end_after_months - start_date).days
        applied_promo_bonus_days = 0

        if promo_code_id_from_payment:
            promo_model = await promo_code_dal.get_promo_code_by_id(
                session, promo_code_id_from_payment
            )
            if (
                promo_model
                and promo_model.is_active
                and promo_model.current_activations < promo_model.max_activations
            ):
                applied_promo_bonus_days = promo_model.bonus_days
                duration_days_total += applied_promo_bonus_days

                activation = await promo_code_dal.record_promo_activation(
                    session,
                    promo_code_id_from_payment,
                    user_id,
                    payment_id=payment_db_id,
                )
                if activation:
                    await promo_code_dal.increment_promo_code_usage(
                        session, promo_code_id_from_payment
                    )
                else:
                    logging.warning(
                        f"Promo code {promo_code_id_from_payment} was already activated by user {user_id}, but bonus applied via payment {payment_db_id}."  # noqa: E501
                    )
            else:
                logging.warning(
                    f"Promo code ID {promo_code_id_from_payment} (from payment) not found or invalid."  # noqa: E501
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
                    at=datetime.now(timezone.utc),
                    subscription_end_before=start_date,
                    delta=timedelta(days=applied_promo_bonus_days),
                )
            except Exception:
                logging.exception(
                    "Failed to extend HWID device purchases for promo payment bonus of user %s",
                    user_id,
                )
        await subscription_dal.deactivate_other_active_subscriptions(
            session, panel_user_uuid, panel_sub_link_id
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
            logging.exception("Failed to evaluate auto-renew availability for user %s", user_id)

        topup_balance_bytes = int(getattr(current_active_sub, "topup_balance_bytes", 0) or 0)
        extra_hwid_devices = 0
        hwid_devices_valid_until = None
        if current_active_sub:
            try:
                hwid_summary = await tariff_dal.get_hwid_device_entitlement_summary(
                    session,
                    subscription_id=current_active_sub.subscription_id,
                    at=datetime.now(timezone.utc),
                )
                extra_hwid_devices = int(hwid_summary.get("active_devices") or 0)
                hwid_devices_valid_until = hwid_summary.get("active_until")
            except Exception:
                logging.exception(
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
            logging.error(
                f"Failed to upsert paid subscription for user {user_id}: {e_upsert_sub}",
                exc_info=True,
            )
            return None

        panel_update_payload = self._build_panel_update_payload(
            panel_user_uuid=panel_user_uuid,
            expire_at=final_end_date,
            status="ACTIVE",
            traffic_limit_bytes=traffic_limit_bytes,
            traffic_limit_strategy="MONTH" if tariff else self.settings.USER_TRAFFIC_STRATEGY,
            hwid_device_limit=effective_hwid_limit,
        )
        if tariff:
            panel_update_payload["activeInternalSquads"] = self._panel_squads_for_tariff(
                tariff,
                include_premium=not premium_is_limited,
            )

        panel_update_payload.update(self._panel_identity_payload_for_user(db_user))

        updated_panel_user = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid, panel_update_payload
        )
        if not updated_panel_user or updated_panel_user.get("error"):
            logging.warning(
                f"Panel user details update FAILED for paid sub user {panel_user_uuid}. Response: {updated_panel_user}"  # noqa: E501
            )
            return None

        final_subscription_url = updated_panel_user.get("subscriptionUrl")
        final_panel_short_uuid = updated_panel_user.get("shortUuid", panel_short_uuid)
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
                logging.warning(
                    "Skipping HWID renewal purchase for payment %s: invalid window %s -> %s",
                    payment_db_id,
                    hwid_renewal_valid_from,
                    hwid_renewal_valid_until,
                )

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
        tariff_key: Optional[str] = None,
    ) -> Optional[datetime]:
        reason_lower = (reason or "").lower()
        apply_main_traffic_limit = any(
            keyword in reason_lower for keyword in ("admin", "promo code", "referral", "bonus")
        )

        user = await user_dal.get_user_by_id(session, user_id)
        if not user:
            logging.warning(f"Cannot extend subscription for user {user_id}: user not found.")
            return None

        panel_uuid, panel_sub_uuid, _, _ = await self._get_or_create_panel_user_link_details(
            session, user_id, user
        )
        if not panel_uuid or not panel_sub_uuid:
            logging.error(
                f"Failed to ensure panel user for subscription extension of user {user_id}."
            )
            return None

        active_sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, panel_uuid
        )
        rollback_payload: Optional[Dict[str, Any]] = None
        hwid_extension_context: Optional[Tuple[int, datetime, datetime]] = None
        pending_tariff_change_payload: Optional[Dict[str, Any]] = None
        requested_tariff = None
        if tariff_key and self._tariffs_config():
            try:
                requested_tariff = self._resolve_tariff(tariff_key, "period")
            except Exception:
                logging.warning(
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
        if not active_sub or not active_sub.end_date:
            logging.info(
                f"No active subscription found for user {user_id}. Creating new one for {bonus_days} days."  # noqa: E501
            )
            start_date = datetime.now(timezone.utc)
            new_end_date_obj = start_date + timedelta(days=bonus_days)

            # Apply main traffic limit for admin/referral/promo bonuses, fallback to trial limit otherwise  # noqa: E501
            traffic_limit = (
                self._traffic_limit_for_period_tariff(bonus_tariff)
                if bonus_tariff
                else self.settings.user_traffic_limit_bytes
                if apply_main_traffic_limit
                else self.settings.trial_traffic_limit_bytes
            )
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
            now_utc = datetime.now(timezone.utc)
            start_point_for_bonus = current_end_date if current_end_date > now_utc else now_utc
            new_end_date_obj = start_point_for_bonus + timedelta(days=bonus_days)
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
                    logging.exception(
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
                target_monthly_price = admin_tariff.period_price(
                    1,
                    default_currency_key_for_settings(self.settings),
                ) or admin_tariff.min_period_price(default_currency_key_for_settings(self.settings))
                admin_update_data: Dict[str, Any] = {
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
                    "hwid_device_limit": self._base_hwid_limit_for_tariff(admin_tariff),
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
                    "MONTH"
                    if panel_tariff and panel_tariff.billing_model == "period"
                    else self.settings.USER_TRAFFIC_STRATEGY
                    if panel_tariff
                    else None
                ),
                hwid_device_limit=(
                    self._effective_hwid_limit(
                        updated_sub_model.hwid_device_limit,
                        int(getattr(updated_sub_model, "extra_hwid_devices", 0) or 0),
                    )
                    if panel_tariff
                    else None
                ),
                include_uuid=False,
                include_default_squads=False,
            )
            if panel_tariff:
                panel_update_payload["activeInternalSquads"] = self._panel_squads_for_tariff(
                    panel_tariff,
                    include_premium=not bool(
                        getattr(updated_sub_model, "premium_is_limited", False)
                    ),
                )
                if self.settings.parsed_user_external_squad_uuid:
                    panel_update_payload["externalSquadUuid"] = (
                        self.settings.parsed_user_external_squad_uuid
                    )

            panel_update_success = await self.panel_service.update_user_details_on_panel(
                panel_uuid,
                panel_update_payload,
            )
            if not await self._panel_update_confirms_expiry(
                panel_uuid,
                panel_update_success,
                new_end_date_obj,
            ):
                logging.warning(
                    "Panel expiry update failed for user %s panel_uuid=%s after %s bonus. "
                    "requested_expire_at=%s panel_response=%s. Reverting local bonus update.",
                    user_id,
                    panel_uuid,
                    reason,
                    new_end_date_obj.isoformat(),
                    panel_update_success,
                )
                if rollback_payload:
                    try:
                        await subscription_dal.update_subscription(
                            session,
                            updated_sub_model.subscription_id,
                            rollback_payload,
                        )
                    except Exception:
                        logging.exception(
                            "Failed to revert local subscription update for user %s after "
                            "panel expiry update failure.",
                            user_id,
                        )
                if panel_tariff and "admin" in reason_lower:
                    return None
                return None

            if pending_tariff_change_payload:
                await tariff_dal.create_tariff_change(session, pending_tariff_change_payload)

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
                    logging.exception(
                        "Failed to extend HWID device purchases for %s bonus of user %s",
                        reason,
                        user_id,
                    )

            logging.info(
                f"Subscription for user {user_id} extended by {bonus_days} days ({reason}). New end date: {new_end_date_obj}."  # noqa: E501
            )
            return new_end_date_obj
        else:
            logging.error(f"Failed to update subscription end date locally for user {user_id}.")
            return None

    async def get_active_subscription_details(
        self, session: AsyncSession, user_id: int
    ) -> Optional[Dict[str, Any]]:
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            logging.info(
                f"User {user_id} not found in DB or no panel_user_uuid for 'my_subscription'."
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

        if not panel_user_data:
            if panel_user_confirmed_absent:
                logging.warning(
                    "Panel user %s confirmed absent on panel for user %s. "
                    "Clearing local linkage. reason=%s",
                    panel_user_uuid,
                    user_id,
                    panel_lookup_failure_reason,
                )
                await subscription_dal.deactivate_all_user_subscriptions(session, user_id)
                await user_dal.update_user(session, user_id, {"panel_user_uuid": None})
                return None
            logging.warning(
                "Panel user %s lookup failed for user %s; treating it as a panel access/API "
                "problem and preserving local linkage/subscription. reason=%s",
                panel_user_uuid,
                user_id,
                panel_lookup_failure_reason,
            )
            if local_active_sub:
                return await self._local_active_subscription_details_fallback(
                    db_user,
                    local_active_sub,
                )
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
                panel_expire_dt > datetime.now(timezone.utc) if panel_expire_dt else False
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
        hwid_entitlement_summary: Dict[str, Any] = {}
        active_extra_hwid_devices = (
            int(local_active_sub.extra_hwid_devices or 0) if local_active_sub else 0
        )
        if local_active_sub:
            try:
                hwid_entitlement_summary = await tariff_dal.get_hwid_device_entitlement_summary(
                    session,
                    subscription_id=local_active_sub.subscription_id,
                    at=datetime.now(timezone.utc),
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
                logging.exception(
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
            "premium_limit_bytes": self._premium_effective_limit_bytes(
                premium_baseline,
                premium_topup_balance,
                premium_topup_used,
                premium_bonus_bytes,
            ),
            "premium_is_limited": bool(local_active_sub.premium_is_limited)
            if local_active_sub
            else False,
            "premium_period_start_at": getattr(local_active_sub, "premium_period_start_at", None)
            if local_active_sub
            else None,
            "premium_squad_labels": premium_access.get("squad_labels") or [],
            "premium_node_labels": premium_access.get("node_labels") or [],
            "period_start_at": local_active_sub.period_start_at if local_active_sub else None,
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
    ) -> List[Dict[str, Any]]:
        subs_models_with_users = await subscription_dal.get_subscriptions_near_expiration(
            session, days_threshold
        )
        results = []
        for sub_model in subs_models_with_users:
            if sub_model.user and sub_model.end_date and not sub_model.skip_notifications:
                days_left = (sub_model.end_date - datetime.now(timezone.utc)).total_seconds() / (
                    24 * 3600
                )
                results.append(
                    {
                        "user_id": sub_model.user_id,
                        "first_name": sub_model.user.first_name or f"User {sub_model.user_id}",
                        "language_code": sub_model.user.language_code
                        or self.settings.DEFAULT_LANGUAGE,
                        "end_date_str": sub_model.end_date.strftime("%Y-%m-%d"),
                        "days_left": max(0, int(round(days_left))),
                        "subscription_end_date_iso_for_update": sub_model.end_date,
                    }
                )
        return results
