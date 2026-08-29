from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.shared.checkout_expiration import resolve_checkout_expiration
from bot.payment_providers.shared.reconciliation import (
    _inspect_provider_payment,
    refresh_hosted_payment_status,
    supersede_earlier_pending_hosted_checkouts,
)
from db.dal import payment_checkout_dal, payment_dal, payment_reconciliation_dal


def _payment(provider: str, *, provider_payment_id: str = "provider-1") -> SimpleNamespace:
    return SimpleNamespace(
        payment_id=17,
        user_id=42,
        amount=199.0,
        currency="RUB",
        provider=provider,
        provider_payment_id=provider_payment_id,
        yookassa_payment_id=None,
        status=f"pending_{provider}",
        sale_mode="subscription@standard",
        subscription_duration_months=1,
        checkout_expires_at=None,
        created_at=datetime.now(UTC),
    )


def test_confirmed_platega_success_is_finalized_after_monetary_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("platega")
    succeeded_payment = SimpleNamespace(**{**vars(payment), "status": "succeeded"})
    service = SimpleNamespace(
        bot=object(),
        settings=SimpleNamespace(traffic_sale_mode=False),
        i18n=object(),
        subscription_service=object(),
        referral_service=object(),
        get_transaction=AsyncMock(
            return_value=(
                True,
                {
                    "id": "provider-1",
                    "payload": json.dumps({"payment_db_id": "17"}),
                    "status": "CONFIRMED",
                    "paymentDetails": {"amount": 205.0, "currency": "RUB"},
                },
            )
        ),
    )
    claim = AsyncMock(return_value=payment)
    finalize = AsyncMock(return_value=SimpleNamespace())
    reload_payment = AsyncMock(return_value=succeeded_payment)
    mark_checked = AsyncMock()
    monkeypatch.setattr(payment_dal, "claim_payment_finalization", claim)
    monkeypatch.setattr(payment_dal, "get_payment_by_db_id", reload_payment)
    monkeypatch.setattr(
        "bot.payment_providers.shared.reconciliation.finalize_successful_payment",
        finalize,
    )
    monkeypatch.setattr(
        payment_reconciliation_dal,
        "mark_provider_payment_checked",
        mark_checked,
    )
    session = SimpleNamespace()

    result = asyncio.run(refresh_hosted_payment_status(session, payment, service))

    assert result.status == "succeeded"
    claim.assert_awaited_once_with(session, 17, provider_payment_id="provider-1")
    finalize_call = finalize.await_args
    assert finalize_call is not None
    success_request = finalize_call.args[0]
    assert success_request.payment is payment
    assert success_request.provider_subscription == "platega"
    assert success_request.sale_mode == "subscription@standard"
    assert success_request.months == 1
    mark_checked.assert_not_awaited()


def test_success_with_mismatched_amount_is_not_finalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("platega")
    service = SimpleNamespace(
        get_transaction=AsyncMock(
            return_value=(
                True,
                {
                    "id": "provider-1",
                    "payload": json.dumps({"payment_db_id": "17"}),
                    "status": "CONFIRMED",
                    "amount": 1.0,
                    "currency": "RUB",
                },
            )
        )
    )
    claim = AsyncMock()
    mark_checked = AsyncMock(return_value=payment)
    monkeypatch.setattr(payment_dal, "claim_payment_finalization", claim)
    monkeypatch.setattr(
        payment_reconciliation_dal,
        "mark_provider_payment_checked",
        mark_checked,
    )
    session = SimpleNamespace(commit=AsyncMock())

    result = asyncio.run(refresh_hosted_payment_status(session, payment, service))

    assert result.status == "pending_platega"
    claim.assert_not_awaited()
    mark_checked.assert_awaited_once()


def test_cloudpayments_recovery_resolves_remote_id_from_local_invoice() -> None:
    payment = _payment("cloudpayments", provider_payment_id="")
    service = SimpleNamespace(
        find_payment=AsyncMock(
            return_value=(
                True,
                {
                    "InvoiceId": "17",
                    "TransactionId": "cp-9001",
                    "Status": "Completed",
                    "Amount": 199.0,
                    "Currency": "RUB",
                },
            )
        )
    )

    lifecycle = asyncio.run(_inspect_provider_payment(service, payment))

    assert lifecycle.state == "succeeded"
    assert lifecycle.payment_verified is True
    assert lifecycle.provider_payment_id == "cp-9001"


def test_resolve_checkout_expiration_supports_provider_timestamp_shapes() -> None:
    expected = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)

    payload = {"result": {"expirationDateTime": expected.isoformat()}}
    assert resolve_checkout_expiration(payload) == expected
    assert resolve_checkout_expiration({"expires_at": int(expected.timestamp())}) == expected
    assert resolve_checkout_expiration({"expiredAt": int(expected.timestamp() * 1000)}) == expected


def test_resolve_checkout_expiration_uses_only_an_exact_creation_ttl() -> None:
    started_at = datetime(2030, 1, 1, tzinfo=UTC)

    assert resolve_checkout_expiration({}, now=started_at) is None
    assert resolve_checkout_expiration(
        {},
        fallback_ttl_seconds=600,
        now=started_at,
    ) == started_at + timedelta(minutes=10)


@pytest.mark.parametrize(
    ("provider", "service", "expected_status"),
    [
        (
            "oxapay",
            SimpleNamespace(
                get_payment_info=AsyncMock(
                    return_value=(
                        True,
                        {
                            "track_id": "provider-1",
                            "order_id": "17",
                            "status": "expired",
                        },
                    )
                )
            ),
            "expired",
        ),
        (
            "heleket",
            SimpleNamespace(
                get_payment_info=AsyncMock(
                    return_value=(
                        True,
                        {
                            "uuid": "provider-1",
                            "order_id": "17",
                            "status": "cancel",
                            "is_final": True,
                        },
                    )
                )
            ),
            "cancel",
        ),
        (
            "platega_sbp",
            SimpleNamespace(
                get_transaction=AsyncMock(
                    return_value=(
                        True,
                        {
                            "id": "provider-1",
                            "payload": json.dumps({"payment_db_id": "17"}),
                            "status": "CANCELED",
                        },
                    )
                )
            ),
            "canceled",
        ),
        (
            "lava",
            SimpleNamespace(
                get_invoice_status=AsyncMock(
                    return_value=(
                        True,
                        {
                            "id": "provider-1",
                            "order_id": "17",
                            "status": "expired",
                        },
                    )
                )
            ),
            "expired",
        ),
        (
            "paykilla",
            SimpleNamespace(
                get_invoice_details=AsyncMock(
                    return_value=(
                        True,
                        {
                            "id": "provider-1",
                            "clientOrderId": "17",
                            "status": "INVOICE_EXPIRED",
                        },
                    )
                )
            ),
            "invoice_expired",
        ),
        (
            "pally",
            SimpleNamespace(
                get_bill_status=AsyncMock(
                    return_value=(
                        True,
                        {
                            "bill_id": "provider-1",
                            "order_id": "17",
                            "status": "FAIL",
                        },
                    )
                )
            ),
            "fail",
        ),
        (
            "severpay",
            SimpleNamespace(
                get_payment=AsyncMock(
                    return_value=(
                        True,
                        {
                            "uid": "provider-1",
                            "order_id": "17",
                            "status": "decline",
                        },
                    )
                )
            ),
            "decline",
        ),
        (
            "stripe",
            SimpleNamespace(
                retrieve_checkout_session=AsyncMock(
                    return_value=(
                        True,
                        {
                            "id": "provider-1",
                            "metadata": {"payment_db_id": "17"},
                            "status": "expired",
                            "expires_at": 1_893_542_400,
                        },
                    )
                )
            ),
            "expired",
        ),
        (
            "cryptopay",
            SimpleNamespace(
                get_invoice=AsyncMock(
                    return_value=SimpleNamespace(
                        invoice_id="provider-1",
                        payload=json.dumps({"payment_db_id": "17"}),
                        status="expired",
                        expiration_date="2030-01-01T00:00:00Z",
                    )
                )
            ),
            "expired",
        ),
    ],
)
def test_provider_terminal_statuses_are_classified_as_failed(
    provider: str,
    service: SimpleNamespace,
    expected_status: str,
) -> None:
    lifecycle = asyncio.run(_inspect_provider_payment(service, _payment(provider)))

    assert lifecycle.state == "failed"
    assert lifecycle.provider_status == expected_status


def test_freekassa_pending_order_stays_reusable() -> None:
    service = SimpleNamespace(
        get_orders=AsyncMock(
            side_effect=[
                (True, {"orders": []}),
                (
                    True,
                    {
                        "orders": [
                            {
                                "merchant_order_id": "17",
                                "status": 0,
                            }
                        ]
                    },
                ),
            ]
        )
    )

    lifecycle = asyncio.run(_inspect_provider_payment(service, _payment("freekassa")))

    assert lifecycle.state == "pending"


def test_oxapay_paid_invoice_is_monetarily_verified() -> None:
    service = SimpleNamespace(
        get_payment_info=AsyncMock(
            return_value=(
                True,
                {
                    "track_id": "provider-1",
                    "order_id": "17",
                    "status": "paid",
                    "amount": 199,
                    "currency": "RUB",
                    "expired_at": 1_893_542_400,
                },
            )
        )
    )

    lifecycle = asyncio.run(_inspect_provider_payment(service, _payment("oxapay")))

    assert lifecycle.state == "succeeded"
    assert lifecycle.provider_status == "paid"
    assert lifecycle.payment_verified


def test_confirmed_terminal_failure_releases_checkout_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("lava")
    failed_values = vars(payment).copy()
    failed_values["status"] = "failed"
    failed_payment = SimpleNamespace(**failed_values)
    service = SimpleNamespace(
        bot=object(),
        settings=object(),
        i18n=object(),
        get_invoice_status=AsyncMock(
            return_value=(
                True,
                {
                    "id": "provider-1",
                    "order_id": "17",
                    "status": "expired",
                },
            )
        ),
    )
    transition = AsyncMock(return_value=(failed_payment, True))
    reload_payment = AsyncMock(return_value=failed_payment)
    notify = AsyncMock()
    monkeypatch.setattr(payment_dal, "transition_provider_payment_to_terminal", transition)
    monkeypatch.setattr(payment_dal, "get_payment_by_db_id", reload_payment)
    monkeypatch.setattr(
        "bot.payment_providers.shared.reconciliation.notify_user_payment_failed",
        notify,
    )
    session = SimpleNamespace(commit=AsyncMock())

    result = asyncio.run(refresh_hosted_payment_status(session, payment, service))

    assert result.status == "failed"
    transition.assert_awaited_once_with(
        session,
        17,
        "provider-1",
        "failed",
        failure_kind="provider_payment_failed",
        failure_provider_code="expired",
    )
    notify.assert_awaited_once()


def test_expired_local_timestamp_does_not_override_provider_pending_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("lava")
    payment.checkout_expires_at = datetime.now(UTC) - timedelta(hours=1)
    service = SimpleNamespace(
        get_invoice_status=AsyncMock(
            return_value=(
                True,
                {
                    "id": "provider-1",
                    "order_id": "17",
                    "status": "pending",
                },
            )
        )
    )
    mark_checked = AsyncMock(return_value=payment)
    transition = AsyncMock()
    monkeypatch.setattr(
        payment_reconciliation_dal,
        "mark_provider_payment_checked",
        mark_checked,
    )
    monkeypatch.setattr(payment_dal, "transition_provider_payment_to_terminal", transition)
    session = SimpleNamespace(commit=AsyncMock())

    result = asyncio.run(refresh_hosted_payment_status(session, payment, service))

    assert result.status == "pending_lava"
    transition.assert_not_awaited()
    mark_checked.assert_awaited_once()


def test_pally_new_bill_is_canceled_after_equivalent_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("pally")
    payment.created_at = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
    payment.sale_mode = "subscription@standard"
    payment.subscription_duration_months = 1
    service = SimpleNamespace(
        get_bill_status=AsyncMock(
            return_value=(
                True,
                {"id": "provider-1", "order_id": "17", "status": "NEW"},
            )
        ),
        cancel_pending_bill=AsyncMock(return_value=(True, {"activity": False})),
    )
    successful = SimpleNamespace(payment_id=18)
    canceled = SimpleNamespace(**{**vars(payment), "status": "canceled"})
    find_success = AsyncMock(return_value=successful)
    transition = AsyncMock(return_value=(canceled, True))
    reload_payment = AsyncMock(return_value=canceled)
    monkeypatch.setattr(
        payment_checkout_dal,
        "find_later_equivalent_succeeded_payment",
        find_success,
    )
    monkeypatch.setattr(payment_dal, "transition_provider_payment_to_terminal", transition)
    monkeypatch.setattr(payment_dal, "get_payment_by_db_id", reload_payment)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    result = asyncio.run(refresh_hosted_payment_status(session, payment, service))

    assert result.status == "canceled"
    service.cancel_pending_bill.assert_awaited_once_with("provider-1")
    transition.assert_awaited_once_with(
        session,
        17,
        "provider-1",
        "canceled",
        failure_kind="superseded_checkout",
        provider_cancellation_party="merchant",
        provider_cancellation_reason="superseded_by_payment_18",
        suppress_failure_notification=True,
    )


def test_new_pally_checkout_cancels_older_link_in_same_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = _payment("pally", provider_payment_id="provider-old")
    replacement = _payment("pally", provider_payment_id="provider-new")
    replacement.payment_id = 18
    find_earlier = AsyncMock(return_value=[previous])
    transition = AsyncMock(return_value=(previous, True))
    service = SimpleNamespace(
        cancel_pending_bill=AsyncMock(return_value=(True, {"activity": False}))
    )
    monkeypatch.setattr(
        payment_checkout_dal,
        "list_earlier_pending_provider_payments_for_checkout_scope",
        find_earlier,
    )
    monkeypatch.setattr(payment_dal, "transition_provider_payment_to_terminal", transition)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    asyncio.run(
        supersede_earlier_pending_hosted_checkouts(
            session,
            replacement,
            service,
            pending_status="pending_pally",
        )
    )

    find_earlier.assert_awaited_once_with(
        session,
        replacement,
        pending_status="pending_pally",
    )
    service.cancel_pending_bill.assert_awaited_once_with("provider-old")
    transition.assert_awaited_once_with(
        session,
        17,
        "provider-old",
        "canceled",
        failure_kind="superseded_checkout",
        provider_cancellation_party="merchant",
        provider_cancellation_reason="superseded_by_payment_18",
        suppress_failure_notification=True,
    )
    session.commit.assert_awaited_once()


def test_pally_status_success_is_finalized_after_monetary_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("pally")
    succeeded_payment = SimpleNamespace(**{**vars(payment), "status": "succeeded"})
    service = SimpleNamespace(
        bot=object(),
        settings=SimpleNamespace(traffic_sale_mode=False),
        config=SimpleNamespace(PAYER_PAYS_COMMISSION=False),
        i18n=object(),
        subscription_service=object(),
        referral_service=object(),
        get_bill_status=AsyncMock(
            return_value=(
                True,
                {
                    "id": "provider-1",
                    "order_id": "17",
                    "status": "SUCCESS",
                    "amount": 199.0,
                    "currency_in": "RUB",
                },
            )
        ),
    )
    claim = AsyncMock(return_value=payment)
    finalize = AsyncMock(return_value=SimpleNamespace())
    reload_payment = AsyncMock(return_value=succeeded_payment)
    mark_checked = AsyncMock()
    monkeypatch.setattr(payment_dal, "claim_payment_finalization", claim)
    monkeypatch.setattr(payment_dal, "get_payment_by_db_id", reload_payment)
    monkeypatch.setattr(
        "bot.payment_providers.shared.reconciliation.finalize_successful_payment",
        finalize,
    )
    monkeypatch.setattr(
        payment_reconciliation_dal,
        "mark_provider_payment_checked",
        mark_checked,
    )
    session = SimpleNamespace()

    result = asyncio.run(refresh_hosted_payment_status(session, payment, service))

    assert result.status == "succeeded"
    claim.assert_awaited_once_with(session, 17, provider_payment_id="provider-1")
    finalize.assert_awaited_once()
    mark_checked.assert_not_awaited()


def test_pally_status_success_with_mismatched_amount_is_not_finalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("pally")
    service = SimpleNamespace(
        config=SimpleNamespace(PAYER_PAYS_COMMISSION=False),
        get_bill_status=AsyncMock(
            return_value=(
                True,
                {
                    "id": "provider-1",
                    "order_id": "17",
                    "status": "SUCCESS",
                    "amount": 1.0,
                    "currency_in": "RUB",
                },
            )
        ),
    )
    claim = AsyncMock()
    mark_checked = AsyncMock(return_value=payment)
    monkeypatch.setattr(payment_dal, "claim_payment_finalization", claim)
    monkeypatch.setattr(
        payment_reconciliation_dal,
        "mark_provider_payment_checked",
        mark_checked,
    )
    session = SimpleNamespace(commit=AsyncMock())

    result = asyncio.run(refresh_hosted_payment_status(session, payment, service))

    assert result.status == "pending_pally"
    claim.assert_not_awaited()
    mark_checked.assert_awaited_once()


def test_pally_failure_records_processing_error_code() -> None:
    service = SimpleNamespace(
        get_bill_status=AsyncMock(
            return_value=(
                True,
                {"id": "provider-1", "order_id": "17", "status": "FAIL"},
            )
        ),
        get_bill_payments=AsyncMock(
            return_value=(
                True,
                {"data": [{"status": "FAIL", "error_code": 666}]},
            )
        ),
    )

    lifecycle = asyncio.run(_inspect_provider_payment(service, _payment("pally")))

    assert lifecycle.state == "failed"
    assert lifecycle.failure_provider_code == "666"


def test_expired_pally_bill_is_canceled_before_checkout_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("pally")
    payment.created_at = datetime.now(UTC) - timedelta(hours=1)
    service = SimpleNamespace(
        ttl_seconds=1800,
        get_bill_status=AsyncMock(
            return_value=(
                True,
                {"id": "provider-1", "order_id": "17", "status": "NEW", "active": True},
            )
        ),
        cancel_pending_bill=AsyncMock(return_value=(True, {"activity": False})),
    )
    canceled = SimpleNamespace(**{**vars(payment), "status": "canceled"})
    transition = AsyncMock(return_value=(canceled, True))
    reload_payment = AsyncMock(return_value=canceled)
    find_success = AsyncMock()
    mark_checked = AsyncMock()
    monkeypatch.setattr(
        payment_checkout_dal,
        "find_later_equivalent_succeeded_payment",
        find_success,
    )
    monkeypatch.setattr(payment_dal, "transition_provider_payment_to_terminal", transition)
    monkeypatch.setattr(payment_dal, "get_payment_by_db_id", reload_payment)
    monkeypatch.setattr(
        payment_reconciliation_dal,
        "mark_provider_payment_checked",
        mark_checked,
    )
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    result = asyncio.run(
        refresh_hosted_payment_status(
            session,
            payment,
            service,
            expiration_grace_seconds=0,
        )
    )

    assert result.status == "canceled"
    service.cancel_pending_bill.assert_awaited_once_with("provider-1")
    find_success.assert_not_awaited()
    transition.assert_awaited_once_with(
        session,
        17,
        "provider-1",
        "canceled",
        failure_kind="checkout_expired",
        provider_cancellation_party="merchant",
        provider_cancellation_reason="checkout_ttl_1800s",
        suppress_failure_notification=False,
    )
    mark_checked.assert_not_awaited()


def test_pally_cancel_failure_keeps_checkout_reservations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment("pally")
    payment.created_at = datetime.now(UTC) - timedelta(hours=1)
    service = SimpleNamespace(
        ttl_seconds=1800,
        get_bill_status=AsyncMock(
            return_value=(
                True,
                {"id": "provider-1", "order_id": "17", "status": "NEW", "active": True},
            )
        ),
        cancel_pending_bill=AsyncMock(return_value=(False, {"message": "provider_error"})),
    )
    transition = AsyncMock()
    mark_checked = AsyncMock(return_value=payment)
    monkeypatch.setattr(payment_dal, "transition_provider_payment_to_terminal", transition)
    monkeypatch.setattr(
        payment_reconciliation_dal,
        "mark_provider_payment_checked",
        mark_checked,
    )
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    result = asyncio.run(
        refresh_hosted_payment_status(
            session,
            payment,
            service,
            expiration_grace_seconds=0,
        )
    )

    assert result.status == "pending_pally"
    transition.assert_not_awaited()
    mark_checked.assert_awaited_once_with(
        session,
        17,
        checkout_expires_at=payment.created_at + timedelta(seconds=1800),
    )
