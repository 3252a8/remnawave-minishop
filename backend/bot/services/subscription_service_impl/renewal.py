# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


class RenewalMixin:
    async def charge_subscription_renewal(
        self,
        session: AsyncSession,
        sub: Subscription,
    ) -> bool:
        """Attempt to charge user using saved payment method. Return True on initiated/handled, False on failure."""  # noqa: E501
        if getattr(self.settings, "traffic_sale_mode", False):
            logging.info("Auto-renew skipped: traffic sale mode enabled")
            return True
        if not sub.auto_renew_enabled:
            return True
        # If autopayments are disabled globally, skip charging attempts
        if not self.settings.yookassa_autopayments_active:
            return True
        if sub.provider != "yookassa":
            logging.info(
                "Auto-renew skipped: provider %s does not support auto-renew", sub.provider
            )
            return True

        from db.dal.user_billing_dal import get_user_default_payment_method

        default_pm = await get_user_default_payment_method(session, sub.user_id)
        if not default_pm:
            logging.info(f"Auto-renew skipped: no saved payment method for user {sub.user_id}")
            return False

        # ``yookassa_service`` is wired onto the subscription service via
        # ``build_core_services`` (setattr). Read it directly — the previous
        # ``from .yookassa_service import …`` pointed at a non-existent module
        # inside this package, the ImportError got swallowed, and every
        # auto-renew silently returned False.
        yk = getattr(self, "yookassa_service", None)
        if not yk or not getattr(yk, "configured", False):
            logging.warning("YooKassa unavailable for auto-renew")
            return False

        months = sub.duration_months or 1
        currency = default_payment_currency_code_for_settings(self.settings)
        tariff_key = str(getattr(sub, "tariff_key", "") or "").strip() or None
        sale_mode = f"subscription@{tariff_key}" if tariff_key else "subscription"
        amount = None
        tariffs_config = (
            self._tariffs_config() if callable(getattr(self, "_tariffs_config", None)) else None
        )
        if tariffs_config and callable(getattr(self, "_resolve_tariff", None)):
            try:
                tariff = self._resolve_tariff(getattr(sub, "tariff_key", None))
            except Exception:
                tariff = None
            if tariff and tariff.billing_model == "period":
                amount = tariff.period_price(
                    months,
                    default_currency_key_for_settings(self.settings),
                )
        if amount is None:
            amount = self.settings.subscription_options.get(months)
        if not amount:
            logging.error(f"Auto-renew price missing for {months} months")
            return False

        hwid_quote = None
        quote_hwid_renewal = getattr(
            self,
            "quote_hwid_device_renewal_for_subscription",
            None,
        )
        if tariff_key and callable(quote_hwid_renewal):
            try:
                hwid_quote = await quote_hwid_renewal(
                    session,
                    user_id=sub.user_id,
                    target_tariff_key=tariff_key,
                    months=int(months),
                    currency=default_currency_key_for_settings(self.settings),
                )
            except Exception:
                logging.exception(
                    "Failed to quote HWID devices for auto-renew user %s",
                    sub.user_id,
                )
                hwid_quote = None
        if hwid_quote:
            amount = float(amount) + float(hwid_quote.get("price") or 0)

        metadata = {
            "user_id": str(sub.user_id),
            "auto_renew_for_subscription_id": str(sub.subscription_id),
            "subscription_months": str(months),
            "sale_mode": sale_mode,
        }
        if hwid_quote:
            metadata["hwid_devices"] = str(int(hwid_quote.get("device_count") or 0))
            for source_key, metadata_key in (
                ("valid_from", "hwid_valid_from"),
                ("valid_until", "hwid_valid_until"),
            ):
                value = hwid_quote.get(source_key)
                if value:
                    metadata[metadata_key] = (
                        value.isoformat() if hasattr(value, "isoformat") else str(value)
                    )
            for key in (
                "pricing_period_months",
                "proration_ratio",
                "full_price",
            ):
                value = hwid_quote.get(key)
                if value is not None:
                    metadata[f"hwid_{key}"] = str(value)
        resp = await yk.create_payment(
            amount=float(amount),
            currency=currency,
            description=f"Auto-renewal for {months} months",
            metadata=metadata,
            payment_method_id=default_pm.provider_payment_method_id,
            save_payment_method=False,
            capture=True,
        )
        if not resp or resp.get("status") not in {"pending", "waiting_for_capture", "succeeded"}:
            logging.error(f"Auto-renew create_payment failed: {resp}")
            return False
        logging.info(f"Auto-renew initiated for user {sub.user_id} payment_id={resp.get('id')}")
        return True
