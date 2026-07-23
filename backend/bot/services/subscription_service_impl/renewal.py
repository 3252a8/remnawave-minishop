import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import AutoRenewFailureReason, SubscriptionAutoRenewFailedPayload
from bot.middlewares.i18n import get_i18n_instance
from bot.payment_providers.shared import (
    RecurringProviderService,
    build_payment_description,
    make_translator,
)
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.models import Subscription

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SubscriptionRenewalQuote:
    amount: float
    currency: str
    months: int
    sale_mode: str
    tariff_key: str | None
    hwid_quote: dict[str, Any] | None


def _renewal_idempotence_key(
    sub: Subscription,
    *,
    renewal_cycle_end: datetime | None,
) -> str:
    """Build a YooKassa-safe key stable for one renewal cycle attempt.

    ``renewal_cycle_end`` comes from the panel event when available.  That is
    deliberately preferred over the mutable local ``Subscription.end_date``:
    after a successful webhook extends the same subscription row, a late copy
    of the old panel event must still resolve to the original payment order.
    Every before-expiry stage for that cycle deliberately shares this key:
    a second panel event must not create a second merchant-initiated charge.
    """
    cycle_end = renewal_cycle_end or getattr(sub, "end_date", None)
    if isinstance(cycle_end, datetime):
        if cycle_end.tzinfo is None:
            cycle_end = cycle_end.replace(tzinfo=UTC)
        # Panel payloads may express the same instant with or without a time
        # component.  A renewal period cannot legitimately recur twice on one
        # UTC date, so the normalized calendar date prevents representation
        # drift from producing a second charge key.
        cycle_anchor = cycle_end.astimezone(UTC).date().isoformat()
    else:
        cycle_anchor = str(cycle_end or "missing")
    source = "|".join(
        (
            "yookassa-auto-renew-v1",
            str(getattr(sub, "subscription_id", "missing")),
            cycle_anchor,
        )
    )
    # YooKassa limits Idempotence-Key to 64 characters.  The fixed prefix and
    # UUID5 digest are 40 ASCII characters and retain no customer data.
    return f"yk-auto-{uuid.uuid5(uuid.NAMESPACE_URL, source).hex}"


async def _emit_auto_renew_failure(
    *,
    sub: Subscription,
    provider: str,
    reason_code: AutoRenewFailureReason,
    renewal_cycle_end: datetime | None,
    retryable: bool,
    payment_db_id: int | None = None,
    provider_payment_id: str | None = None,
) -> None:
    """Emit the neutral failure contract without exposing provider details."""

    await events.emit_model(
        SubscriptionAutoRenewFailedPayload(
            user_id=int(sub.user_id),
            subscription_id=int(sub.subscription_id),
            provider=provider,
            reason_code=reason_code,
            payment_db_id=payment_db_id,
            provider_payment_id=provider_payment_id,
            renewal_cycle_end=renewal_cycle_end or getattr(sub, "end_date", None),
            retryable=retryable,
            occurred_at=datetime.now(UTC),
        )
    )


class RenewalMixin(SubscriptionServiceMixinContract):
    def recurring_service_for(self, provider: str | None) -> RecurringProviderService | None:
        """Resolve a provider service that can charge a saved payment method."""
        provider_key = str(provider or "").strip().lower()
        if not provider_key:
            return None
        try:
            services = self.recurring_provider_services
        except AttributeError:
            return None
        return (services or {}).get(provider_key)

    async def quote_subscription_renewal(
        self,
        session: AsyncSession,
        sub: Subscription,
    ) -> SubscriptionRenewalQuote | None:
        """Build the authoritative entitlement and price for one renewal.

        This quote is shared by charge initiation and compatibility handling for
        in-flight YooKassa charges created by a previous application version.
        Provider callback values are deliberately not inputs to the quote.
        """
        months = int(sub.duration_months or 1)
        if months <= 0:
            return None

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
            logger.error("Auto-renew price missing for %s months", months)
            return None

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
                    months=months,
                    currency=default_currency_key_for_settings(self.settings),
                )
            except Exception:
                logger.exception(
                    "Failed to quote HWID devices for auto-renew user %s",
                    sub.user_id,
                )
                hwid_quote = None
        if hwid_quote:
            amount = float(amount) + float(hwid_quote.get("price") or 0)

        return SubscriptionRenewalQuote(
            amount=float(amount),
            currency=currency,
            months=months,
            sale_mode=sale_mode,
            tariff_key=tariff_key,
            hwid_quote=hwid_quote,
        )

    async def charge_subscription_renewal(
        self,
        session: AsyncSession,
        sub: Subscription,
        *,
        renewal_cycle_end: datetime | None = None,
    ) -> bool:
        """Attempt to charge user using saved payment method.

        Returns True when the renewal is skipped intentionally or the charge was
        accepted by the provider, and False when the renewal needs attention.
        """
        if getattr(self.settings, "traffic_sale_mode", False):
            logger.info("Auto-renew skipped: traffic sale mode enabled")
            return True
        if not sub.auto_renew_enabled:
            return True

        from bot.payment_providers import provider_supports_recurring
        from bot.payment_providers.shared import RecurringChargeContext, service_supports_recurring

        provider = str(getattr(sub, "provider", "") or "").strip().lower()
        if not provider_supports_recurring(provider):
            logger.info(
                "Auto-renew skipped: provider %s does not support auto-renew",
                getattr(sub, "provider", None),
            )
            return True

        recurring_service = self.recurring_service_for(provider)
        if not recurring_service:
            logger.warning("%s unavailable for auto-renew", provider)
            await _emit_auto_renew_failure(
                sub=sub,
                provider=provider,
                reason_code="provider_unavailable",
                renewal_cycle_end=renewal_cycle_end,
                retryable=True,
            )
            return False
        if not getattr(recurring_service, "configured", False):
            logger.warning("%s is not configured for auto-renew", provider)
            await _emit_auto_renew_failure(
                sub=sub,
                provider=provider,
                reason_code="provider_unavailable",
                renewal_cycle_end=renewal_cycle_end,
                retryable=True,
            )
            return False
        if not service_supports_recurring(recurring_service):
            logger.info("Auto-renew skipped: %s recurring charges are disabled", provider)
            return True

        from db.dal.user_billing_dal import get_user_default_payment_method

        default_pm = await get_user_default_payment_method(session, sub.user_id, provider=provider)
        if not default_pm:
            logger.info(
                "Auto-renew skipped: no saved %s payment method for user %s",
                provider,
                sub.user_id,
            )
            await _emit_auto_renew_failure(
                sub=sub,
                provider=provider,
                reason_code="saved_payment_method_missing",
                renewal_cycle_end=renewal_cycle_end,
                retryable=False,
            )
            return False

        quote = await self.quote_subscription_renewal(session, sub)
        if quote is None:
            await _emit_auto_renew_failure(
                sub=sub,
                provider=provider,
                reason_code="renewal_quote_unavailable",
                renewal_cycle_end=renewal_cycle_end,
                retryable=True,
            )
            return False
        months = quote.months
        currency = quote.currency
        sale_mode = quote.sale_mode
        amount = quote.amount
        hwid_quote = quote.hwid_quote

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

        i18n = getattr(self, "i18n", None) or get_i18n_instance()
        description = build_payment_description(
            make_translator(
                i18n,
                str(getattr(self.settings, "DEFAULT_LANGUAGE", "en") or "en"),
            ),
            months=months,
            sale_mode=sale_mode,
        )

        try:
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
                    description=description,
                    metadata=metadata,
                    hwid_quote=hwid_quote,
                    idempotence_key=_renewal_idempotence_key(
                        sub,
                        renewal_cycle_end=renewal_cycle_end,
                    ),
                    renewal_cycle_end=renewal_cycle_end or getattr(sub, "end_date", None),
                )
            )
        except Exception:
            logger.exception("Auto-renew saved-method charge crashed for provider %s", provider)
            await _emit_auto_renew_failure(
                sub=sub,
                provider=provider,
                reason_code="provider_request_failed",
                renewal_cycle_end=renewal_cycle_end,
                retryable=True,
            )
            return False
        if not result.initiated:
            logger.error(
                "Auto-renew saved-method charge failed for provider %s: %s",
                provider,
                result.message,
            )
            await _emit_auto_renew_failure(
                sub=sub,
                provider=provider,
                reason_code="provider_rejected",
                renewal_cycle_end=renewal_cycle_end,
                retryable=True,
                payment_db_id=result.payment_db_id,
                provider_payment_id=result.provider_payment_id,
            )
            return False
        logger.info(
            "Auto-renew initiated for user %s provider=%s payment_id=%s status=%s",
            sub.user_id,
            provider,
            result.provider_payment_id,
            result.status,
        )
        return True
