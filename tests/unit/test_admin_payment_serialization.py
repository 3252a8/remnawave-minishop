from datetime import UTC, datetime
from types import SimpleNamespace

from bot.app.web.admin_api_impl.common import _serialize_payment
from bot.app.web.admin_api_impl.schemas import PaymentDetailOut, PaymentOut


def _payment(**overrides):
    data = {
        "payment_id": 10,
        "user_id": 42,
        "provider": "wata",
        "provider_payment_id": "provider-10",
        "amount": 120.0,
        "currency": "RUB",
        "status": "succeeded",
        "description": "Top-up",
        "subscription_duration_months": None,
        "sale_mode": "topup@standard",
        "tariff_key": "standard",
        "purchased_gb": 12.5,
        "purchased_hwid_devices": 2,
        "provider_payment_url": "https://pay.example.test/provider-10",
        "promo_code_id": 5,
        "promo_discount_percent": 20,
        "checkout_discount_amount": 30,
        "checkout_base_amount": 150,
        "fulfillment_source": "admin",
        "fulfilled_at": datetime(2026, 1, 2, 3, 5, tzinfo=UTC),
        "fulfilled_by_admin_id": 7,
        "fulfillment_note": "Provider confirmed the charge",
        "promo_conflict_override": False,
        "reversed_at": None,
        "reversed_by_admin_id": None,
        "reversal_note": None,
        "promo_usage_restored": False,
        "yookassa_payment_id": None,
        "idempotence_key": "payment-10",
        "updated_at": datetime(2026, 1, 2, 3, 5, tzinfo=UTC),
        "promo_code_used": SimpleNamespace(code="SAVE20", archived_code=None),
        "created_at": datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        "user": SimpleNamespace(
            user_id=42,
            telegram_id=42,
            username="alice",
            first_name="Alice",
            last_name="",
            email="alice@example.test",
        ),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_admin_payment_serializer_exposes_regular_traffic_and_hwid_devices():
    payload = _serialize_payment(_payment())

    assert payload["traffic_regular_gb"] == 12.5
    assert payload["traffic_premium_gb"] is None
    assert payload["purchased_gb"] == 12.5
    assert payload["purchased_hwid_devices"] == 2


def test_admin_payment_serializer_exposes_premium_traffic_split():
    payload = _serialize_payment(_payment(sale_mode="premium_topup@standard", purchased_gb=7))

    assert payload["traffic_regular_gb"] is None
    assert payload["traffic_premium_gb"] == 7.0


def test_payment_list_schema_exposes_discount_and_provider_link():
    payload = PaymentOut.from_orm_payment(_payment())

    assert payload.provider_payment_url == "https://pay.example.test/provider-10"
    assert payload.promo_code_id == 5
    assert payload.promo_discount_percent == 20
    assert payload.checkout_discount_amount == 30


def test_payment_detail_schema_exposes_promo_and_manual_audit():
    payload = PaymentDetailOut.from_orm_payment_detail(_payment())

    assert payload.promo_code == "SAVE20"
    assert payload.checkout_base_amount == 150
    assert payload.fulfillment_source == "admin"
    assert payload.fulfilled_by_admin_id == 7
    assert payload.fulfillment_note == "Provider confirmed the charge"
