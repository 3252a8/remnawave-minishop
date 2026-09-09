from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_checkout_dal, payment_dal, payment_reconciliation_dal
from db.models import Payment

from .checkout_expiration import resolve_checkout_expiration
from .common import (
    detached_payment_snapshot,
    payment_amount_and_currency_match,
    payment_amount_matches,
    payment_units_for_activation,
)
from .success import PaymentSuccessRequest, finalize_successful_payment
from .webhooks import notify_user_payment_failed

logger = logging.getLogger(__name__)

LifecycleState = Literal["pending", "failed", "succeeded", "unknown"]

RECONCILABLE_PROVIDER_KEYS = (
    "cloudpayments",
    "cryptopay",
    "freekassa",
    "heleket",
    "lava",
    "overpay",
    "oxapay",
    "pally",
    "paykilla",
    "platega",
    "platega_card",
    "platega_crypto",
    "platega_sbp",
    "rollypay",
    "rollypay_card",
    "rollypay_crypto",
    "rollypay_international",
    "rollypay_sbp",
    "severpay",
    "stripe",
    "tribute",
)

_EXPIRY_ONLY_PROVIDER_KEYS = {"cloudpayments", "overpay", "tribute"}

_FAILED_STATUSES = {
    "cryptopay": {"expired"},
    "heleket": {"cancel", "fail", "system_fail", "wrong_amount"},
    "lava": {"cancel", "cancelled", "error", "expired", "failed"},
    "oxapay": {"expired", "refunded"},
    "pally": {"cancelled", "canceled", "fail", "failed"},
    "paykilla": {
        "cancelled",
        "canceled",
        "expired",
        "failed",
        "invoice_cancelled",
        "invoice_expired",
        "payment_cancelled",
        "payment_failed",
    },
    "platega": {"canceled", "cancelled", "chargebacked"},
    "rollypay": {"canceled", "cancelled", "expired", "chargeback", "refunded"},
    "severpay": {"decline", "fail"},
}
_SUCCESS_STATUSES = {
    "cryptopay": {"paid"},
    "heleket": {"paid", "paid_over"},
    "oxapay": {"manual_accept", "paid"},
    "lava": {"success"},
    "pally": {"overpaid", "success"},
    "paykilla": {"completed", "paid", "success"},
    "platega": {"confirmed"},
    "rollypay": {"paid"},
    "severpay": {"success"},
}
_PENDING_STATUSES = {
    "cloudpayments": {"authorized", "awaitingauthentication", "created", "pending"},
    "cryptopay": {"active"},
    "heleket": {"check"},
    "oxapay": {"new", "paying", "refunding", "underpaid", "waiting"},
    "lava": {"created", "pending", "processing"},
    "pally": {"new", "process", "underpaid"},
    "paykilla": {"created", "new", "pending", "processing"},
    "platega": {"pending"},
    "rollypay": {"created", "processing"},
    "severpay": {"new", "process"},
}

_FAILED_STATUSES["cloudpayments"] = {"cancelled", "canceled", "declined"}
_SUCCESS_STATUSES["cloudpayments"] = {"completed"}


@dataclass(frozen=True, slots=True)
class ProviderLifecycle:
    state: LifecycleState
    provider_status: str = ""
    checkout_expires_at: datetime | None = None
    failure_provider_code: str | None = None
    payment_verified: bool = False
    provider_payment_id: str | None = None


async def supersede_earlier_pending_hosted_checkouts(
    session: AsyncSession,
    payment: Any,
    service: Any,
    *,
    pending_status: str,
) -> None:
    """Cancel older payable links after a replacement checkout is ready."""

    cancel_pending = getattr(service, "cancel_pending_bill", None)
    if cancel_pending is None:
        return
    earlier = await payment_checkout_dal.list_earlier_pending_provider_payments_for_checkout_scope(
        session,
        payment,
        pending_status=pending_status,
    )
    snapshots = [detached_payment_snapshot(item) for item in earlier]
    await session.rollback()
    replacement_id = int(payment.payment_id)
    for previous in snapshots:
        previous_id = int(previous.payment_id)
        provider_payment_id = str(previous.provider_payment_id or "").strip()
        if not provider_payment_id:
            continue
        try:
            canceled, _response = await cancel_pending(provider_payment_id)
        except Exception:
            logger.exception(
                "Failed to cancel superseded %s checkout %s.",
                getattr(previous, "provider", "hosted"),
                previous_id,
            )
            continue
        if not canceled:
            logger.warning(
                "Provider kept superseded %s checkout %s active.",
                getattr(previous, "provider", "hosted"),
                previous_id,
            )
            continue
        await payment_dal.transition_provider_payment_to_terminal(
            session,
            previous_id,
            provider_payment_id,
            "canceled",
            failure_kind="superseded_checkout",
            provider_cancellation_party="merchant",
            provider_cancellation_reason=f"superseded_by_payment_{replacement_id}",
            suppress_failure_notification=True,
        )
        await session.commit()
        logger.info(
            "Canceled superseded %s checkout %s after creating payment %s.",
            getattr(previous, "provider", "hosted"),
            previous_id,
            replacement_id,
        )


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _state_for(provider: str, status: Any) -> LifecycleState:
    normalized = _normalized(status)
    if normalized in _FAILED_STATUSES.get(provider, set()):
        return "failed"
    if normalized in _SUCCESS_STATUSES.get(provider, set()):
        return "succeeded"
    if normalized in _PENDING_STATUSES.get(provider, set()):
        return "pending"
    return "unknown"


def _payload_payment_id(value: Any) -> str | None:
    try:
        payload = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return str(payload.get("payment_db_id") or payload.get("payment_id") or "").strip() or None


def _id_matches(data: dict[str, Any], expected: str, *keys: str) -> bool:
    returned = {str(data.get(key) or "").strip() for key in keys}
    returned.discard("")
    return not returned or expected in returned


def _pally_checkout_expiration(payment: Any, service: Any) -> datetime | None:
    expires_at = getattr(payment, "checkout_expires_at", None)
    if expires_at is not None:
        return expires_at
    created_at = getattr(payment, "created_at", None)
    ttl_seconds = getattr(service, "ttl_seconds", None)
    if created_at is None or ttl_seconds is None:
        return None
    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError):
        return None
    if ttl <= 0:
        return None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC) + timedelta(seconds=ttl)


async def _inspect_provider_payment(service: Any, payment: Payment) -> ProviderLifecycle:
    provider = _normalized(payment.provider)
    provider_id = str(payment.provider_payment_id or "").strip()
    if not provider_id and provider not in {"cloudpayments", "overpay"}:
        return ProviderLifecycle("unknown")

    success = False
    data: dict[str, Any] = {}
    status: Any = None
    state_provider = provider

    payment_verified = False
    if provider == "cloudpayments":
        success, data = await service.find_payment(int(payment.payment_id))
        invoice_id = str(data.get("InvoiceId") or data.get("invoiceId") or "").strip()
        if success and invoice_id and invoice_id != str(payment.payment_id):
            return ProviderLifecycle("unknown")
        provider_id = str(
            data.get("TransactionId") or data.get("transactionId") or provider_id
        ).strip()
        status = data.get("Status") or data.get("status")
        payment_verified = bool(
            success
            and _state_for("cloudpayments", status) == "succeeded"
            and payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=data.get("Amount") or data.get("amount"),
                received_currency=data.get("Currency") or data.get("currency"),
            )
        )
    elif provider == "overpay":
        success, data = await service.get_transaction_by_tracking_id(int(payment.payment_id))
        tracking_id = str(data.get("tracking_id") or "").strip()
        if success and tracking_id and tracking_id != str(payment.payment_id):
            return ProviderLifecycle("unknown")
        status = data.get("status")
        overpay_state: LifecycleState = (
            "succeeded"
            if _normalized(status) in {"successful", "success"}
            else "failed"
            if _normalized(status)
            in {"failed", "declined", "error", "expired", "canceled", "cancelled"}
            else "pending"
            if _normalized(status) in {"incomplete", "pending", "processing"}
            else "unknown"
        )
        if success and overpay_state == "succeeded":
            payment_verified = bool(
                service._amount_matches_payment(data.get("amount"), payment)
                and service._currency_matches_payment(data.get("currency"), payment)
            )
        provider_id = str(data.get("uid") or data.get("id") or provider_id).strip()
        return ProviderLifecycle(
            overpay_state if success else "unknown",
            _normalized(status),
            payment_verified=payment_verified,
            provider_payment_id=provider_id or None,
        )
    elif provider == "oxapay":
        success, data = await service.get_payment_info(provider_id)
        if success and (
            not _id_matches(data, provider_id, "track_id")
            or str(data.get("order_id") or "") != str(payment.payment_id)
        ):
            return ProviderLifecycle("unknown")
        status = data.get("status")
        payment_verified = bool(
            success
            and _state_for("oxapay", status) == "succeeded"
            and payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=data.get("amount"),
                received_currency=data.get("currency"),
                places=None,
            )
        )
    elif provider == "heleket":
        success, data = await service.get_payment_info(provider_id)
        if success and (
            not _id_matches(data, provider_id, "uuid")
            or str(data.get("order_id") or "") != str(payment.payment_id)
        ):
            return ProviderLifecycle("unknown")
        status = data.get("payment_status") or data.get("status")
        payment_verified = bool(
            success
            and _state_for("heleket", status) == "succeeded"
            and payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=data.get("amount"),
                received_currency=data.get("currency"),
                places=None,
            )
        )
    elif provider in {"platega", "platega_sbp", "platega_card", "platega_crypto"}:
        success, data = await service.get_transaction(provider_id)
        if success and not _id_matches(data, provider_id, "id"):
            return ProviderLifecycle("unknown")
        payload_payment_id = _payload_payment_id(data.get("payload")) if success else None
        if payload_payment_id and payload_payment_id != str(payment.payment_id):
            return ProviderLifecycle("unknown")
        received_amount = data.get("amount")
        received_currency = data.get("currency")
        payment_details = data.get("paymentDetails")
        if isinstance(payment_details, dict):
            received_amount = payment_details.get("amount", received_amount)
            received_currency = payment_details.get("currency", received_currency)
        status = data.get("status")
        state_provider = "platega"
        payment_verified = bool(
            success
            and _state_for("platega", status) == "succeeded"
            and payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=received_amount,
                received_currency=received_currency,
                places=None,
                allow_overpayment=True,
            )
        )
    elif provider in {
        "rollypay",
        "rollypay_sbp",
        "rollypay_card",
        "rollypay_international",
        "rollypay_crypto",
    }:
        success, data = await service.get_payment(provider_id)
        if success and not _id_matches(data, provider_id, "payment_id", "id"):
            return ProviderLifecycle("unknown")
        if success and str(data.get("order_id") or "") != f"minishop-{payment.payment_id}":
            return ProviderLifecycle("unknown")
        status = data.get("status")
        state_provider = "rollypay"
        payment_verified = bool(
            success
            and _state_for("rollypay", status) == "succeeded"
            and payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=data.get("amount"),
                received_currency=data.get("currency") or data.get("payment_currency"),
                places=2,
            )
        )
    elif provider == "lava":
        success, data = await service.get_invoice_status(
            order_id=str(payment.payment_id),
            invoice_id=provider_id,
        )
        if success and (
            not _id_matches(data, provider_id, "id", "invoice_id")
            or (
                data.get("order_id") is not None
                and str(data.get("order_id")) != str(payment.payment_id)
            )
            or (
                data.get("orderId") is not None
                and str(data.get("orderId")) != str(payment.payment_id)
            )
        ):
            return ProviderLifecycle("unknown")
        status = data.get("status")
        payment_verified = bool(
            success
            and _state_for("lava", status) == "succeeded"
            and payment_amount_matches(
                expected_amount=payment.amount,
                received_amount=data.get("amount"),
            )
        )
    elif provider == "paykilla":
        success, data = await service.get_invoice_details(provider_id)
        if success and (
            not _id_matches(data, provider_id, "id")
            or str(data.get("clientOrderId") or "") != str(payment.payment_id)
        ):
            return ProviderLifecycle("unknown")
        status = data.get("status")
        if success and _state_for("paykilla", status) == "succeeded":
            expected_amount, expected_currency = await service._invoice_amount_and_currency(
                amount=float(payment.amount),
                payment_currency=str(payment.currency),
            )
            payment_verified = bool(
                payment_amount_and_currency_match(
                    expected_amount=expected_amount,
                    expected_currency=expected_currency,
                    received_amount=(
                        data.get("totalPrice") or data.get("expectedAmount") or data.get("amount")
                    ),
                    received_currency=data.get("currency"),
                    places=None,
                    allow_overpayment=True,
                )
            )
    elif provider == "pally":
        success, data = await service.get_bill_status(provider_id)
        if success and not _id_matches(data, provider_id, "id", "bill_id"):
            return ProviderLifecycle("unknown")
        order_id = data.get("order_id") if success else None
        if order_id is None and success:
            order_id = data.get("orderId")
        if order_id is not None and str(order_id) != str(payment.payment_id):
            return ProviderLifecycle("unknown")
        status = data.get("status") or data.get("Status")
        if success and _state_for("pally", status) == "succeeded":
            normalized_status = _normalized(status)
            received_amount = data.get("amount")
            if received_amount is None:
                received_amount = data.get("OutSum") or data.get("out_sum")
            received_currency = data.get("currency_in")
            if received_currency is None:
                received_currency = data.get("CurrencyIn") or data.get("currency")
            payer_pays_commission = bool(
                getattr(getattr(service, "config", None), "PAYER_PAYS_COMMISSION", False)
            )
            payment_verified = payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=received_amount,
                received_currency=received_currency,
                allow_overpayment=(normalized_status == "overpaid" or payer_pays_commission),
            )
    elif provider == "severpay":
        success, data = await service.get_payment(provider_id)
        if success and (
            not _id_matches(data, provider_id, "id", "uid")
            or str(data.get("order_id") or "") != str(payment.payment_id)
        ):
            return ProviderLifecycle("unknown")
        status = data.get("status")
        payment_verified = bool(
            success
            and _state_for("severpay", status) == "succeeded"
            and payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=data.get("amount"),
                received_currency=data.get("currency"),
                allow_overpayment=True,
            )
        )
    elif provider == "stripe":
        if bool(getattr(payment, "is_auto_renew", False)):
            intent = await service.retrieve_payment_intent(provider_id)
            success = isinstance(intent, dict)
            data = intent if isinstance(intent, dict) else {}
            if success and not _id_matches(data, provider_id, "id"):
                return ProviderLifecycle("unknown")
            metadata = data.get("metadata") if success else None
            if isinstance(metadata, dict):
                returned_payment_id = str(metadata.get("payment_db_id") or "").strip()
                if returned_payment_id and returned_payment_id != str(payment.payment_id):
                    return ProviderLifecycle("unknown")
            intent_status = _normalized(data.get("status"))
            intent_state: LifecycleState = (
                "succeeded"
                if intent_status == "succeeded"
                else "failed"
                if intent_status in {"canceled", "requires_payment_method"}
                else "pending"
                if intent_status in {"processing", "requires_capture"}
                else "unknown"
            )
            return ProviderLifecycle(
                intent_state if success else "unknown",
                intent_status,
                payment_verified=bool(
                    success
                    and intent_state == "succeeded"
                    and service.payment_intent_matches_payment(payment, data)
                ),
            )
        success, data = await service.retrieve_checkout_session(provider_id)
        if success and not _id_matches(data, provider_id, "id"):
            return ProviderLifecycle("unknown")
        metadata = data.get("metadata") if success else None
        if isinstance(metadata, dict):
            returned_payment_id = str(metadata.get("payment_db_id") or "").strip()
            if returned_payment_id and returned_payment_id != str(payment.payment_id):
                return ProviderLifecycle("unknown")
        checkout_status = _normalized(data.get("status"))
        payment_status = _normalized(data.get("payment_status"))
        if checkout_status == "expired":
            checkout_state: LifecycleState = "failed"
        elif checkout_status == "complete" and payment_status in {"paid", "no_payment_required"}:
            checkout_state = "succeeded"
        elif checkout_status == "open":
            checkout_state = "pending"
        else:
            checkout_state = "unknown"
        return ProviderLifecycle(
            checkout_state if success else "unknown",
            checkout_status or payment_status,
            resolve_checkout_expiration(data),
            payment_verified=bool(
                success
                and checkout_state == "succeeded"
                and service.checkout_session_matches_payment(payment, data)
            ),
        )
    elif provider == "cryptopay":
        invoice = await service.get_invoice(provider_id)
        if invoice is None or str(invoice.invoice_id) != provider_id:
            return ProviderLifecycle("unknown")
        payload_payment_id = _payload_payment_id(invoice.payload)
        if payload_payment_id and payload_payment_id != str(payment.payment_id):
            return ProviderLifecycle("unknown")
        status = invoice.status
        success = True
        data = {"expiration_date": invoice.expiration_date}
        if _state_for("cryptopay", status) == "succeeded":
            payment_verified = payment_amount_and_currency_match(
                expected_amount=payment.amount,
                expected_currency=payment.currency,
                received_amount=getattr(invoice, "amount", None),
                received_currency=getattr(invoice, "asset", None)
                or getattr(invoice, "currency", None),
                places=None,
            )
    elif provider == "freekassa":
        paid_success, paid_data = await service.get_orders(
            payment_id=payment.payment_id,
            order_status=1,
        )
        if paid_success:
            for order in paid_data.get("orders") or []:
                if (
                    isinstance(order, dict)
                    and str(order.get("merchant_order_id") or "") == str(payment.payment_id)
                    and str(order.get("status")) == "1"
                ):
                    verified = payment_amount_and_currency_match(
                        expected_amount=payment.amount,
                        expected_currency=payment.currency,
                        received_amount=order.get("amount"),
                        received_currency=order.get("currency"),
                        allow_overpayment=True,
                    )
                    return ProviderLifecycle(
                        "succeeded",
                        "1",
                        payment_verified=verified,
                    )
        pending_success, pending_data = await service.get_orders(
            payment_id=payment.payment_id,
            order_status=0,
        )
        if pending_success:
            for order in pending_data.get("orders") or []:
                if (
                    isinstance(order, dict)
                    and str(order.get("merchant_order_id") or "") == str(payment.payment_id)
                    and str(order.get("status")) == "0"
                ):
                    return ProviderLifecycle("pending", "0")
        return ProviderLifecycle("unknown")
    else:
        return ProviderLifecycle("unknown")

    if not success or not isinstance(data, dict):
        return ProviderLifecycle("unknown")
    provider_status = _normalized(status)
    provider_state = _state_for(state_provider, provider_status)
    failure_provider_code = None
    if provider == "pally" and provider_state == "failed" and hasattr(service, "get_bill_payments"):
        details_success, details = await service.get_bill_payments(provider_id)
        if details_success and isinstance(details, dict):
            items = details.get("data")
            if isinstance(items, list):
                failed_item = next(
                    (
                        item
                        for item in items
                        if isinstance(item, dict)
                        and _normalized(item.get("status")) in _FAILED_STATUSES["pally"]
                    ),
                    None,
                )
                if failed_item is not None:
                    code = failed_item.get("error_code") or failed_item.get("error_message")
                    if code not in (None, ""):
                        failure_provider_code = str(code)[:128]
    expires_at = resolve_checkout_expiration(data)
    if (
        provider == "heleket"
        and provider_state == "pending"
        and expires_at is not None
        and expires_at <= datetime.now(UTC)
    ):
        provider_state = "failed"
    return ProviderLifecycle(
        provider_state,
        provider_status,
        expires_at,
        failure_provider_code,
        payment_verified,
        provider_id or None,
    )


async def refresh_hosted_payment_status(
    session: AsyncSession,
    payment: Payment,
    service: Any,
    *,
    expiration_grace_seconds: int = 30,
) -> Any:
    """Reconcile a pending hosted checkout against its provider's read API."""

    payment_snapshot = detached_payment_snapshot(payment)
    payment_id = int(payment_snapshot.payment_id)
    provider = _normalized(payment_snapshot.provider)

    if provider in {"wata", "wata_crypto"} and hasattr(service, "refresh_payment_status"):
        return await service.refresh_payment_status(session, payment_snapshot)

    lifecycle = await _inspect_provider_payment(service, payment_snapshot)
    if lifecycle.state == "succeeded":
        if not lifecycle.payment_verified:
            logger.error(
                "Provider %s reported payment %s succeeded without matching monetary data",
                provider,
                payment_id,
            )
        else:
            provider_id = (
                lifecycle.provider_payment_id
                or str(payment_snapshot.provider_payment_id or "").strip()
                or None
            )
            claimed = await payment_dal.claim_payment_finalization(
                session,
                payment_id,
                provider_payment_id=provider_id,
            )
            if claimed is None:
                return (
                    await payment_dal.get_payment_by_db_id(session, payment_id, fresh=True)
                    or payment_snapshot
                )
            sale_mode = str(claimed.sale_mode or "").strip() or (
                "traffic" if service.settings.traffic_sale_mode else "subscription"
            )
            units = payment_units_for_activation(claimed, sale_mode)
            outcome = await finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=service.bot,
                    settings=service.settings,
                    i18n=service.i18n,
                    session=session,
                    subscription_service=service.subscription_service,
                    referral_service=service.referral_service,
                    payment=claimed,
                    user_id=int(claimed.user_id),
                    amount=float(claimed.amount),
                    currency=str(claimed.currency),
                    sale_mode=sale_mode,
                    months=units,
                    traffic_amount=float(units),
                    provider_subscription=provider,
                    provider_notification=provider,
                    db_user=getattr(claimed, "user", None),
                    log_prefix=f"{provider} reconciliation",
                )
            )
            if outcome is not None:
                return (
                    await payment_dal.get_payment_by_db_id(session, payment_id, fresh=True)
                    or claimed
                )
            return (
                await payment_dal.get_payment_by_db_id(session, payment_id, fresh=True) or claimed
            )
    expires_at = lifecycle.checkout_expires_at or getattr(
        payment_snapshot,
        "checkout_expires_at",
        None,
    )
    if provider == "pally" and expires_at is None:
        expires_at = _pally_checkout_expiration(payment_snapshot, service)
    expired_pending = bool(
        lifecycle.state == "pending"
        and expires_at is not None
        and expires_at + timedelta(seconds=max(0, expiration_grace_seconds)) <= datetime.now(UTC)
    )
    if expired_pending:
        # A provider can briefly return a stale pending state at its boundary.
        # Do not release the promo until the provider itself reports terminal.
        logger.info(
            "Provider %s still reports payment %s pending after checkout expiry",
            provider,
            payment_id,
        )

    can_cancel_pending = bool(
        lifecycle.state == "pending"
        and hasattr(service, "cancel_pending_bill")
        and (expired_pending or lifecycle.provider_status == "new")
    )
    if can_cancel_pending:
        superseding_payment = None
        if not expired_pending:
            superseding_payment = (
                await payment_checkout_dal.find_later_equivalent_succeeded_payment(
                    session,
                    payment_snapshot,
                )
            )
        if expired_pending or superseding_payment is not None:
            superseding_payment_id = (
                int(superseding_payment.payment_id) if superseding_payment is not None else None
            )
            await session.rollback()
            canceled, _cancel_response = await service.cancel_pending_bill(
                str(payment_snapshot.provider_payment_id or "")
            )
            if canceled:
                expiration_reason = f"checkout_ttl_{getattr(service, 'ttl_seconds', 0)}s"
                updated, _transitioned = await payment_dal.transition_provider_payment_to_terminal(
                    session,
                    payment_id,
                    str(payment_snapshot.provider_payment_id or payment_id),
                    "canceled",
                    failure_kind=("checkout_expired" if expired_pending else "superseded_checkout"),
                    provider_cancellation_party="merchant",
                    provider_cancellation_reason=(
                        expiration_reason
                        if expired_pending
                        else f"superseded_by_payment_{superseding_payment_id}"
                    ),
                    suppress_failure_notification=not expired_pending,
                )
                await session.commit()
                logger.info(
                    "Canceled %s payment %s (%s).",
                    provider,
                    payment_id,
                    "checkout expired"
                    if expired_pending
                    else f"superseded by payment {superseding_payment_id}",
                )
                return (
                    await payment_dal.get_payment_by_db_id(session, payment_id, fresh=True)
                    or updated
                    or payment_snapshot
                )
            logger.warning(
                "Provider %s did not cancel payment %s (%s); checkout reservations stay held.",
                provider,
                payment_id,
                "checkout expired"
                if expired_pending
                else f"superseded by payment {superseding_payment_id}",
            )

    locally_expired = bool(
        provider in _EXPIRY_ONLY_PROVIDER_KEYS
        and lifecycle.state == "unknown"
        and expires_at is not None
        and expires_at + timedelta(seconds=max(300, expiration_grace_seconds)) <= datetime.now(UTC)
    )
    if lifecycle.state == "failed" or locally_expired:
        provider_id = str(payment_snapshot.provider_payment_id or payment_id)
        if provider == "pally" and lifecycle.failure_provider_code:
            logger.warning(
                "metric payment_provider_failure_total=1 provider=pally failure_code=%s "
                "payment_id=%s",
                lifecycle.failure_provider_code,
                payment_id,
            )
        updated, transitioned = await payment_dal.transition_provider_payment_to_terminal(
            session,
            payment_id,
            provider_id,
            "failed",
            failure_kind="provider_payment_failed",
            failure_provider_code=(
                lifecycle.failure_provider_code or lifecycle.provider_status or None
            ),
        )
        await session.commit()
        if updated is None:
            return payment_snapshot
        if transitioned:
            await notify_user_payment_failed(
                bot=service.bot,
                settings=service.settings,
                i18n=service.i18n,
                session=session,
                payment=updated,
            )
        return await payment_dal.get_payment_by_db_id(session, payment_id, fresh=True) or updated

    checked = await payment_reconciliation_dal.mark_provider_payment_checked(
        session,
        payment_id,
        checkout_expires_at=expires_at,
    )
    await session.commit()
    return checked or payment_snapshot
