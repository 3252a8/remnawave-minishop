from datetime import UTC, datetime
from types import SimpleNamespace

from bot.app.web.admin_api_impl.common import _serialize_payment


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
