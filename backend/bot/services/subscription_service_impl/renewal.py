# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


class RenewalMixin:
    def recurring_service_for(self, provider: Optional[str]) -> Any:
        """Resolve a provider service that can charge a saved payment method."""
        provider_key = str(provider or "").strip().lower()
        if not provider_key:
            return None
        services = getattr(self, "recurring_provider_services", {}) or {}
        return services.get(provider_key)

    async def charge_subscription_renewal(
        self,
        session: AsyncSession,
        sub: Subscription,
    ) -> bool:
        """Attempt to charge user using saved payment method.

        Returns True when the renewal is skipped intentionally or the charge was
        accepted by the provider, and False when the renewal needs attention.
        """
        if getattr(self.settings, "traffic_sale_mode", False):
            logging.info("Auto-renew skipped: traffic sale mode enabled")
            return True
        if not sub.auto_renew_enabled:
            return True

        from bot.payment_providers import provider_supports_recurring
        from bot.payment_providers.shared import RecurringChargeContext, service_supports_recurring

        provider = str(getattr(sub, "provider", "") or "").strip().lower()
        if not provider_supports_recurring(provider):
            logging.info(
                "Auto-renew skipped: provider %s does not support auto-renew",
                getattr(sub, "provider", None),
            )
            return True

        recurring_service = self.recurring_service_for(provider)
        if not recurring_service:
            logging.warning("%s unavailable for auto-renew", provider)
            return False
        if not getattr(recurring_service, "configured", False):
            logging.warning("%s is not configured for auto-renew", provider)
            return False
        if not service_supports_recurring(recurring_service):
            logging.info("Auto-renew skipped: %s recurring charges are disabled", provider)
            return True

        from db.dal.user_billing_dal import get_user_default_payment_method

        default_pm = await get_user_default_payment_method(session, sub.user_id, provider=provider)
        if not default_pm:
            logging.info(
                "Auto-renew skipped: no saved %s payment method for user %s",
                provider,
                sub.user_id,
            )
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
            logging.error("Auto-renew price missing for %s months", months)
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

        result = await recurring_service.charge_saved_payment_method(
            RecurringChargeContext(
                session=session,
                user_id=sub.user_id,
                subscription_id=sub.subscription_id,
                saved_method=default_pm,
                amount=float(amount),
                currency=currency,
                months=int(months),
                sale_mode=sale_mode,
                description=f"Auto-renewal for {months} months",
                metadata=metadata,
                hwid_quote=hwid_quote,
            )
        )
        if not result.initiated:
            logging.error(
                "Auto-renew saved-method charge failed for provider %s: %s",
                provider,
                result.message,
            )
            return False
        logging.info(
            "Auto-renew initiated for user %s provider=%s payment_id=%s status=%s",
            sub.user_id,
            provider,
            result.provider_payment_id,
            result.status,
        )
        return True
