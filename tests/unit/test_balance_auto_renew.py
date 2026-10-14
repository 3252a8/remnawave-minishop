"""Balance renewals require explicit consent, a full quote and one funding source."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from bot.app.web.webapp import billing_payments
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from bot.payment_providers import get_provider_spec, provider_supports_recurring
from bot.payment_providers.shared.durable_recurring import (
    DurableRecurringDispatch,
    DurableRecurringPreparation,
)
from bot.payment_providers.shared.recurring import BalancePaymentMethod, RecurringChargeContext
from bot.services import balance_recurring
from bot.services.balance_recurring import BalanceRecurringService, balance_recurring_available
from bot.services.partner_checkout_balance import PartnerCheckoutBalanceAllocation
from bot.services.user_balance_service import UserBalanceAllocation
from config.settings import Settings
from db.models import Payment


def _settings(**overrides) -> Settings:
    return cast(
        Settings,
        SimpleNamespace(
            USER_BALANCE_RECURRING_ENABLED=True,
            traffic_sale_mode=False,
            balance_settings=SimpleNamespace(enabled=True, currency="RUB"),
            partner_settings=SimpleNamespace(enabled=True, balance_payment_enabled=True),
            AUTO_RENEW_MAX_TRANSPORT_REPLAYS=4,
            AUTO_RENEW_MAX_FINANCIAL_ATTEMPTS=2,
            AUTO_RENEW_RETRY_ENABLED=True,
            AUTO_RENEW_RETRY_GRACE_HOURS=0,
            DEFAULT_CURRENCY_SYMBOL="RUB",
            DEFAULT_LANGUAGE="en",
            MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
            **overrides,
        ),
    )


def test_balance_consent_defaults_off_and_internal_sources_are_not_provider_buttons():
    assert WebAppPaymentCreatePayload().balance_auto_renew is False
    assert Settings(_env_file=None).USER_BALANCE_RECURRING_ENABLED is False
    for provider in ("user_balance", "partner_balance"):
        assert provider_supports_recurring(provider)
        assert get_provider_spec(provider) is None


def test_partner_only_recurrence_requires_its_own_payment_permission():
    settings = _settings()
    settings.balance_settings.enabled = False
    assert not balance_recurring_available(settings, "user_balance")
    assert balance_recurring_available(settings, "partner_balance")
    settings.partner_settings.balance_payment_enabled = False
    assert not balance_recurring_available(settings, "partner_balance")


@pytest.mark.parametrize("source", ["user", "partner"])
@pytest.mark.parametrize("full", [True, False])
def test_checkout_requires_full_current_quote_and_persists_consent(source, full):
    asyncio.run(_checkout(source, full))


async def _checkout(source, full):
    allocation = UserBalanceAllocation(
        user_id=42,
        currency="RUB",
        currency_scale=2,
        checkout_total_minor=70000,
        applied_minor=70000 if full else 50000,
    )
    with (
        patch.object(billing_payments, "get_settings", return_value=_settings()),
        patch.object(billing_payments, "get_i18n", return_value=None),
        patch.object(
            billing_payments.subscription_dal,
            "get_active_subscription_by_user_id",
            AsyncMock(return_value=None),
        ),
        patch.object(
            billing_payments, "allocate_checkout_balance", AsyncMock(return_value=allocation)
        ),
        patch.object(
            billing_payments,
            "create_fully_balance_funded_payment",
            AsyncMock(return_value=billing_payments.web.json_response({"ok": True})),
        ) as finalize,
    ):
        response = await billing_payments._create_subscription_payment(
            request=SimpleNamespace(app={}),
            session=AsyncMock(),
            user_id=42,
            method="balance",
            months=3,
            price=700,
            stars_price=None,
            lang="en",
            currency="RUB",
            sale_mode="subscription@standard",
            balance_source=source,
            balance_auto_renew=True,
            entitlement_context_snapshot="frozen-subscription",
        )
    if full:
        assert response.status == 200
        assert finalize.await_args.kwargs["balance_auto_renew"] is True
    else:
        assert response.status == 409
        assert json.loads(response.text)["error"] == "balance_auto_renew_requires_full_payment"
        finalize.assert_not_awaited()


@pytest.mark.parametrize(
    "mode", ["subscription|gift", "trial", "topup@standard", "hwid_devices@standard"]
)
def test_forged_balance_consent_is_rejected_for_non_subscription_orders(mode):
    asyncio.run(_forged_consent(mode))


async def _forged_consent(mode):
    with (
        patch.object(billing_payments, "get_settings", return_value=_settings()),
        patch.object(
            billing_payments.subscription_dal,
            "get_active_subscription_by_user_id",
            AsyncMock(return_value=None),
        ),
        patch.object(billing_payments, "allocate_checkout_balance", AsyncMock()) as allocate,
    ):
        response = await billing_payments._create_subscription_payment(
            request=SimpleNamespace(app={}),
            session=AsyncMock(),
            user_id=42,
            method="balance",
            months=1,
            price=199,
            stars_price=None,
            lang="en",
            sale_mode=mode,
            balance_source="user",
            balance_auto_renew=True,
        )
    assert response.status == 409
    allocate.assert_not_awaited()


def _charge_context(provider):
    return RecurringChargeContext(
        session=AsyncMock(),
        user_id=42,
        subscription_id=7,
        saved_method=BalancePaymentMethod(user_id=42, provider=provider),
        amount=199,
        currency="RUB",
        months=1,
        duration_days=30,
        sale_mode="subscription@standard|days:30",
        description="Renewal",
        idempotence_key="balance-cycle-7",
        renewal_cycle_end=datetime.now(UTC) + timedelta(days=1),
        consent_version=3,
        entitlement_context_snapshot="frozen-entitlement",
        checkout_bundle_snapshot='{"version":3,"items":[{"kind":"traffic"}]}',
    )


def _dispatch(context, provider):
    payment = Payment(
        payment_id=91,
        user_id=42,
        amount=context.amount,
        currency=context.currency,
        status="pending",
        provider=provider,
        is_auto_renew=True,
        checkout_bundle_snapshot=context.checkout_bundle_snapshot,
    )
    return DurableRecurringDispatch(
        cycle_id=11,
        payment=payment,
        payment_id=91,
        request_id="balance-cycle-7",
        attempt_number=1,
        transport_replays=0,
        fallback_retry_at=datetime.now(UTC),
    )


def _service(settings, provider):
    return BalanceRecurringService(
        settings,
        provider=provider,
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
        bot=None,
        i18n=SimpleNamespace(),
    )


@pytest.mark.parametrize("provider", ["user_balance", "partner_balance"])
def test_renewal_debits_only_selected_balance_and_preserves_flexible_terms(provider):
    asyncio.run(_charge(provider, full=True))


@pytest.mark.parametrize("provider", ["user_balance", "partner_balance"])
def test_insufficient_selected_balance_never_falls_back_and_schedules_capped_retry(provider):
    asyncio.run(_charge(provider, full=False))


async def _charge(provider, *, full, already_reserved=False, consent_allowed=True):
    context = _charge_context(provider)
    dispatch = _dispatch(context, provider)
    if already_reserved:
        dispatch.payment.status = "succeeded_pending_finalization"
    applied_minor = 19900 if full else 9900
    allocation = (
        UserBalanceAllocation(
            user_id=42,
            currency="RUB",
            currency_scale=2,
            checkout_total_minor=19900,
            applied_minor=applied_minor,
        )
        if provider == "user_balance"
        else PartnerCheckoutBalanceAllocation(
            partner_id=8,
            currency="RUB",
            currency_scale=2,
            checkout_total_minor=19900,
            applied_minor=applied_minor,
        )
    )
    user_quote = AsyncMock(return_value=allocation)
    partner_quote = AsyncMock(return_value=allocation)

    async def finalized(request):
        request.payment.status = "succeeded"
        return SimpleNamespace()

    with (
        patch.object(
            balance_recurring,
            "prepare_durable_recurring_charge",
            AsyncMock(return_value=DurableRecurringPreparation(dispatch=dispatch)),
        ),
        patch.object(
            balance_recurring.payment_dal,
            "get_payment_by_db_id_for_update",
            AsyncMock(return_value=dispatch.payment),
        ),
        patch.object(
            balance_recurring.payment_dal,
            "get_payment_by_db_id",
            AsyncMock(return_value=dispatch.payment),
        ),
        patch.object(
            balance_recurring.user_dal,
            "lock_user_by_id",
            AsyncMock(return_value=SimpleNamespace(is_banned=False)),
        ),
        patch.object(balance_recurring.UserBalanceService, "quote", user_quote),
        patch.object(balance_recurring.PartnerCheckoutBalanceService, "quote", partner_quote),
        patch.object(balance_recurring.UserBalanceService, "reserve", AsyncMock()) as reserve_user,
        patch.object(
            balance_recurring.PartnerCheckoutBalanceService, "reserve", AsyncMock()
        ) as reserve_partner,
        patch.object(
            balance_recurring, "finalize_successful_payment", AsyncMock(side_effect=finalized)
        ) as finalize,
        patch.object(balance_recurring.payment_dal, "update_payment_status_by_db_id", AsyncMock()),
        patch.object(balance_recurring.auto_renew_dal, "mark_request_failure", AsyncMock()),
        patch.object(
            balance_recurring.auto_renew_dal,
            "get_cycle",
            AsyncMock(return_value=SimpleNamespace(financial_attempts=1)),
        ),
        patch.object(
            balance_recurring.auto_renew_dal, "schedule_financial_retry", AsyncMock()
        ) as retry,
        patch.object(balance_recurring.auto_renew_dal, "stop_cycle", AsyncMock()),
        patch.object(
            balance_recurring.auto_renew_dal,
            "validate_dispatch_context_for_update",
            AsyncMock(return_value=consent_allowed),
        ),
        patch.object(
            balance_recurring.user_balance_dal,
            "get_ledger_entry_by_key",
            AsyncMock(
                side_effect=[SimpleNamespace(user_id=42, amount_minor=-19900, currency="RUB"), None]
            ),
        ),
        patch.object(
            balance_recurring.partner_dal,
            "get_ledger_entry_by_key",
            AsyncMock(
                side_effect=[
                    SimpleNamespace(partner_id=8, amount_minor=-19900, currency="RUB"),
                    None,
                ]
            ),
        ),
        patch.object(
            balance_recurring.partner_dal,
            "get_profile_by_user_id",
            AsyncMock(return_value=SimpleNamespace(partner_id=8, status="active")),
        ),
    ):
        result = await _service(_settings(), provider).charge_saved_payment_method(context)
    selected_quote = user_quote if provider == "user_balance" else partner_quote
    other_quote = partner_quote if provider == "user_balance" else user_quote
    if already_reserved:
        selected_quote.assert_not_awaited()
    else:
        selected_quote.assert_awaited_once()
    other_quote.assert_not_awaited()
    if not consent_allowed:
        assert not result.initiated and result.message == "consent_changed"
        finalize.assert_not_awaited()
    elif full:
        assert result.initiated and result.status == "succeeded"
        request = finalize.await_args.args[0]
        assert request.payment.balance_auto_renew is True
        assert request.payment.checkout_bundle_snapshot == context.checkout_bundle_snapshot
        assert request.provider_subscription == provider
        if already_reserved:
            reserve_user.assert_not_awaited()
            reserve_partner.assert_not_awaited()
        else:
            (reserve_user if provider == "user_balance" else reserve_partner).assert_awaited_once()
        (reserve_partner if provider == "user_balance" else reserve_user).assert_not_awaited()
    else:
        assert not result.initiated and result.retryable
        reserve_user.assert_not_awaited()
        reserve_partner.assert_not_awaited()
        finalize.assert_not_awaited()
        retry.assert_awaited_once()


@pytest.mark.parametrize("provider", ["user_balance", "partner_balance"])
def test_recovery_finishes_reserved_order_without_quoting_or_debiting_twice(provider):
    asyncio.run(_charge(provider, full=True, already_reserved=True))


def test_consent_revoked_after_reservation_prevents_activation():
    asyncio.run(_charge("user_balance", full=True, consent_allowed=False))


def test_financial_retry_cap_is_enforced_before_creating_another_payment():
    context = replace(
        _charge_context("user_balance"), auto_renew_cycle_id=11, retry_kind="financial"
    )
    with (
        patch.object(
            balance_recurring.auto_renew_dal,
            "get_cycle",
            AsyncMock(return_value=SimpleNamespace(financial_attempts=2)),
        ),
        patch.object(balance_recurring.auto_renew_dal, "stop_cycle", AsyncMock()) as stop,
        patch.object(balance_recurring, "prepare_durable_recurring_charge", AsyncMock()) as prepare,
    ):
        result = asyncio.run(
            _service(_settings(), "user_balance").charge_saved_payment_method(context)
        )
    assert not result.initiated and result.message == "financial_attempt_cap"
    stop.assert_awaited_once()
    prepare.assert_not_awaited()


@pytest.mark.parametrize("mode", ["trial", "subscription|gift", "topup", "hwid_devices"])
def test_renewal_service_rejects_forged_non_subscription_context(mode):
    context = replace(_charge_context("user_balance"), sale_mode=mode)
    with patch.object(
        balance_recurring, "prepare_durable_recurring_charge", AsyncMock()
    ) as prepare:
        result = asyncio.run(
            _service(_settings(), "user_balance").charge_saved_payment_method(context)
        )
    assert not result.initiated
    prepare.assert_not_awaited()


@pytest.mark.parametrize("provider", ["user_balance", "partner_balance"])
def test_active_balance_recurrence_blocks_standalone_addons(provider):
    subscription = SimpleNamespace(provider=provider, auto_renew_enabled=True)
    for mode in ("topup", "premium_topup", "hwid_devices", "traffic_package"):
        assert balance_recurring.balance_recurrence_blocks_purchase(subscription, mode)
    assert not balance_recurring.balance_recurrence_blocks_purchase(subscription, "subscription")
    subscription.auto_renew_enabled = False
    assert not balance_recurring.balance_recurrence_blocks_purchase(subscription, "topup")
