from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.handlers.admin.sync_admin import (
    _coerce_panel_telegram_id,
    _description_matches,
    _should_update_lifetime_used_traffic,
    _subscription_update_delta,
)
from db.models import Subscription


def test_description_match_ignores_whitespace_shape():
    assert _description_matches("email@example.com username", "email@example.com\nusername")


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
