# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


class HwidDeviceMixin:
    @staticmethod
    def _as_aware_utc(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    async def _active_hwid_extra_devices_for_sub(
        self,
        session: AsyncSession,
        sub: Subscription,
        *,
        at: Optional[datetime] = None,
    ) -> int:
        try:
            return await tariff_dal.sum_active_hwid_devices(
                session,
                subscription_id=sub.subscription_id,
                at=at or datetime.now(timezone.utc),
            )
        except Exception:
            logging.exception(
                "Failed to recalculate active HWID devices for subscription %s",
                getattr(sub, "subscription_id", None),
            )
            return int(getattr(sub, "extra_hwid_devices", 0) or 0)

    async def _hwid_topup_validity_window(
        self,
        session: AsyncSession,
        sub: Subscription,
        *,
        renewal: bool,
        now: datetime,
    ) -> Optional[Tuple[datetime, datetime, Dict[str, Any]]]:
        valid_until = self._as_aware_utc(getattr(sub, "end_date", None))
        if not valid_until or valid_until <= now:
            return None

        summary = await tariff_dal.get_hwid_device_entitlement_summary(
            session,
            subscription_id=sub.subscription_id,
            at=now,
        )
        valid_from = now
        if renewal:
            active_until = self._as_aware_utc(summary.get("active_until"))
            if active_until and now < active_until < valid_until:
                valid_from = active_until
            elif active_until and active_until >= valid_until:
                return None
        return valid_from, valid_until, summary

    @staticmethod
    def _round_hwid_price(value: float, *, currency: str) -> float:
        if value <= 0:
            return 0.0
        if currency == "stars":
            return float(math.ceil(value))
        return math.ceil(float(value) * 100) / 100

    @staticmethod
    def _find_hwid_package(tariff: Tariff, device_count: int, currency: str) -> Optional[Any]:
        package_set = tariff.hwid_device_packages
        if not package_set:
            return None
        packages = package_set.for_currency(currency)
        return next((pkg for pkg in packages if int(pkg.count) == int(device_count)), None)

    def _quote_hwid_package_price(
        self,
        *,
        sub: Subscription,
        package: Any,
        valid_from: datetime,
        valid_until: datetime,
        now: datetime,
        currency: str,
    ) -> Dict[str, Any]:
        period_months = max(1, int(getattr(sub, "duration_months", None) or 1))
        full_price = float(package.price_for_period(period_months))
        period_start = self._as_aware_utc(getattr(sub, "start_date", None))
        period_end = self._as_aware_utc(getattr(sub, "end_date", None)) or valid_until
        inferred_period_start = add_months(period_end, -period_months)
        if not period_start or period_start >= period_end or period_start < inferred_period_start:
            period_start = inferred_period_start

        basis_seconds = max(1.0, (period_end - period_start).total_seconds())
        billable_start = max(now, valid_from)
        billable_seconds = max(0.0, (valid_until - billable_start).total_seconds())
        ratio = billable_seconds / basis_seconds
        raw_price = full_price * ratio
        price = self._round_hwid_price(raw_price, currency=currency)
        min_price = getattr(package, "min_price", None)
        if raw_price > 0 and min_price is not None:
            price = max(price, self._round_hwid_price(float(min_price), currency=currency))
        if currency == "stars":
            price = float(int(math.ceil(price)))

        return {
            "price": price,
            "full_price": full_price,
            "pricing_period_months": period_months,
            "proration_ratio": ratio,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "billable_seconds": billable_seconds,
            "period_seconds": basis_seconds,
            "currency": currency,
        }

    async def quote_hwid_device_topup(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        device_count: int,
        tariff_key: Optional[str] = None,
        renewal: bool = False,
        currency: str = "rub",
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            purchased_devices = int(device_count)
        except (TypeError, ValueError):
            return None
        if purchased_devices <= 0:
            return None

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None

        tariff = self._resolve_tariff(tariff_key or sub.tariff_key)
        if not tariff or tariff.billing_model != "period":
            return None
        base_hwid_limit = (
            int(sub.hwid_device_limit)
            if sub.hwid_device_limit is not None
            else self._base_hwid_limit_for_tariff(tariff)
        )
        if base_hwid_limit == 0:
            return None

        package = self._find_hwid_package(tariff, purchased_devices, currency)
        if not package:
            return None

        now = now or datetime.now(timezone.utc)
        window = await self._hwid_topup_validity_window(
            session,
            sub,
            renewal=renewal,
            now=now,
        )
        if not window:
            return None
        valid_from, valid_until, entitlement_summary = window
        quote = self._quote_hwid_package_price(
            sub=sub,
            package=package,
            valid_from=valid_from,
            valid_until=valid_until,
            now=now,
            currency=currency,
        )
        quote.update(
            {
                "subscription_id": sub.subscription_id,
                "tariff_key": tariff.key,
                "device_count": purchased_devices,
                "renewal": renewal,
                "active_extra_devices": int(entitlement_summary.get("active_devices") or 0),
                "active_until": entitlement_summary.get("active_until"),
            }
        )
        return quote

    async def activate_hwid_device_topup(
        self,
        session: AsyncSession,
        user_id: int,
        device_count: int,
        payment_amount: float,
        payment_db_id: int,
        provider: str = "yookassa",
        tariff_key: Optional[str] = None,
        renewal: bool = False,
    ) -> Optional[Dict[str, Any]]:
        try:
            purchased_devices = int(device_count)
        except (TypeError, ValueError):
            purchased_devices = 0
        if purchased_devices <= 0:
            logging.error("HWID device top-up requires positive device count for user %s", user_id)
            return None

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user or not db_user.panel_user_uuid:
            return None
        sub = await subscription_dal.get_active_subscription_by_user_id(
            session, user_id, db_user.panel_user_uuid
        )
        if not sub:
            return None

        tariff = None
        if self._tariffs_config():
            tariff = self._resolve_tariff(tariff_key or sub.tariff_key)
            if tariff.billing_model != "period":
                logging.info(
                    "Skipping HWID top-up for user %s because tariff %s is %s",
                    user_id,
                    tariff.key,
                    tariff.billing_model,
                )
                return None
            packages = (
                [
                    package
                    for currency_packages in tariff.hwid_device_packages.root.values()
                    for package in currency_packages
                ]
                if tariff.hwid_device_packages
                else []
            )
            if packages and not any(pkg.count == purchased_devices for pkg in packages):
                logging.error(
                    "HWID device package %s is not available for tariff %s",
                    purchased_devices,
                    tariff.key,
                )
                return None

        base_hwid_limit = (
            int(sub.hwid_device_limit)
            if sub.hwid_device_limit is not None
            else self._base_hwid_limit_for_tariff(tariff)
        )
        if base_hwid_limit == 0:
            logging.info(
                "Skipping HWID top-up for user %s because current limit is unlimited", user_id
            )
            return {
                "subscription_id": sub.subscription_id,
                "end_date": sub.end_date,
                "is_active": True,
                "panel_user_uuid": db_user.panel_user_uuid,
                "panel_short_uuid": getattr(sub, "panel_subscription_uuid", None),
                "hwid_device_limit": 0,
                "extra_hwid_devices": int(sub.extra_hwid_devices or 0),
                "purchased_hwid_devices": 0,
            }

        now = datetime.now(timezone.utc)
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        entitlement_summary = await tariff_dal.get_hwid_device_entitlement_summary(
            session,
            subscription_id=sub.subscription_id,
            at=now,
        )
        valid_from = self._as_aware_utc(getattr(payment, "hwid_valid_from", None))
        valid_until = self._as_aware_utc(getattr(payment, "hwid_valid_until", None))
        if valid_from and valid_until:
            if valid_until <= now or valid_from >= valid_until:
                logging.error(
                    "Frozen HWID quote is no longer valid for user %s "
                    "(payment_id=%s, valid_from=%s, valid_until=%s)",
                    user_id,
                    payment_db_id,
                    valid_from,
                    valid_until,
                )
                return None
        else:
            window = await self._hwid_topup_validity_window(
                session,
                sub,
                renewal=renewal,
                now=now,
            )
            if window:
                valid_from, valid_until, entitlement_summary = window
        if not valid_from or not valid_until:
            logging.error(
                "HWID top-up has no valid subscription window for user %s "
                "(subscription_id=%s, renewal=%s)",
                user_id,
                sub.subscription_id,
                renewal,
            )
            return None

        active_extra_devices = int(entitlement_summary.get("active_devices") or 0)
        starts_now = valid_from <= now < valid_until
        new_extra_devices = active_extra_devices + (purchased_devices if starts_now else 0)
        effective_hwid_limit = self._effective_hwid_limit(base_hwid_limit, new_extra_devices)
        await self._record_payment_context(
            session,
            payment_db_id,
            sale_mode="hwid_devices_renewal" if renewal else "hwid_devices",
            tariff_key=tariff.key if tariff else sub.tariff_key,
            purchased_hwid_devices=purchased_devices,
            hwid_valid_from=valid_from,
            hwid_valid_until=valid_until,
            hwid_pricing_period_months=getattr(payment, "hwid_pricing_period_months", None),
            hwid_proration_ratio=getattr(payment, "hwid_proration_ratio", None),
            hwid_full_price=getattr(payment, "hwid_full_price", None),
        )
        updated_sub = await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {
                "hwid_device_limit": base_hwid_limit,
                "extra_hwid_devices": new_extra_devices,
                "tariff_key": tariff.key if tariff else sub.tariff_key,
            },
        )
        if not updated_sub:
            return None

        panel_payload = self._build_panel_update_payload(
            panel_user_uuid=db_user.panel_user_uuid,
            expire_at=updated_sub.end_date,
            status="ACTIVE",
            hwid_device_limit=effective_hwid_limit,
        )
        panel_payload.update(self._panel_identity_payload_for_user(db_user))
        updated_panel = await self.panel_service.update_user_details_on_panel(
            db_user.panel_user_uuid,
            panel_payload,
        )
        if not updated_panel or updated_panel.get("error"):
            logging.warning(
                "Panel user HWID limit update failed for user %s. Response: %s",
                user_id,
                updated_panel,
            )
            return None

        final_subscription_url = updated_panel.get("subscriptionUrl")
        final_panel_short_uuid = updated_panel.get(
            "shortUuid", getattr(updated_sub, "panel_subscription_uuid", None)
        )
        await tariff_dal.create_hwid_device_purchase(
            session,
            subscription_id=updated_sub.subscription_id,
            payment_id=payment_db_id,
            purchased_devices=purchased_devices,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        await self._send_payment_success_email(
            db_user=db_user,
            sale_mode="hwid_devices_renewal" if renewal else "hwid_devices",
            months=purchased_devices,
            traffic_gb=None,
            payment_amount=payment_amount,
            end_date=valid_until,
            provider=provider,
        )
        return {
            "subscription_id": updated_sub.subscription_id,
            "end_date": updated_sub.end_date,
            "is_active": True,
            "panel_user_uuid": db_user.panel_user_uuid,
            "panel_short_uuid": final_panel_short_uuid,
            "subscription_url": final_subscription_url,
            "hwid_device_limit": effective_hwid_limit,
            "extra_hwid_devices": new_extra_devices,
            "purchased_hwid_devices": purchased_devices,
            "tariff_key": tariff.key if tariff else sub.tariff_key,
            "hwid_devices_valid_from": valid_from,
            "hwid_devices_valid_until": valid_until,
            "hwid_devices_renewal": renewal,
        }
