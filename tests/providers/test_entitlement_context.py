from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, patch

from bot.app.web.webapp import billing_payments
from bot.payment_providers.shared.callbacks import (
    PaymentCallbackParts,
    quote_hwid_callback_parts,
)
from bot.payment_providers.shared.entitlement_context import (
    EntitlementPreflightStatus,
    build_entitlement_context_snapshot,
    parse_entitlement_context_snapshot,
    preflight_payment_entitlement,
)
from bot.payment_providers.shared.success import (
    PaymentSuccessRequest,
    finalize_successful_payment,
)


def _subscription(subscription_id: int, tariff_key: str) -> SimpleNamespace:
    return SimpleNamespace(
        subscription_id=subscription_id,
        tariff_key=tariff_key,
    )


def _payment(
    *,
    sale_mode: str = "topup@pro",
    tariff_key: str = "pro",
    snapshot: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        payment_id=12,
        user_id=42,
        status="succeeded_pending_finalization",
        amount=100.0,
        currency="RUB",
        provider="tribute",
        sale_mode=sale_mode,
        tariff_key=tariff_key,
        subscription_duration_months=10,
        purchased_gb=10.0,
        entitlement_context_snapshot=snapshot,
    )


def test_snapshot_allows_only_the_same_subscription_and_tariff() -> None:
    quoted_subscription = _subscription(11, "pro")
    snapshot = build_entitlement_context_snapshot(
        sale_mode="premium_topup@pro",
        active_subscription=quoted_subscription,
    )
    assert snapshot is not None
    parsed = parse_entitlement_context_snapshot(snapshot)
    assert parsed is not None
    assert parsed.active_subscription_id == 11
    assert parsed.active_tariff_key == "pro"

    payment = _payment(
        sale_mode="premium_topup@pro",
        snapshot=snapshot,
    )
    assert preflight_payment_entitlement(payment, quoted_subscription).allowed

    replaced = preflight_payment_entitlement(
        payment,
        _subscription(12, "pro"),
    )
    assert replaced.status is EntitlementPreflightStatus.DETERMINISTIC_STALE
    assert replaced.reason == "active_subscription_changed"

    switched = preflight_payment_entitlement(
        payment,
        _subscription(11, "other"),
    )
    assert switched.status is EntitlementPreflightStatus.DETERMINISTIC_STALE
    assert switched.reason == "active_tariff_changed"


def test_initial_traffic_package_snapshot_rejects_a_later_subscription() -> None:
    snapshot = build_entitlement_context_snapshot(
        sale_mode="traffic_package@traffic",
        active_subscription=None,
    )
    payment = _payment(
        sale_mode="traffic_package@traffic",
        tariff_key="traffic",
        snapshot=snapshot,
    )

    assert preflight_payment_entitlement(payment, None).allowed
    stale = preflight_payment_entitlement(
        payment,
        _subscription(20, "traffic"),
    )
    assert stale.status is EntitlementPreflightStatus.DETERMINISTIC_STALE
    assert stale.reason == "active_subscription_changed"


def test_legacy_cross_tariff_addon_is_rejected_without_snapshot() -> None:
    payment = _payment(snapshot=None)

    stale = preflight_payment_entitlement(
        payment,
        _subscription(11, "other"),
    )

    assert stale.status is EntitlementPreflightStatus.DETERMINISTIC_STALE
    assert stale.reason == "active_tariff_mismatch"


def test_snapshot_target_cannot_be_rebound_by_payment_payload() -> None:
    snapshot = build_entitlement_context_snapshot(
        sale_mode="hwid_devices@pro",
        active_subscription=_subscription(11, "pro"),
    )
    payment = _payment(
        sale_mode="hwid_devices@other",
        tariff_key="other",
        snapshot=snapshot,
    )

    invalid = preflight_payment_entitlement(
        payment,
        _subscription(11, "pro"),
    )

    assert invalid.status is EntitlementPreflightStatus.INVALID
    assert invalid.reason == "payment_target_mismatch"


def test_hwid_renewal_is_bound_to_the_quoted_subscription() -> None:
    snapshot = build_entitlement_context_snapshot(
        sale_mode="hwid_devices_renewal@pro",
        active_subscription=_subscription(11, "pro"),
    )
    payment = _payment(
        sale_mode="hwid_devices_renewal@pro",
        snapshot=snapshot,
    )

    assert preflight_payment_entitlement(payment, _subscription(11, "pro")).allowed
    stale = preflight_payment_entitlement(payment, _subscription(12, "pro"))
    assert stale.status is EntitlementPreflightStatus.DETERMINISTIC_STALE
    assert stale.reason == "active_subscription_changed"


def test_configured_topup_snapshot_uses_the_subscription_quoted_by_the_server() -> None:
    quoted_subscription = _subscription(11, "pro")
    active_lookup = AsyncMock(return_value=quoted_subscription)
    packages = SimpleNamespace(
        for_currency=lambda currency: (
            [SimpleNamespace(gb=10, price=100)] if currency == "rub" else []
        )
    )
    tariff = SimpleNamespace(
        key="pro",
        premium_topup_packages=None,
        premium_squad_uuids=[],
    )
    settings = SimpleNamespace(
        tariffs_config=SimpleNamespace(
            require=lambda key: tariff if key == "pro" else None,
            require_configured=lambda key: tariff if key == "pro" else None,
            topup_packages_for=lambda configured_tariff: (
                packages if configured_tariff is tariff else None
            ),
        )
    )

    with patch(
        "bot.payment_providers.shared.callbacks."
        "subscription_dal.get_active_subscription_by_user_id",
        active_lookup,
    ):
        quoted_parts, quote = asyncio.run(
            quote_hwid_callback_parts(
                session=cast(Any, SimpleNamespace()),
                user_id=42,
                parts=PaymentCallbackParts(
                    months=10,
                    price=1,
                    sale_mode="topup@pro",
                ),
                subscription_service=SimpleNamespace(),
                currency="rub",
                settings=settings,
            )
        )

    assert quote is None
    assert quoted_parts is not None
    parsed = parse_entitlement_context_snapshot(quoted_parts.entitlement_context_snapshot)
    assert parsed is not None
    assert parsed.active_subscription_id == 11
    assert parsed.active_tariff_key == "pro"
    active_lookup.assert_awaited_once()


def test_hwid_snapshot_uses_the_subscription_identity_returned_by_the_quote() -> None:
    service = SimpleNamespace(
        quote_hwid_device_topup=AsyncMock(
            return_value={
                "subscription_id": 11,
                "tariff_key": "pro",
                "device_count": 1,
                "price": 50,
            }
        )
    )

    with patch(
        "bot.payment_providers.shared.callbacks."
        "subscription_dal.get_active_subscription_by_user_id",
        AsyncMock(side_effect=AssertionError("quote identity must not be re-read")),
    ):
        quoted_parts, quote = asyncio.run(
            quote_hwid_callback_parts(
                session=cast(Any, SimpleNamespace()),
                user_id=42,
                parts=PaymentCallbackParts(
                    months=1,
                    price=1,
                    sale_mode="hwid_devices_renewal@pro",
                ),
                subscription_service=service,
                currency="rub",
            )
        )

    assert quote is not None
    assert quoted_parts is not None
    parsed = parse_entitlement_context_snapshot(quoted_parts.entitlement_context_snapshot)
    assert parsed is not None
    assert parsed.active_subscription_id == 11
    assert parsed.active_tariff_key == "pro"


def test_webapp_rejects_cross_tariff_addon_before_provider_creation() -> None:
    active_subscription = AsyncMock(return_value=_subscription(11, "other"))

    with (
        patch("db.dal.gift_dal.activating_for_user", AsyncMock(return_value=None)),
        patch.object(
            billing_payments,
            "get_settings",
            return_value=SimpleNamespace(),
        ),
        patch.object(
            billing_payments.subscription_dal,
            "get_active_subscription_by_user_id",
            active_subscription,
        ),
    ):
        response = asyncio.run(
            billing_payments._create_subscription_payment(
                request=cast(Any, SimpleNamespace(app={})),
                session=cast(Any, SimpleNamespace()),
                user_id=42,
                method="tribute",
                months=10,
                price=100,
                stars_price=None,
                lang="en",
                currency="RUB",
                sale_mode="topup@pro",
                traffic_gb=10,
            )
        )

    assert response.status == 409
    assert json.loads(response.body)["error"] == "entitlement_context_changed"


def test_generic_finalizer_fails_closed_before_stale_addon_activation() -> None:
    snapshot = build_entitlement_context_snapshot(
        sale_mode="topup@pro",
        active_subscription=_subscription(11, "pro"),
    )
    payment = _payment(snapshot=snapshot)
    session = AsyncMock()
    subscription_service = SimpleNamespace(activate_subscription=AsyncMock())
    update_status = AsyncMock(return_value=payment)

    with (
        patch("db.dal.gift_dal.activating_for_user", AsyncMock(return_value=None)),
        patch(
            "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
            AsyncMock(return_value=payment),
        ),
        patch(
            "bot.payment_providers.shared.success.user_dal.lock_user_by_id",
            AsyncMock(return_value=SimpleNamespace(user_id=42)),
        ),
        patch(
            "bot.payment_providers.shared.success."
            "subscription_dal.get_active_subscription_by_user_id_for_update",
            AsyncMock(return_value=_subscription(12, "pro")),
        ),
        patch(
            "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
            update_status,
        ),
    ):
        outcome = asyncio.run(
            finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
                    i18n=SimpleNamespace(),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=SimpleNamespace(),
                    payment=payment,
                    user_id=42,
                    amount=100,
                    currency="RUB",
                    sale_mode="topup@pro",
                    months=10,
                    traffic_amount=10,
                    provider_subscription="tribute",
                    provider_notification="tribute",
                )
            )
        )

    assert outcome is None
    subscription_service.activate_subscription.assert_not_awaited()
    session.rollback.assert_awaited_once()
    update_status.assert_awaited_once_with(session, 12, "activation_failed")
    session.commit.assert_awaited_once()


def test_generic_finalizer_blocks_cross_provider_subscription_race() -> None:
    payment = _payment(
        sale_mode="subscription@pro",
        snapshot=None,
    )
    payment.provider = "stripe"
    payment.subscription_duration_months = 1
    session = AsyncMock()
    subscription_service = SimpleNamespace(activate_subscription=AsyncMock())
    update_status = AsyncMock(return_value=payment)
    active_tribute_subscription = SimpleNamespace(
        subscription_id=11,
        tariff_key="pro",
        provider="tribute",
        auto_renew_enabled=True,
    )

    with (
        patch("db.dal.gift_dal.activating_for_user", AsyncMock(return_value=None)),
        patch(
            "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
            AsyncMock(return_value=payment),
        ),
        patch(
            "bot.payment_providers.shared.success.user_dal.lock_user_by_id",
            AsyncMock(return_value=SimpleNamespace(user_id=42)),
        ),
        patch(
            "bot.payment_providers.shared.success."
            "subscription_dal.get_active_subscription_by_user_id_for_update",
            AsyncMock(return_value=active_tribute_subscription),
        ),
        patch(
            "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
            update_status,
        ),
    ):
        outcome = asyncio.run(
            finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
                    i18n=SimpleNamespace(),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=SimpleNamespace(),
                    payment=payment,
                    user_id=42,
                    amount=100,
                    currency="RUB",
                    sale_mode="subscription@pro",
                    months=1,
                    traffic_amount=None,
                    provider_subscription="stripe",
                    provider_notification="stripe",
                )
            )
        )

    assert outcome is None
    subscription_service.activate_subscription.assert_not_awaited()
    update_status.assert_awaited_once_with(session, 12, "activation_failed")
    session.rollback.assert_awaited_once()
    session.commit.assert_awaited_once()


class _ReachedActivation(Exception):
    """Sentinel: the guard let the payment reach entitlement activation."""


def _live_tribute_recurrence() -> SimpleNamespace:
    return SimpleNamespace(
        subscription_id=11,
        tariff_key="pro",
        provider="tribute",
        auto_renew_enabled=True,
    )


def _finalize_against_live_tribute_recurrence(
    payment: SimpleNamespace,
    *,
    sale_mode: str,
    provider: str,
) -> tuple[Any, AsyncMock, SimpleNamespace]:
    session = AsyncMock()
    subscription_service = SimpleNamespace(activate_subscription=AsyncMock())
    update_status = AsyncMock(return_value=payment)

    with (
        patch("db.dal.gift_dal.activating_for_user", AsyncMock(return_value=None)),
        patch(
            "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
            AsyncMock(return_value=payment),
        ),
        patch(
            "bot.payment_providers.shared.success.user_dal.lock_user_by_id",
            AsyncMock(return_value=SimpleNamespace(user_id=42)),
        ),
        patch(
            "bot.payment_providers.shared.success."
            "subscription_dal.get_active_subscription_by_user_id_for_update",
            AsyncMock(return_value=_live_tribute_recurrence()),
        ),
        patch(
            "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
            update_status,
        ),
    ):
        outcome = asyncio.run(
            finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
                    i18n=SimpleNamespace(),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=SimpleNamespace(),
                    payment=payment,
                    user_id=42,
                    amount=100,
                    currency="RUB",
                    sale_mode=sale_mode,
                    months=1,
                    traffic_amount=None,
                    provider_subscription=provider,
                    provider_notification=provider,
                )
            )
        )
    return outcome, update_status, subscription_service


def test_generic_finalizer_blocks_a_tribute_tariff_upgrade_onto_live_recurrence() -> None:
    """Only a real Tribute subscription webhook may land on its own recurrence.

    An upgrade replaces the plan the recurrence was created for, and Tribute
    cannot reprice a recurrence that already exists, so it is blocked like any
    other provider's payment rather than riding the provider exemption.
    """

    payment = _payment(sale_mode="tariff_upgrade@pro", snapshot=None)
    payment.subscription_duration_months = 1

    outcome, update_status, subscription_service = _finalize_against_live_tribute_recurrence(
        payment,
        sale_mode="tariff_upgrade@pro",
        provider="tribute",
    )

    assert outcome is None
    subscription_service.activate_subscription.assert_not_awaited()
    update_status.assert_awaited_once_with(ANY, 12, "activation_failed")


def test_generic_finalizer_lets_the_tribute_subscription_webhook_through() -> None:
    """The exemption exists for exactly one case: Tribute renewing itself."""

    payment = _payment(sale_mode="subscription@pro", snapshot=None)
    payment.subscription_duration_months = 1
    session = AsyncMock()
    # Stopping at activation keeps the test on the guard rather than on the
    # whole post-activation pipeline; reaching it at all is the assertion.
    subscription_service = SimpleNamespace(
        activate_subscription=AsyncMock(side_effect=_ReachedActivation())
    )
    lock_subscription = AsyncMock(return_value=_live_tribute_recurrence())

    with (
        patch("db.dal.gift_dal.activating_for_user", AsyncMock(return_value=None)),
        patch(
            "bot.payment_providers.shared.success.payment_dal.get_payment_by_db_id_for_update",
            AsyncMock(return_value=payment),
        ),
        patch(
            "bot.payment_providers.shared.success.user_dal.lock_user_by_id",
            AsyncMock(return_value=SimpleNamespace(user_id=42)),
        ),
        patch(
            "bot.payment_providers.shared.success."
            "subscription_dal.get_active_subscription_by_user_id_for_update",
            lock_subscription,
        ),
        patch(
            "bot.payment_providers.shared.success.payment_dal.update_payment_status_by_db_id",
            AsyncMock(return_value=payment),
        ),
    ):
        outcome = asyncio.run(
            finalize_successful_payment(
                PaymentSuccessRequest(
                    bot=SimpleNamespace(),
                    settings=SimpleNamespace(DEFAULT_LANGUAGE="en"),
                    i18n=SimpleNamespace(),
                    session=session,
                    subscription_service=subscription_service,
                    referral_service=SimpleNamespace(),
                    payment=payment,
                    user_id=42,
                    amount=100,
                    currency="RUB",
                    sale_mode="subscription@pro",
                    months=1,
                    traffic_amount=None,
                    provider_subscription="tribute",
                    provider_notification="tribute",
                )
            )
        )

    assert outcome is None
    subscription_service.activate_subscription.assert_awaited_once()
    # The exempted path does not even take the entitlement lock.
    lock_subscription.assert_not_awaited()
