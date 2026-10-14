"""Renew period subscriptions through the same durable cycles using one balance."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot

from bot.middlewares.i18n import JsonI18n
from bot.payment_providers.shared.common import sale_mode_base
from bot.payment_providers.shared.durable_recurring import (
    DurableRecurringDispatch,
    prepare_durable_recurring_charge,
)
from bot.payment_providers.shared.recurring import (
    BALANCE_RECURRING_PROVIDERS,
    BalancePaymentMethod,
    RecurringChargeContext,
    RecurringChargeResult,
)
from bot.payment_providers.shared.success import PaymentSuccessRequest, finalize_successful_payment
from bot.services.partner_checkout_balance import (
    PartnerCheckoutBalanceAllocation,
    PartnerCheckoutBalanceService,
)
from bot.services.partner_common import PartnerError, amount_to_minor, currency_scale
from bot.services.subscription_gifts import is_gift_sale
from bot.services.user_balance_service import (
    UserBalanceAllocation,
    UserBalanceError,
    UserBalanceService,
)
from config.settings import Settings
from db.dal import auto_renew_dal, partner_dal, payment_dal, user_balance_dal, user_dal
from db.models import Payment

logger = logging.getLogger(__name__)

BALANCE_RECURRING_ADDON_BASES = frozenset(
    {"traffic", "traffic_package", "topup", "premium_topup", "hwid_device", "hwid_devices"}
)


def balance_recurring_available(settings: Settings, provider: str) -> bool:
    if not settings.USER_BALANCE_RECURRING_ENABLED:
        return False
    if settings.traffic_sale_mode:
        return False
    if provider == "user_balance":
        return bool(getattr(settings.balance_settings, "enabled", False))
    if provider == "partner_balance":
        partner = settings.partner_settings
        return bool(partner.enabled and partner.balance_payment_enabled)
    return False


def active_balance_recurrence(subscription: Any) -> bool:
    return bool(
        subscription is not None
        and str(getattr(subscription, "provider", "") or "").lower() in BALANCE_RECURRING_PROVIDERS
        and bool(getattr(subscription, "auto_renew_enabled", False))
    )


def balance_recurrence_blocks_purchase(subscription: Any, sale_mode: str) -> bool:
    return (
        active_balance_recurrence(subscription)
        and sale_mode_base(sale_mode) in BALANCE_RECURRING_ADDON_BASES
    )


class BalanceRecurringService:
    def __init__(
        self,
        settings: Settings,
        *,
        provider: str,
        subscription_service: Any,
        referral_service: Any,
        bot: Bot | None,
        i18n: JsonI18n,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self.bot = bot
        self.i18n = i18n

    @property
    def configured(self) -> bool:
        return True

    @property
    def recurring_active(self) -> bool:
        return balance_recurring_available(self.settings, self.provider)

    async def charge_saved_payment_method(
        self, context: RecurringChargeContext
    ) -> RecurringChargeResult:
        if not self.recurring_active:
            return RecurringChargeResult.failed("balance_auto_renew_unavailable")
        if (
            sale_mode_base(context.sale_mode) != "subscription"
            or is_gift_sale(context.sale_mode)
            or not isinstance(context.saved_method, BalancePaymentMethod)
            or context.saved_method.provider != self.provider
            or context.saved_method.user_id != context.user_id
        ):
            return RecurringChargeResult.failed("balance_auto_renew_context_invalid")
        if context.auto_renew_cycle_id is not None and context.retry_kind == "financial":
            cycle = await auto_renew_dal.get_cycle(
                context.session, context.auto_renew_cycle_id, fresh=True
            )
            if (
                cycle is None
                or int(cycle.financial_attempts or 0) >= self._max_financial_attempts()
            ):
                await auto_renew_dal.stop_cycle(
                    context.session, context.auto_renew_cycle_id, "financial_attempt_cap"
                )
                await context.session.commit()
                return RecurringChargeResult.failed("financial_attempt_cap")
        preparation = await prepare_durable_recurring_charge(
            context,
            provider=self.provider,
            saved_method_id=context.saved_method.provider_payment_method_id,
            pending_status="pending",
            max_transport_replays=int(self.settings.AUTO_RENEW_MAX_TRANSPORT_REPLAYS),
            lease_seconds=60,
        )
        if preparation.result is not None:
            return preparation.result
        dispatch = preparation.dispatch
        if dispatch is None:
            return RecurringChargeResult.failed("balance_dispatch_missing")
        try:
            if not self.recurring_active:
                raise UserBalanceError("balance_auto_renew_unavailable", 409)
            if context.currency.upper() != self.settings.balance_settings.currency.upper():
                raise UserBalanceError("user_balance_currency_mismatch", 409)
            payment = await payment_dal.get_payment_by_db_id_for_update(
                context.session, dispatch.payment_id
            )
            if payment is None:
                raise UserBalanceError("balance_payment_missing", 409)
            user = await user_dal.lock_user_by_id(context.session, context.user_id)
            if user is None or bool(user.is_banned):
                raise UserBalanceError("access_denied", 403)
            # The quote and reservation lock the source; the entire frozen order
            # must fit. Never supplement it from another balance or a saved card.
            if await self._already_reserved(context, payment):
                allocation = None
            elif self.provider == "user_balance":
                allocation = await UserBalanceService(self.settings).quote(
                    context.session,
                    user_id=context.user_id,
                    currency=context.currency,
                    checkout_total=context.amount,
                )
            else:
                allocation = await PartnerCheckoutBalanceService(self.settings).quote(
                    context.session,
                    user_id=context.user_id,
                    currency=context.currency,
                    checkout_total=context.amount,
                )
            if allocation is not None and allocation.external_minor != 0:
                raise UserBalanceError("insufficient_balance", 409)
            if allocation is not None:
                payment.checkout_total_amount = allocation.checkout_total_amount
            payment.balance_auto_renew = True
            if isinstance(allocation, UserBalanceAllocation):
                payment.user_balance_amount_minor = allocation.applied_minor
                payment.user_balance_currency_scale = allocation.currency_scale
                payment.funding_source = "internal_user_balance"
                await UserBalanceService.reserve(
                    context.session, payment_id=dispatch.payment_id, allocation=allocation
                )
            elif isinstance(allocation, PartnerCheckoutBalanceAllocation):
                payment.partner_balance_amount_minor = allocation.applied_minor
                payment.partner_balance_currency_scale = allocation.currency_scale
                payment.funding_source = "internal_partner_balance"
                await PartnerCheckoutBalanceService.reserve(
                    context.session, payment_id=dispatch.payment_id, allocation=allocation
                )
            payment.status = "succeeded_pending_finalization"
            await context.session.commit()
        except (UserBalanceError, PartnerError) as exc:
            await context.session.rollback()
            return await self._failed_debit(context, dispatch, exc.code)
        if (
            not self.recurring_active
            or not await auto_renew_dal.validate_dispatch_context_for_update(
                context.session, dispatch.cycle_id
            )
        ):
            await payment_dal.update_payment_status_by_db_id(
                context.session, dispatch.payment_id, "activation_failed"
            )
            await auto_renew_dal.stop_cycle(context.session, dispatch.cycle_id, "consent_changed")
            await context.session.commit()
            return RecurringChargeResult.failed(
                "consent_changed", payment_db_id=dispatch.payment_id
            )
        outcome = await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=context.session,
                subscription_service=self.subscription_service,
                referral_service=self.referral_service,
                payment=payment,
                user_id=context.user_id,
                amount=context.amount,
                currency=context.currency,
                sale_mode=context.sale_mode,
                months=context.months,
                traffic_amount=None,
                provider_subscription=self.provider,
                provider_notification=self.provider,
                skip_referral_bonus=True,
            )
        )
        current = await payment_dal.get_payment_by_db_id(
            context.session, dispatch.payment_id, fresh=True
        )
        if outcome is None and (current is None or str(current.status) != "succeeded"):
            await auto_renew_dal.stop_cycle(context.session, dispatch.cycle_id, "activation_failed")
            await context.session.commit()
            return RecurringChargeResult.failed(
                "activation_failed", payment_db_id=dispatch.payment_id
            )
        return RecurringChargeResult.ok(payment_db_id=dispatch.payment_id, status="succeeded")

    def _max_financial_attempts(self) -> int:
        return min(2, max(1, int(self.settings.AUTO_RENEW_MAX_FINANCIAL_ATTEMPTS)))

    async def _already_reserved(self, context: RecurringChargeContext, payment: Payment) -> bool:
        if str(payment.status) != "succeeded_pending_finalization":
            return False
        if self.provider == "user_balance":
            spend = await user_balance_dal.get_ledger_entry_by_key(
                context.session, f"user-balance-checkout-spend:{payment.payment_id}"
            )
            release = await user_balance_dal.get_ledger_entry_by_key(
                context.session, f"user-balance-checkout-spend-release:{payment.payment_id}"
            )
            source_valid = spend is not None and int(spend.user_id) == context.user_id
        else:
            spend = await partner_dal.get_ledger_entry_by_key(
                context.session, f"checkout-spend:{payment.payment_id}"
            )
            release = await partner_dal.get_ledger_entry_by_key(
                context.session, f"checkout-spend-release:{payment.payment_id}"
            )
            profile = await partner_dal.get_profile_by_user_id(
                context.session, context.user_id, for_update=True
            )
            source_valid = bool(
                profile is not None
                and str(profile.status) == "active"
                and spend is not None
                and int(spend.partner_id) == int(profile.partner_id)
            )
        if (
            not source_valid
            or spend is None
            or (release is not None and str(release.state) == "posted")
            or str(spend.currency).upper() != context.currency.upper()
            or int(spend.amount_minor)
            != -amount_to_minor(context.amount, scale=currency_scale(context.currency))
        ):
            raise UserBalanceError("balance_reservation_unavailable", 409)
        return True

    async def _failed_debit(
        self,
        context: RecurringChargeContext,
        dispatch: DurableRecurringDispatch,
        reason: str,
    ) -> RecurringChargeResult:
        await payment_dal.update_payment_status_by_db_id(
            context.session, dispatch.payment_id, "failed_creation"
        )
        await auto_renew_dal.mark_request_failure(
            context.session,
            payment_id=dispatch.payment_id,
            status="failed_creation",
            failure_kind=reason,
            http_status=None,
            provider_code=None,
        )
        cycle = await auto_renew_dal.get_cycle(context.session, dispatch.cycle_id, fresh=True)
        retry_at = datetime.now(UTC) + timedelta(hours=6)
        cycle_end = context.renewal_cycle_end
        if isinstance(cycle_end, datetime):
            cycle_end = (
                cycle_end.replace(tzinfo=UTC)
                if cycle_end.tzinfo is None
                else cycle_end.astimezone(UTC)
            )
        retryable = bool(
            reason
            in {"insufficient_balance", "insufficient_user_balance", "insufficient_partner_balance"}
            and self.settings.AUTO_RENEW_RETRY_ENABLED
            and cycle is not None
            and int(cycle.financial_attempts or 0) < self._max_financial_attempts()
            and cycle_end is not None
            and retry_at <= cycle_end + timedelta(hours=self.settings.AUTO_RENEW_RETRY_GRACE_HOURS)
        )
        if retryable:
            await auto_renew_dal.schedule_financial_retry(
                context.session,
                cycle_id=dispatch.cycle_id,
                next_attempt_at=retry_at,
                cancellation_party=None,
                cancellation_reason=reason,
            )
        else:
            await auto_renew_dal.stop_cycle(context.session, dispatch.cycle_id, reason)
        await context.session.commit()
        logger.info(
            "Balance renewal debit failed payment=%s source=%s reason=%s",
            dispatch.payment_id,
            self.provider,
            reason,
        )
        return RecurringChargeResult.failed(
            reason, payment_db_id=dispatch.payment_id, retryable=retryable
        )
