import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.shared import managed_mandates as runtime
from bot.payment_providers.shared.link_flow import CreatePaymentRequest


class Session:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    execute = AsyncMock()
    flush = AsyncMock()
    commit = AsyncMock()


def test_new_mandate_does_not_create_duplicate_schedule(monkeypatch):
    service = SimpleNamespace(
        async_session_factory=Session(), mandate_providers=("cryptomus_subscription",)
    )
    monkeypatch.setattr(
        runtime.provider_mandate_dal, "list_mandates", AsyncMock(return_value=[object()])
    )
    create = AsyncMock(side_effect=AssertionError("double billing schedule"))
    req = CreatePaymentRequest(
        payment=SimpleNamespace(payment_id=77),
        user_id=42,
        amount=150,
        currency="RUB",
        description="Subscription",
        months=1,
        sale_mode="subscription",
    )
    success, data = asyncio.run(
        runtime.create_managed_checkout(
            service, req, provider="cryptomus_subscription", period_days=30, create_remote=create
        )
    )
    assert not success and data["message"] == "active_provider_subscription_exists"
    create.assert_not_awaited()


@pytest.mark.parametrize(
    "owner,provider,amount,currency",
    [
        (99, "cryptomus_subscription", 150, "RUB"),
        (42, "other", 150, "RUB"),
        (42, "cryptomus_subscription", 1, "RUB"),
        (42, "cryptomus_subscription", 150, "USD"),
    ],
)
def test_charge_requires_frozen_owner_provider_and_quote(
    monkeypatch, owner, provider, amount, currency
):
    service = SimpleNamespace(async_session_factory=Session())
    record = SimpleNamespace(anchor_payment_id=77, user_id=42)
    anchor = SimpleNamespace(user_id=owner, provider=provider, amount=150, currency="RUB")
    monkeypatch.setattr(runtime.provider_mandate_dal, "get_mandate", AsyncMock(return_value=record))
    monkeypatch.setattr(runtime.payment_dal, "get_payment_by_db_id", AsyncMock(return_value=anchor))
    finalize = AsyncMock(side_effect=AssertionError("unmatched payment"))
    monkeypatch.setattr(runtime, "finalize_successful_payment", finalize)
    assert not asyncio.run(
        runtime.settle_managed_charge(
            service,
            provider="cryptomus_subscription",
            remote_id="mandate",
            charge_id="charge",
            amount=amount,
            currency=currency,
            occurred_at=datetime.now(UTC),
            remote_state="active",
        )
    )
    finalize.assert_not_awaited()


def test_duplicate_charge_uses_persisted_idempotency_key(monkeypatch):
    service = SimpleNamespace(async_session_factory=Session())
    record = SimpleNamespace(anchor_payment_id=77, user_id=42)
    anchor = SimpleNamespace(
        user_id=42, provider="cryptomus_subscription", amount=150, currency="RUB"
    )
    monkeypatch.setattr(runtime.provider_mandate_dal, "get_mandate", AsyncMock(return_value=record))
    monkeypatch.setattr(runtime.payment_dal, "get_payment_by_db_id", AsyncMock(return_value=anchor))
    lookup = AsyncMock(return_value=SimpleNamespace(status="succeeded"))
    monkeypatch.setattr(runtime.payment_dal, "get_payment_by_idempotence_key", lookup)
    claim = AsyncMock(side_effect=AssertionError("duplicate fulfillment"))
    monkeypatch.setattr(runtime.payment_dal, "claim_payment_finalization", claim)
    assert asyncio.run(
        runtime.settle_managed_charge(
            service,
            provider="cryptomus_subscription",
            remote_id="mandate",
            charge_id="charge",
            amount=150,
            currency="RUB",
            occurred_at=datetime.now(UTC),
            remote_state="active",
        )
    )
    assert lookup.call_args.args[1] == "mandate:cryptomus_subscription:mandate:charge"
    claim.assert_not_awaited()


def test_provider_timestamp_without_offset_is_moscow():
    from datetime import timedelta, timezone

    result = runtime.parse_charge_time(
        "2026-10-09 12:00:00", default_timezone=timezone(timedelta(hours=3))
    )
    assert result == datetime(2026, 10, 9, 9, tzinfo=UTC)


@pytest.mark.parametrize("initial_charge,finalized", [(None, True), ("first", True), (None, False)])
def test_first_and_later_cycles_use_frozen_order_and_retry_failed_activation(
    monkeypatch, initial_charge, finalized
):
    service = SimpleNamespace(
        async_session_factory=Session(),
        bot=None,
        settings=None,
        i18n=None,
        subscription_service=None,
        referral_service=None,
    )
    record = SimpleNamespace(
        anchor_payment_id=77,
        user_id=42,
        initial_charge_id=initial_charge,
        period_days=90,
        status="active",
        last_charge_at=datetime(2026, 9, 1, tzinfo=UTC).replace(tzinfo=None),
    )
    anchor = SimpleNamespace(
        payment_id=77,
        user_id=42,
        provider="cryptomus_subscription",
        amount=150,
        currency="RUB",
        description="Frozen quote",
        sale_mode="subscription",
        tariff_key="old_tariff",
        subscription_duration_months=3,
        subscription_terms_snapshot={"frozen": True},
        idempotence_key=None,
    )
    renewal = SimpleNamespace(payment_id=78)
    monkeypatch.setattr(runtime.provider_mandate_dal, "get_mandate", AsyncMock(return_value=record))
    monkeypatch.setattr(runtime.payment_dal, "get_payment_by_db_id", AsyncMock(return_value=anchor))
    monkeypatch.setattr(
        runtime.payment_dal, "get_payment_by_idempotence_key", AsyncMock(return_value=None)
    )
    create = AsyncMock(return_value=(renewal, True))
    monkeypatch.setattr(
        runtime.payment_dal, "create_or_get_payment_record_by_idempotence_key", create
    )
    claim = AsyncMock(return_value=anchor if initial_charge is None else renewal)
    monkeypatch.setattr(runtime.payment_dal, "claim_payment_finalization", claim)
    finalize = AsyncMock(return_value=object() if finalized else None)
    monkeypatch.setattr(runtime, "finalize_successful_payment", finalize)
    mirror = AsyncMock()
    monkeypatch.setattr(runtime, "mirror_auto_renew", mirror)
    assert (
        asyncio.run(
            runtime.settle_managed_charge(
                service,
                provider="cryptomus_subscription",
                remote_id="mandate",
                charge_id="second",
                amount=150,
                currency="RUB",
                occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
                remote_state="active",
            )
        )
        is finalized
    )
    request = finalize.call_args.args[0]
    assert request.amount == 150 and request.months == 3 and request.user_id == 42
    assert record.last_charge_at == datetime(2026, 10, 1, tzinfo=UTC)
    if initial_charge is None:
        create.assert_not_awaited()
        assert anchor.idempotence_key.endswith(":second")
        assert claim.call_args.kwargs["provider_payment_id"] == "mandate"
    else:
        frozen = create.call_args.args[1]
        assert frozen["subscription_duration_days"] == 90
        assert frozen["subscription_terms_snapshot"] == {"frozen": True}
        assert frozen["is_auto_renew"]
        assert claim.call_args.kwargs["provider_payment_id"] == "second"
    assert mirror.await_count == int(finalized)


def test_reconciliation_uses_bounded_round_robin_batches(monkeypatch):
    service = runtime.ManagedMandateMixin()
    service.async_session_factory = Session()
    service.mandate_providers = ("cryptomus_subscription",)
    batches = AsyncMock(
        side_effect=[
            [SimpleNamespace(mandate_id=1, provider="cryptomus_subscription", remote_id="first")],
            [SimpleNamespace(mandate_id=2, provider="cryptomus_subscription", remote_id="second")],
            [],
        ]
    )
    monkeypatch.setattr(runtime.provider_mandate_dal, "list_mandates", batches)
    reconcile = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "reconcile_remote_mandate", reconcile)
    for _ in range(3):
        asyncio.run(service.reconcile_recurring_payments())
    assert [call.kwargs["after_id"] for call in batches.call_args_list] == [0, 1, 2]
    assert service._mandate_cursor == 0
    assert reconcile.await_count == 2
