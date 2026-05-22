import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.admin.sync_admin import (
    _absorb_duplicate_panel_identity,
    _coerce_panel_telegram_id,
    _description_matches,
    _should_update_lifetime_used_traffic,
    _subscription_update_delta,
)
from db.models import Subscription


def test_description_match_ignores_whitespace_shape():
    assert _description_matches("email@example.com username", "email@example.com\nusername")


def test_description_match_accepts_cp1251_mojibake_from_panel():
    desired = "user@example.com\nalice\nАлексей\nЧерников"
    panel_value = "user@example.com\nalice\nÀëåêñåé\n×åðíèêîâ"

    assert _description_matches(panel_value, desired)


def test_description_match_rejects_different_identity_after_mojibake_repair():
    desired = "user@example.com\nalice\nАлексей"
    panel_value = "other@example.com\nalice\nÀëåêñåé"

    assert not _description_matches(panel_value, desired)


def test_panel_telegram_id_is_coerced_to_int():
    assert _coerce_panel_telegram_id("12345") == 12345
    assert _coerce_panel_telegram_id("") is None


def test_subscription_update_delta_skips_unchanged_fields():
    end_date = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    subscription = Subscription(
        user_id=1,
        panel_user_uuid="panel-1",
        panel_subscription_uuid="sub-1",
        end_date=end_date,
        is_active=True,
        status_from_panel="ACTIVE",
    )

    assert (
        _subscription_update_delta(
            subscription,
            {
                "user_id": 1,
                "panel_user_uuid": "panel-1",
                "end_date": end_date + timedelta(milliseconds=500),
                "is_active": True,
                "status_from_panel": "ACTIVE",
            },
        )
        == {}
    )


def test_subscription_update_delta_returns_only_changed_fields():
    end_date = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    subscription = Subscription(
        user_id=1,
        panel_user_uuid="panel-1",
        panel_subscription_uuid="sub-1",
        end_date=end_date,
        is_active=True,
        status_from_panel="ACTIVE",
    )

    assert _subscription_update_delta(
        subscription,
        {
            "user_id": 2,
            "panel_user_uuid": "panel-1",
            "end_date": end_date + timedelta(seconds=2),
            "is_active": False,
            "status_from_panel": "EXPIRED",
        },
    ) == {
        "user_id": 2,
        "end_date": end_date + timedelta(seconds=2),
        "is_active": False,
        "status_from_panel": "EXPIRED",
    }


def test_lifetime_traffic_update_waits_for_time_window_for_small_delta():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    settings = SimpleNamespace(
        PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS=3600,
        PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES=100 * 1024 * 1024,
    )
    user = SimpleNamespace(
        lifetime_used_traffic_bytes=10 * 1024 * 1024,
        lifetime_used_traffic_synced_at=now - timedelta(minutes=15),
    )

    assert not _should_update_lifetime_used_traffic(
        user,
        11 * 1024 * 1024,
        now=now,
        settings=settings,
    )
    assert _should_update_lifetime_used_traffic(
        user,
        11 * 1024 * 1024,
        now=now + timedelta(hours=1),
        settings=settings,
    )


def test_lifetime_traffic_update_allows_large_delta_and_skips_duplicate_panel_identity():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    settings = SimpleNamespace(
        PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS=3600,
        PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES=100 * 1024 * 1024,
    )
    user = SimpleNamespace(
        lifetime_used_traffic_bytes=10 * 1024 * 1024,
        lifetime_used_traffic_synced_at=now,
    )

    assert _should_update_lifetime_used_traffic(
        user,
        200 * 1024 * 1024,
        now=now,
        settings=settings,
    )
    assert not _should_update_lifetime_used_traffic(
        user,
        0,
        now=now + timedelta(hours=2),
        settings=settings,
        is_duplicate_panel_identity=True,
    )


def test_absorb_duplicate_panel_identity_extends_kept_user_and_deletes_duplicate():
    now = datetime.now(timezone.utc)
    target_sub = SimpleNamespace(
        subscription_id=10,
        user_id=42,
        panel_user_uuid="panel-keep",
        panel_subscription_uuid="sub-keep",
        end_date=now - timedelta(days=2),
        is_active=False,
        status_from_panel="EXPIRED",
    )
    duplicate_sub = SimpleNamespace(
        subscription_id=11,
        user_id=42,
        panel_user_uuid="panel-duplicate",
        panel_subscription_uuid="sub-duplicate",
        end_date=now + timedelta(days=30),
        is_active=True,
        skip_notifications=False,
        status_from_panel="ACTIVE",
    )
    panel_service = SimpleNamespace(
        update_user_details_on_panel=AsyncMock(return_value={"uuid": "panel-keep"}),
        delete_user_from_panel=AsyncMock(return_value=True),
    )
    session = SimpleNamespace(execute=AsyncMock())
    settings = SimpleNamespace(user_traffic_limit_bytes=0)
    user = SimpleNamespace(
        user_id=42,
        panel_user_uuid="panel-keep",
        telegram_id=969808056,
        email="paid@example.com",
        username="alice",
        first_name="Alice",
        last_name=None,
    )

    async def update_subscription(_session, subscription_id, update_data):
        sub = target_sub if subscription_id == target_sub.subscription_id else duplicate_sub
        for key, value in update_data.items():
            setattr(sub, key, value)
        return sub

    with patch(
        "bot.handlers.admin.sync_admin.subscription_dal.update_subscription",
        AsyncMock(side_effect=update_subscription),
    ):
        result = asyncio.run(
            _absorb_duplicate_panel_identity(
                session,
                panel_service=panel_service,
                existing_user=user,
                keep_panel_uuid="panel-keep",
                keep_panel_user={
                    "uuid": "panel-keep",
                    "subscriptionUuid": "sub-keep",
                    "status": "EXPIRED",
                    "expireAt": (now - timedelta(days=2)).isoformat(),
                },
                duplicate_panel_user={
                    "uuid": "panel-duplicate",
                    "subscriptionUuid": "sub-duplicate",
                    "telegramId": 969808056,
                    "status": "ACTIVE",
                    "expireAt": (now + timedelta(days=30)).isoformat(),
                },
                settings=settings,
                subscriptions_by_panel_uuid={
                    "sub-keep": target_sub,
                    "sub-duplicate": duplicate_sub,
                },
                active_subscriptions_by_user_panel={},
            )
        )

    assert result["resolved"]
    assert result["subscriptions_updated"] == 2
    assert target_sub.is_active
    assert target_sub.status_from_panel == "ACTIVE_EXTENDED_BY_PANEL_DUPLICATE_MERGE"
    assert target_sub.panel_user_uuid == "panel-keep"
    assert target_sub.end_date > now + timedelta(days=29)
    assert not duplicate_sub.is_active
    assert duplicate_sub.skip_notifications
    assert duplicate_sub.status_from_panel == "MERGED_PANEL_DUPLICATE"
    panel_service.update_user_details_on_panel.assert_awaited_once()
    update_uuid, update_payload = panel_service.update_user_details_on_panel.await_args.args[:2]
    assert update_uuid == "panel-keep"
    assert update_payload["status"] == "ACTIVE"
    assert update_payload["telegramId"] == 969808056
    panel_service.delete_user_from_panel.assert_awaited_once_with(
        "panel-duplicate",
        log_response=False,
    )
