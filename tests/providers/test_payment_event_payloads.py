from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session, make_transient_to_detached

from bot.infra.payment_events import (
    PaymentPurchase,
    build_payment_succeeded_payload,
    register_payment_purchase_resolver,
    reset_payment_purchase_resolvers,
    resolve_payment_success_snapshot,
)
from db.models import Payment, PromoCode


def teardown_function():
    reset_payment_purchase_resolvers()


def test_payment_success_snapshot_resolves_core_purchase_units_from_payment():
    payment = SimpleNamespace(
        amount=120.0,
        currency="RUB",
        provider="wata",
        sale_mode="topup@standard",
        tariff_key="standard",
        purchased_gb=12.5,
        purchased_hwid_devices=2,
        subscription_duration_months=None,
    )

    snapshot = resolve_payment_success_snapshot(
        {
            "user_id": 42,
            "payment_db_id": 5,
            "notification_provider": "wata",
            "sale_mode": "topup@standard",
        },
        payment,
    )

    assert snapshot.amount == 120.0
    assert snapshot.currency == "RUB"
    assert snapshot.notification_provider == "wata"
    assert snapshot.traffic_gb == 12.5
    assert snapshot.purchased_hwid_devices == 2
    assert snapshot.purchases == (
        PaymentPurchase(kind="traffic", amount=12.5, unit="gb", scope="regular", sort_order=20),
        PaymentPurchase(kind="hwid_devices", amount=2.0, unit="device", sort_order=40),
    )


def test_payment_success_payload_builder_backfills_purchase_units():
    payment = SimpleNamespace(
        sale_mode="subscription@standard",
        tariff_key="standard",
        purchased_hwid_devices=None,
        purchased_gb=None,
    )

    payload = build_payment_succeeded_payload(
        user_id=42,
        payment_db_id=5,
        provider="yookassa",
        notification_provider="yookassa",
        amount=180.0,
        currency="RUB",
        sale_mode="subscription@standard",
        tariff_key="standard",
        months=1,
        traffic_gb=None,
        activation={"hwid_devices_renewed_count": 2},
        payment=payment,
        end_date="2026-01-02T03:04:00+00:00",
        is_auto_renew=False,
    )

    assert payload["months"] == 1
    assert payload["traffic_gb"] is None
    assert payload["purchased_hwid_devices"] == 2
    assert payload["end_date"] == "2026-01-02T03:04:00+00:00"


@pytest.mark.parametrize("detached", [False, True])
def test_payment_success_payload_does_not_load_payment_relationships(detached: bool):
    payment = Payment(
        payment_id=5,
        amount=75.0,
        currency="RUB",
        provider="partner_balance",
        sale_mode="subscription@standard",
        tariff_key="standard",
        subscription_duration_months=1,
        subscription_duration_days=None,
        purchased_gb=None,
        purchased_hwid_devices=None,
        promo_code_id=17,
        checkout_base_amount=100.0,
        checkout_discount_amount=25.0,
    )
    make_transient_to_detached(payment)

    # No database is bound: any implicit ORM load must fail this test.
    with Session() as session:
        if not detached:
            session.add(payment)
        payload = build_payment_succeeded_payload(
            user_id=42,
            payment_db_id=5,
            provider="partner_balance",
            notification_provider="partner_balance",
            amount=75.0,
            currency="RUB",
            sale_mode="subscription@standard",
            tariff_key="standard",
            months=1,
            traffic_gb=None,
            payment=payment,
            end_date="2026-01-02T03:04:00+00:00",
            is_auto_renew=False,
        )

    assert payload["promo_code_id"] == 17
    assert payload["base_amount"] == 100.0
    assert payload["discount_amount"] == 25.0
    assert payload["amount"] == 75.0
    assert payload["provider"] == "partner_balance"


@pytest.mark.parametrize("expired_fields", [(), ("archived_code",), ("code", "archived_code")])
def test_payment_success_snapshot_reads_only_loaded_code_attributes(
    expired_fields: tuple[str, ...],
):
    promo = PromoCode(promo_code_id=17, code="PUBLIC17", archived_code=None)
    make_transient_to_detached(promo)
    payment = Payment(promo_code_id=17, promo_code_used=promo)

    with Session() as session:
        session.add(promo)
        if expired_fields:
            session.expire(promo, list(expired_fields))
        snapshot = resolve_payment_success_snapshot(
            {"amount": 75.0, "currency": "RUB", "sale_mode": "subscription@standard"},
            payment,
        )

    assert snapshot.promo_code == (None if "code" in expired_fields else "PUBLIC17")
    assert snapshot.promo_code_id == 17


def test_payment_success_snapshot_backfills_checkout_amounts_from_payment():
    payment = SimpleNamespace(
        amount=75.0,
        currency="RUB",
        provider="wata",
        sale_mode="subscription@standard",
        subscription_duration_months=1,
        checkout_base_amount=100.0,
        checkout_discount_amount=25.0,
    )

    snapshot = resolve_payment_success_snapshot(
        {
            "user_id": 42,
            "payment_db_id": 5,
            "sale_mode": "subscription@standard",
        },
        payment,
    )

    assert snapshot.base_amount == 100.0
    assert snapshot.discount_amount == 25.0


def test_payment_success_snapshot_resolves_public_promo_code_from_payment():
    payment = SimpleNamespace(
        amount=75.0,
        currency="RUB",
        provider="wata",
        sale_mode="subscription@standard",
        subscription_duration_months=1,
        promo_code_id=17,
        promo_code_used=SimpleNamespace(
            code="__ARCHIVED_PROMO__17__AGATA",
            archived_code="AGATA",
        ),
        checkout_discount_amount=25.0,
    )

    snapshot = resolve_payment_success_snapshot(
        {
            "user_id": 42,
            "payment_db_id": 5,
            "sale_mode": "subscription@standard",
        },
        payment,
    )

    assert snapshot.promo_code == "AGATA"
    assert snapshot.discount_amount == 25.0


def test_payment_success_snapshot_keeps_explicit_zero_discount():
    payment = SimpleNamespace(
        amount=100.0,
        currency="RUB",
        provider="wata",
        sale_mode="subscription@standard",
        subscription_duration_months=1,
        checkout_base_amount=100.0,
        checkout_discount_amount=25.0,
    )

    snapshot = resolve_payment_success_snapshot(
        {
            "user_id": 42,
            "payment_db_id": 5,
            "sale_mode": "subscription@standard",
            "discount_amount": 0,
        },
        payment,
    )

    assert snapshot.base_amount == 100.0
    assert snapshot.discount_amount == 0.0


def test_plugin_purchase_resolver_extends_payment_snapshot():
    def resolver(ctx):
        if ctx.payload.get("extra_seats"):
            return (
                PaymentPurchase(
                    kind="extra_seats",
                    amount=float(ctx.payload["extra_seats"]),
                    unit="seat",
                    label_key="log_payment_extra_seats_line",
                    label_kwargs={"plan": ctx.tariff_key or ""},
                    sort_order=60,
                ),
            )
        return ()

    register_payment_purchase_resolver(resolver)
    register_payment_purchase_resolver(resolver)

    snapshot = resolve_payment_success_snapshot(
        {
            "user_id": 42,
            "payment_db_id": 5,
            "amount": 50,
            "currency": "RUB",
            "provider": "plugin",
            "sale_mode": "subscription@standard",
            "tariff_key": "standard",
            "months": 1,
            "extra_seats": 3,
        }
    )

    assert [purchase.kind for purchase in snapshot.purchases] == ["extra_seats"]
    assert snapshot.purchases[0].label_key == "log_payment_extra_seats_line"
    assert snapshot.purchases[0].label_kwargs == {"plan": "standard"}
