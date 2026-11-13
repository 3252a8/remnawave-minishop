from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.subscription_service_impl.tariff_change_quote import (
    TariffChangePreflightStatus,
    preflight_paid_tariff_change,
)
from db.dal import payment_dal, subscription_dal, tribute_dal, user_dal
from db.models import Payment, Subscription

from ..shared import (
    EntitlementPreflightStatus,
    PaymentSuccessRequest,
    payment_units_for_activation,
    payment_uses_entitlement_context,
    preflight_payment_entitlement,
    sale_mode_base,
    sale_mode_tariff_key,
)
from .config import (
    TRIBUTE_PROVIDER,
    _as_utc,
    _shop_event_fingerprint,
)
from .models import TributeWebhookEnvelope
from .shop import (
    TributeShopOrderCancelledPayload,
    TributeShopOrderChargeFailedPayload,
    TributeShopOrderChargeSuccessPayload,
    TributeShopOrderPayload,
    TributeShopOrderPaymentFailedPayload,
    TributeShopOrderRefundedPayload,
    TributeShopWebhookPayload,
    tribute_shop_major_to_minor,
    tribute_shop_period_for_months,
)
from .webhook_runtime import TributeWebhookRuntime

logger = logging.getLogger(__name__)

_DUPLICATE_RECURRENCE_REASON = "duplicate_active_recurrence_manual_review"
_STALE_PAID_ENTITLEMENT_PREFIX = "stale_paid_entitlement:"
_INVALID_PAID_ENTITLEMENT_PREFIX = "invalid_paid_entitlement:"


class TributeShopWebhookMixin(TributeWebhookRuntime):
    @staticmethod
    def _shop_amount_snapshot(payment: Payment) -> tuple[int, int] | None:
        """Return ``(initial_charge, regular_charge)`` in minor units."""

        try:
            initial_amount = tribute_shop_major_to_minor(
                Decimal(str(payment.amount)),
                str(payment.currency),
            )
            regular_source = payment.amount
            if sale_mode_base(str(payment.sale_mode or "")) == "subscription":
                checkout_base_amount = getattr(payment, "checkout_base_amount", None)
                if checkout_base_amount is not None:
                    regular_source = checkout_base_amount
            regular_amount = tribute_shop_major_to_minor(
                Decimal(str(regular_source)),
                str(payment.currency),
            )
        except (TypeError, ValueError, OverflowError):
            return None
        return initial_amount, regular_amount

    def _shop_value_mismatch(
        self,
        payment: Payment,
        payload: TributeShopWebhookPayload,
        *,
        amount_kind: str,
    ) -> str | None:
        expected_shop_id = self.config.SHOP_ID
        if expected_shop_id is None:
            return "shop_id_unconfigured"
        if int(payload.shop_id) != int(expected_shop_id):
            return "shop_id_mismatch"
        amount_snapshot = self._shop_amount_snapshot(payment)
        if amount_snapshot is None:
            return "invalid_local_amount"
        initial_amount, regular_amount = amount_snapshot
        is_subscription = sale_mode_base(str(payment.sale_mode or "")) == "subscription"

        if amount_kind == "refund":
            accepted_amounts = {initial_amount}
            if is_subscription:
                accepted_amounts.add(regular_amount)
            if int(payload.amount) not in accepted_amounts:
                return "amount_mismatch"
        elif int(payload.amount) != regular_amount:
            return "amount_mismatch"

        if str(payload.currency).upper() != str(payment.currency or "").strip().upper():
            return "currency_mismatch"
        customer_id = getattr(payload, "customer_id", None)
        if customer_id is not None and str(customer_id) not in {
            str(payment.user_id),
            f"telegram:{int(payment.user_id)}",
        }:
            return "customer_mismatch"
        if bool(getattr(payload, "only_stars", False)) or int(
            getattr(payload, "stars_amount", 0) or 0
        ):
            return "unsupported_stars_payment"
        first_period_amount = getattr(payload, "first_period_amount", None)
        has_first_period_override = is_subscription and initial_amount != regular_amount
        if amount_kind == "initial" and has_first_period_override:
            if first_period_amount is None:
                return "first_period_amount_missing"
            if int(first_period_amount) != initial_amount:
                return "first_period_amount_mismatch"
        elif first_period_amount is not None and (
            not has_first_period_override or int(first_period_amount) != initial_amount
        ):
            return "first_period_amount_mismatch"
        return None

    def _shop_snapshot_mismatch(
        self,
        payment: Payment,
        payload: TributeShopWebhookPayload,
        *,
        initial: bool,
    ) -> str | None:
        value_mismatch = self._shop_value_mismatch(
            payment,
            payload,
            amount_kind="initial" if initial else "recurring",
        )
        if value_mismatch is not None:
            return value_mismatch

        base = sale_mode_base(str(payment.sale_mode or ""))
        is_subscription = base == "subscription"
        period = str(getattr(payload, "period", "") or "").lower()
        if initial:
            if (
                bool(getattr(payload, "is_trial", False))
                or getattr(payload, "trial_period", None) is not None
                or getattr(payload, "trial_ends_at", None) is not None
            ):
                # Minishop never creates Shop orders with trialPeriod. A paid
                # event carrying trial state therefore cannot prove a charge.
                return "unsupported_trial"
            if bool(getattr(payload, "is_recurrent", False)) != is_subscription:
                return "recurrence_mismatch"
            if not is_subscription:
                # Tribute's published Shop schema currently shows
                # ``isRecurrent=false`` together with ``period=monthly`` in
                # the canonical event example. The locally persisted order
                # UUID and sale mode are authoritative; provider flags are
                # useful metadata but must not make a paid one-time order
                # impossible to fulfil.
                return None
        elif not is_subscription:
            return "non_subscription_recurring_event"

        if is_subscription:
            try:
                expected_period = tribute_shop_period_for_months(
                    int(payment.subscription_duration_months)
                )
            except (TypeError, ValueError, OverflowError):
                return "invalid_local_period"
            if period != expected_period:
                return "period_mismatch"
        return None

    def _initial_entitlement_preflight(
        self,
        payment: Payment,
        active_subscription: Subscription | None,
    ) -> tuple[str | None, str | None]:
        """Return ``(stale_reason, invalid_reason)`` without mutating entitlements."""

        sale_mode = str(payment.sale_mode or "")
        base = sale_mode_base(sale_mode)
        if base == "tariff_upgrade":
            expected_target = str(payment.tariff_key or "").strip() or (
                sale_mode_tariff_key(sale_mode) or ""
            )
            result = preflight_paid_tariff_change(
                payment=payment,
                active_subscription=active_subscription,
                tariffs_config=getattr(self.settings, "tariffs_config", None),
                expected_user_id=int(payment.user_id),
                expected_target_tariff_key=expected_target,
            )
            if result.status is TariffChangePreflightStatus.DETERMINISTIC_STALE:
                return result.reason, None
            if result.status is TariffChangePreflightStatus.INVALID:
                return None, result.reason
            return None, None

        if payment_uses_entitlement_context(payment):
            result = preflight_payment_entitlement(payment, active_subscription)
            if result.status is EntitlementPreflightStatus.DETERMINISTIC_STALE:
                return result.reason or "entitlement_context_changed", None
            if result.status is EntitlementPreflightStatus.INVALID:
                return None, result.reason or "invalid_entitlement_context"
        return None, None

    @staticmethod
    def _shop_event_values(
        envelope: TributeWebhookEnvelope,
        payload: TributeShopWebhookPayload,
        fingerprint: str,
    ) -> dict[str, Any]:
        return {
            "fingerprint": fingerprint,
            "event_name": envelope.name,
            "order_uuid": str(payload.uuid),
            "event_created_at": _as_utc(envelope.created_at),
            "event_sent_at": _as_utc(envelope.sent_at),
            "amount": int(payload.amount),
            "currency": str(payload.currency).upper(),
            "transaction_id": getattr(payload, "transaction_id", None),
            "status": "processing",
        }

    async def _finalize_shop_payment(
        self,
        session: AsyncSession,
        *,
        payment: Payment,
        event: Any,
        payload: TributeShopWebhookPayload,
    ) -> web.Response:
        if str(payment.status or "").strip().lower() == "succeeded":
            if sale_mode_base(str(payment.sale_mode or "")) == "subscription":
                await self._sync_shop_auto_renew(
                    session,
                    user_id=int(payment.user_id),
                    tariff_key=str(payment.tariff_key or ""),
                    order_uuid=str(payload.uuid),
                )
            tribute_dal.mark_event_processed(
                event,
                payment_id=int(payment.payment_id),
            )
            await session.commit()
            return web.json_response(
                {
                    "ok": True,
                    "status": "processed",
                    "duplicate": True,
                    "payment_id": int(payment.payment_id),
                }
            )

        claimed = await payment_dal.claim_payment_finalization(
            session,
            int(payment.payment_id),
            provider_payment_id=str(payment.provider_payment_id),
        )
        if claimed is None:
            payment = await payment_dal.get_payment_by_db_id(
                session,
                int(payment.payment_id),
                fresh=True,
            )
            if payment is None or str(payment.status or "").strip().lower() != "succeeded":
                return web.json_response(
                    {"ok": False, "error": "activation_in_progress"},
                    status=503,
                )
        else:
            payment = claimed
            sale_mode = str(payment.sale_mode or "")
            base = sale_mode_base(sale_mode)
            units = payment_units_for_activation(payment, sale_mode)
            activation_extra_kwargs: dict[str, Any] = {}
            member_expires_at = getattr(payload, "member_expires_at", None)
            if base == "subscription" and member_expires_at is not None:
                activation_extra_kwargs["authoritative_end_at"] = _as_utc(member_expires_at)
            outcome = await self._finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=self.bot,
                    settings=self.settings,
                    i18n=self.i18n,
                    session=session,
                    subscription_service=self.subscription_service,
                    referral_service=self.referral_service,
                    payment=payment,
                    user_id=int(payment.user_id),
                    amount=float(payment.amount),
                    currency=str(payment.currency),
                    sale_mode=sale_mode,
                    months=units,
                    traffic_amount=(
                        float(units)
                        if base in {"traffic", "traffic_package", "topup", "premium_topup"}
                        else None
                    ),
                    provider_subscription=TRIBUTE_PROVIDER,
                    provider_notification=TRIBUTE_PROVIDER,
                    db_user=getattr(payment, "user", None),
                    log_prefix="Tribute Shop webhook",
                    activation_extra_kwargs=activation_extra_kwargs,
                    skip_referral_bonus=base != "subscription",
                )
            )
            if outcome is None:
                return web.json_response(
                    {"ok": False, "error": "activation_failed"},
                    status=500,
                )

        if sale_mode_base(str(payment.sale_mode or "")) == "subscription":
            await self._sync_shop_auto_renew(
                session,
                user_id=int(payment.user_id),
                tariff_key=str(payment.tariff_key or ""),
                order_uuid=str(payload.uuid),
            )
        tribute_dal.mark_event_processed(
            event,
            payment_id=int(payment.payment_id),
        )
        await session.commit()
        return web.json_response(
            {
                "ok": True,
                "status": "processed",
                "payment_id": int(payment.payment_id),
            }
        )

    async def _process_shop_event(
        self,
        envelope: TributeWebhookEnvelope,
        payload: TributeShopWebhookPayload,
    ) -> web.Response:
        fingerprint = _shop_event_fingerprint(envelope, payload)
        order_uuid = str(payload.uuid)
        async with self.async_session_factory() as session:
            initial_payment = await payment_dal.get_payment_by_provider_payment_id(
                session,
                TRIBUTE_PROVIDER,
                order_uuid,
                fresh=True,
            )
            if initial_payment is None:
                # The provider can deliver immediately after creating the order,
                # before the checkout request commits the UUID. A retryable
                # response closes that race without accepting an unknown order.
                return web.json_response(
                    {"ok": False, "error": "payment_not_found"},
                    status=404,
                )

            initial_order = isinstance(payload, TributeShopOrderPayload)
            initial_recurrence = (
                initial_order
                and sale_mode_base(str(initial_payment.sale_mode or "")) == "subscription"
            )
            if initial_order:
                locked_user = await user_dal.lock_user_by_id(
                    session,
                    int(initial_payment.user_id),
                )
                if locked_user is None:
                    return web.json_response(
                        {"ok": False, "error": "user_not_found"},
                        status=404,
                    )

            event, _created = await tribute_dal.ensure_shop_webhook_event(
                session,
                self._shop_event_values(envelope, payload, fingerprint),
            )
            if event.status in {"processed", "ignored", "quarantined"}:
                await session.commit()
                return web.json_response(
                    {
                        "ok": True,
                        "status": str(event.status),
                        "duplicate": True,
                    }
                )

            mismatch: str | None
            if isinstance(payload, TributeShopOrderPayload):
                mismatch = self._shop_snapshot_mismatch(
                    initial_payment,
                    payload,
                    initial=True,
                )
            elif isinstance(
                payload,
                (
                    TributeShopOrderChargeSuccessPayload,
                    TributeShopOrderChargeFailedPayload,
                    TributeShopOrderCancelledPayload,
                ),
            ):
                mismatch = self._shop_snapshot_mismatch(
                    initial_payment,
                    payload,
                    initial=False,
                )
            else:
                mismatch = self._shop_value_mismatch(
                    initial_payment,
                    payload,
                    amount_kind=(
                        "refund"
                        if isinstance(payload, TributeShopOrderRefundedPayload)
                        else "initial"
                    ),
                )
            if mismatch is not None:
                tribute_dal.mark_event_processed(
                    event,
                    status="quarantined",
                    reason=mismatch,
                    payment_id=int(initial_payment.payment_id),
                )
                await session.commit()
                return web.json_response(
                    {"ok": False, "error": "snapshot_mismatch", "reason": mismatch},
                    status=400,
                )

            if isinstance(
                payload,
                (TributeShopOrderPayload, TributeShopOrderChargeSuccessPayload),
            ):
                tombstone_reason = await tribute_dal.get_shop_success_tombstone_reason(
                    session,
                    order_uuid=order_uuid,
                    success_created_at=_as_utc(envelope.created_at),
                    initial_success=isinstance(payload, TributeShopOrderPayload),
                )
                if tombstone_reason is not None:
                    if isinstance(payload, TributeShopOrderPayload):
                        await payment_dal.update_payment_status_by_db_id(
                            session,
                            int(initial_payment.payment_id),
                            (
                                "refunded"
                                if tombstone_reason in {"completed_refund", "last_charge_refunded"}
                                else "failed"
                            ),
                        )
                    tribute_dal.mark_event_processed(
                        event,
                        status="quarantined",
                        reason=f"superseded_by_{tombstone_reason}",
                        payment_id=int(initial_payment.payment_id),
                    )
                    await session.commit()
                    return web.json_response(
                        {
                            "ok": True,
                            "status": "quarantined",
                            "reason": tombstone_reason,
                        }
                    )

            if initial_order and (
                sale_mode_base(str(initial_payment.sale_mode or "")) == "tariff_upgrade"
                or payment_uses_entitlement_context(initial_payment)
            ):
                active_subscription = (
                    await subscription_dal.get_active_subscription_by_user_id_for_update(
                        session,
                        int(initial_payment.user_id),
                    )
                )
                stale_reason, invalid_reason = self._initial_entitlement_preflight(
                    initial_payment,
                    active_subscription,
                )
                if invalid_reason is not None:
                    logger.error(
                        "Tribute Shop payment %s failed deterministic preflight: %s.",
                        initial_payment.payment_id,
                        invalid_reason,
                    )
                    await payment_dal.update_payment_status_by_db_id(
                        session,
                        int(initial_payment.payment_id),
                        "failed",
                    )
                    tribute_dal.mark_event_processed(
                        event,
                        status="quarantined",
                        reason=f"{_INVALID_PAID_ENTITLEMENT_PREFIX}{invalid_reason}",
                        payment_id=int(initial_payment.payment_id),
                    )
                    await session.commit()
                    return web.json_response(
                        {
                            "ok": True,
                            "status": "quarantined",
                            "reason": invalid_reason,
                            "manual_review": True,
                        }
                    )
                if stale_reason is not None:
                    refund_status = await self._refund_shop_order_exact_sell(
                        order_uuid,
                        expected_amount=Decimal(str(initial_payment.amount)),
                        expected_currency=str(initial_payment.currency),
                    )
                    if refund_status is None:
                        await session.rollback()
                        return web.json_response(
                            {
                                "ok": False,
                                "error": "stale_entitlement_refund_failed",
                            },
                            status=503,
                        )
                    await payment_dal.update_payment_status_by_db_id(
                        session,
                        int(initial_payment.payment_id),
                        "refunded" if refund_status == "already_refunded" else "failed",
                    )
                    quarantine_reason = f"{_STALE_PAID_ENTITLEMENT_PREFIX}{stale_reason}"
                    tribute_dal.mark_event_processed(
                        event,
                        status="quarantined",
                        reason=quarantine_reason,
                        payment_id=int(initial_payment.payment_id),
                    )
                    await session.commit()
                    logger.warning(
                        "Refunded and quarantined stale Tribute Shop payment "
                        "order=%s payment=%s user=%s reason=%s refund_status=%s.",
                        order_uuid,
                        initial_payment.payment_id,
                        initial_payment.user_id,
                        stale_reason,
                        refund_status,
                    )
                    return web.json_response(
                        {
                            "ok": True,
                            "status": "quarantined",
                            "reason": stale_reason,
                            "refund_status": refund_status,
                        }
                    )

            if initial_recurrence:
                other_shop_order = await tribute_dal.get_other_active_shop_order_uuid(
                    session,
                    user_id=int(initial_payment.user_id),
                    exclude_order_uuid=order_uuid,
                )
                other_creator_subscription = (
                    await tribute_dal.get_other_active_creator_subscription_id(
                        session,
                        user_id=int(initial_payment.user_id),
                    )
                )
                if other_shop_order is not None or other_creator_subscription is not None:
                    if not await self._cancel_shop_order(order_uuid):
                        await session.rollback()
                        return web.json_response(
                            {
                                "ok": False,
                                "error": "conflicting_recurrence_cancel_failed",
                            },
                            status=503,
                        )
                    refund_status = await self._refund_shop_order_exact_sell(
                        order_uuid,
                        expected_amount=Decimal(str(initial_payment.amount)),
                        expected_currency=str(initial_payment.currency),
                    )
                    if refund_status is None:
                        await session.rollback()
                        return web.json_response(
                            {
                                "ok": False,
                                "error": "conflicting_recurrence_refund_failed",
                            },
                            status=503,
                        )
                    await payment_dal.update_payment_status_by_db_id(
                        session,
                        int(initial_payment.payment_id),
                        "refunded" if refund_status == "already_refunded" else "failed",
                    )
                    tribute_dal.mark_event_processed(
                        event,
                        status="quarantined",
                        reason=_DUPLICATE_RECURRENCE_REASON,
                        payment_id=int(initial_payment.payment_id),
                    )
                    await session.commit()
                    logger.error(
                        "Cancelled and quarantined conflicting Tribute Shop recurrence "
                        "order=%s user=%s active_shop_order=%s active_creator_subscription=%s.",
                        order_uuid,
                        initial_payment.user_id,
                        other_shop_order,
                        other_creator_subscription,
                    )
                    return web.json_response(
                        {
                            "ok": True,
                            "status": "quarantined",
                            "manual_review": True,
                            "recurrence_cancelled": True,
                            "refund_status": refund_status,
                        }
                    )

            if not isinstance(payload, TributeShopOrderPayload):
                quarantine_reason = await tribute_dal.get_shop_order_quarantine_reason(
                    session,
                    order_uuid,
                )
                if quarantine_reason is not None:
                    if (
                        isinstance(payload, TributeShopOrderRefundedPayload)
                        and str(payload.status) == "completed"
                    ):
                        await payment_dal.update_payment_status_by_db_id(
                            session,
                            int(initial_payment.payment_id),
                            "refunded",
                        )
                        completed_reason = (
                            "duplicate_recurrence_refund_completed"
                            if quarantine_reason == _DUPLICATE_RECURRENCE_REASON
                            else "quarantined_order_refund_completed"
                        )
                        tribute_dal.mark_event_processed(
                            event,
                            reason=completed_reason,
                            payment_id=int(initial_payment.payment_id),
                        )
                        await session.commit()
                        return web.json_response(
                            {
                                "ok": True,
                                "status": "refunded",
                                "manual_review": True,
                            }
                        )
                    tribute_dal.mark_event_processed(
                        event,
                        status="quarantined",
                        reason=str(quarantine_reason),
                        payment_id=int(initial_payment.payment_id),
                    )
                    await session.commit()
                    return web.json_response(
                        {
                            "ok": True,
                            "status": "quarantined",
                            "manual_review": True,
                        }
                    )

            if isinstance(payload, TributeShopOrderPayload):
                return await self._finalize_shop_payment(
                    session,
                    payment=initial_payment,
                    event=event,
                    payload=payload,
                )

            if isinstance(payload, TributeShopOrderChargeSuccessPayload):
                months = int(initial_payment.subscription_duration_months or 1)
                regular_amount = getattr(initial_payment, "checkout_base_amount", None)
                if regular_amount is None:
                    regular_amount = initial_payment.amount
                cycle_payment = await payment_dal.ensure_payment_with_provider_id(
                    session,
                    user_id=int(initial_payment.user_id),
                    amount=float(regular_amount),
                    currency=str(initial_payment.currency),
                    months=months,
                    description=f"Tribute recurring charge: {order_uuid}",
                    provider=TRIBUTE_PROVIDER,
                    provider_payment_id=f"shop_charge:{order_uuid}:{fingerprint}",
                    sale_mode=str(initial_payment.sale_mode),
                    tariff_key=str(initial_payment.tariff_key or "") or None,
                    purchased_gb=getattr(initial_payment, "purchased_gb", None),
                    purchased_hwid_devices=getattr(
                        initial_payment,
                        "purchased_hwid_devices",
                        None,
                    ),
                    hwid_valid_from=getattr(initial_payment, "hwid_valid_from", None),
                    hwid_valid_until=getattr(initial_payment, "hwid_valid_until", None),
                    hwid_pricing_period_months=getattr(
                        initial_payment,
                        "hwid_pricing_period_months",
                        None,
                    ),
                    hwid_proration_ratio=getattr(
                        initial_payment,
                        "hwid_proration_ratio",
                        None,
                    ),
                    hwid_full_price=getattr(initial_payment, "hwid_full_price", None),
                    hwid_traffic_bonus_bytes=getattr(
                        initial_payment,
                        "hwid_traffic_bonus_bytes",
                        None,
                    ),
                    entitlement_context_snapshot=getattr(
                        initial_payment,
                        "entitlement_context_snapshot",
                        None,
                    ),
                    checkout_bundle_snapshot=getattr(
                        initial_payment,
                        "checkout_bundle_snapshot",
                        None,
                    ),
                    checkout_bundle_hash=getattr(
                        initial_payment,
                        "checkout_bundle_hash",
                        None,
                    ),
                )
                if hasattr(cycle_payment, "is_auto_renew"):
                    cycle_payment.is_auto_renew = True
                event.payment_id = int(cycle_payment.payment_id)
                await session.flush()
                return await self._finalize_shop_payment(
                    session,
                    payment=cycle_payment,
                    event=event,
                    payload=payload,
                )

            if isinstance(payload, TributeShopOrderChargeFailedPayload):
                retry_reason = f"charge_retry_{int(payload.charge_retries)}"
                event.status_reason = retry_reason
                if int(payload.charge_retries) >= 3:
                    await self._sync_shop_auto_renew(
                        session,
                        user_id=int(initial_payment.user_id),
                        tariff_key=str(initial_payment.tariff_key or ""),
                        order_uuid=order_uuid,
                    )
                tribute_dal.mark_event_processed(
                    event,
                    reason=retry_reason,
                    payment_id=int(initial_payment.payment_id),
                )
                await session.commit()
                return web.json_response({"ok": True, "status": "charge_failed"})

            if isinstance(payload, TributeShopOrderCancelledPayload):
                event.status_reason = str(payload.cancel_reason)
                await self._sync_shop_auto_renew(
                    session,
                    user_id=int(initial_payment.user_id),
                    tariff_key=str(initial_payment.tariff_key or ""),
                    order_uuid=order_uuid,
                )
                tribute_dal.mark_event_processed(
                    event,
                    reason=str(payload.cancel_reason),
                    payment_id=int(initial_payment.payment_id),
                )
                await session.commit()
                return web.json_response({"ok": True, "status": "cancelled"})

            if isinstance(payload, TributeShopOrderPaymentFailedPayload):
                await payment_dal.update_payment_status_by_db_id(
                    session,
                    int(initial_payment.payment_id),
                    "failed",
                )
                tribute_dal.mark_event_processed(
                    event,
                    reason=str(payload.error_code),
                    payment_id=int(initial_payment.payment_id),
                )
                await session.commit()
                return web.json_response({"ok": True, "status": "failed"})

            if isinstance(payload, TributeShopOrderRefundedPayload):
                refund_completed = str(payload.status) == "completed"
                if (
                    refund_completed
                    and sale_mode_base(str(initial_payment.sale_mode or "")) != "subscription"
                ):
                    await payment_dal.update_payment_status_by_db_id(
                        session,
                        int(initial_payment.payment_id),
                        "refunded",
                    )
                tribute_dal.mark_event_processed(
                    event,
                    reason=(
                        "manual_entitlement_review" if refund_completed else "refund_initiated"
                    ),
                    payment_id=int(initial_payment.payment_id),
                )
                await session.commit()
                logger.warning(
                    "Tribute Shop order %s transaction %s was refunded; "
                    "already consumed traffic/devices are not clawed back automatically.",
                    order_uuid,
                    payload.transaction_id,
                )
                return web.json_response(
                    {
                        "ok": True,
                        "status": "refunded" if refund_completed else "refund_initiated",
                        "manual_review": refund_completed,
                    }
                )

            tribute_dal.mark_event_processed(event, status="ignored", reason="unsupported_event")
            await session.commit()
            return web.json_response({"ok": True, "status": "ignored"})
