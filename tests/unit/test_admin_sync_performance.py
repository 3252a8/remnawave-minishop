import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.admin.sync_admin import (
    _absorb_duplicate_panel_identity,
    _coerce_panel_telegram_id,
    _description_contains_email,
    _description_matches,
    _description_without_email,
    _format_panel_update_changes,
    _identity_panel_update_reasons,
    _panel_description_for_user,
    _panel_identity_fields_update_payload,
    _panel_identity_matches_user,
    _panel_identity_needs_full_fetch,
    _panel_identity_needs_legacy_description_cleanup,
    _panel_identity_payload_with_expiry,
    _panel_identity_view_for_comparison,
    _panel_update_changes,
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


def test_panel_description_for_user_excludes_email():
    user = SimpleNamespace(
        email="linked@example.com",
        username="alice",
        first_name="Alice",
        last_name="Smith",
    )

    assert _panel_description_for_user(user) == "alice\nAlice\nSmith"


def test_panel_description_for_user_filters_broken_lines():
    user = SimpleNamespace(
        email="linked@example.com",
        username="alice??",
        first_name="????",
        last_name="Smith",
    )

    assert _panel_description_for_user(user) == "alice??\nSmith"


def test_panel_update_change_summary_is_compact_and_field_based():
    changes = _panel_update_changes(
        {
            "description": "old@example.com\nalice",
            "email": "old@example.com",
            "telegramId": "41",
        },
        {
            "uuid": "panel-user-uuid",
            "description": "alice",
            "email": "new@example.com",
            "telegramId": 42,
        },
    )

    assert [field for field, _old, _new in changes] == [
        "description",
        "email",
        "telegramId",
    ]
    assert _identity_panel_update_reasons(
        changes,
        description_has_email=True,
    ) == [
        "remove_email_from_description",
        "description_mismatch",
        "email_mismatch",
        "telegramId_mismatch",
    ]
    summary = _format_panel_update_changes(changes)
    assert "\n" not in summary
    assert "description:len=21:old@example.com\\nalice->len=5:alice" in summary
    assert "telegramId:41->42" in summary


def test_description_contains_email_detects_legacy_panel_description():
    assert _description_contains_email(
        "Linked@Example.com\nalice\nAlice",
        "linked@example.com",
    )
    assert not _description_contains_email("alice\nAlice", "linked@example.com")


def test_description_without_email_preserves_panel_text():
    assert (
        _description_without_email(
            "linked@example.com\nalice\nAlice",
            "linked@example.com",
        )
        == "alice\nAlice"
    )
    assert _description_without_email("linked@example.com", "linked@example.com") == ""


def test_panel_identity_match_accepts_list_description_without_email():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
        username="alice",
        first_name="Alice",
        last_name=None,
    )
    panel_user = {
        "description": "alice\nAlice",
        "email": "linked@example.com",
        "telegramId": 42,
    }

    assert _panel_identity_matches_user(
        panel_user,
        user,
        _panel_description_for_user(user),
    )


def test_panel_identity_payload_with_expiry_excludes_description_updates():
    expire_at = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
        username="alice",
        first_name="Alice",
        last_name=None,
    )

    payload = _panel_identity_payload_with_expiry(user, expire_at=expire_at)

    assert "description" not in payload
    assert payload["email"] == "linked@example.com"
    assert payload["telegramId"] == 42


def test_panel_identity_fields_update_payload_excludes_description():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
        username="alice",
        first_name="Alice",
        last_name=None,
    )

    assert _panel_identity_fields_update_payload(user) == {
        "email": "linked@example.com",
        "telegramId": 42,
    }


def test_panel_identity_detects_legacy_full_description_cleanup_need():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
        username="alice",
        first_name="Alice",
        last_name=None,
    )
    panel_user = {
        "description": "alice\nAlice",
        "email": "linked@example.com",
        "telegramId": 42,
    }

    assert _panel_identity_needs_legacy_description_cleanup(
        panel_user,
        user,
        _panel_description_for_user(user),
    )


def test_panel_identity_detects_email_only_legacy_cleanup_need():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=None,
        username=None,
        first_name=None,
        last_name=None,
    )
    panel_user = {
        "description": "",
        "email": "linked@example.com",
    }

    assert _panel_identity_needs_legacy_description_cleanup(
        panel_user,
        user,
        _panel_description_for_user(user),
    )


def test_panel_identity_match_treats_missing_list_email_as_unknown():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
    )
    panel_user = {
        "description": "alice",
        "telegramId": 42,
    }

    assert _panel_identity_matches_user(
        panel_user,
        user,
        "alice",
    )


def test_panel_identity_match_treats_missing_full_email_as_mismatch():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
    )
    panel_user = {
        "description": "alice",
        "telegramId": 42,
    }

    assert not _panel_identity_matches_user(
        panel_user,
        user,
        "alice",
        missing_identity_fields_match=False,
    )


def test_panel_identity_match_rejects_different_returned_email():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
    )
    panel_user = {
        "description": "alice",
        "email": "other@example.com",
        "telegramId": 42,
    }

    assert not _panel_identity_matches_user(
        panel_user,
        user,
        "alice",
    )


def test_panel_identity_needs_full_fetch_for_missing_or_blank_identity_fields():
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
    )

    assert _panel_identity_needs_full_fetch({"telegramId": 42}, user)
    assert _panel_identity_needs_full_fetch({"email": "", "telegramId": 42}, user)
    assert _panel_identity_needs_full_fetch({"email": "linked@example.com"}, user)
    assert not _panel_identity_needs_full_fetch(
        {"email": "linked@example.com", "telegramId": "42"},
        user,
    )


def test_panel_identity_view_fetches_full_user_when_list_email_missing():
    panel_service = SimpleNamespace(
        get_user_by_uuid=AsyncMock(
            return_value={
                "uuid": "panel-1",
                "description": "linked@example.com\nalice",
                "email": "linked@example.com",
                "telegramId": 42,
            }
        )
    )
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
    )

    panel_user, missing_fields_match = asyncio.run(
        _panel_identity_view_for_comparison(
            panel_service,
            "panel-1",
            {
                "uuid": "panel-1",
                "description": "linked@example.com\nalice",
                "telegramId": 42,
            },
            user,
        )
    )

    assert panel_user["email"] == "linked@example.com"
    assert not missing_fields_match
    panel_service.get_user_by_uuid.assert_awaited_once_with("panel-1")


def test_panel_identity_view_fetches_full_user_to_clean_legacy_description_email():
    panel_service = SimpleNamespace(
        get_user_by_uuid=AsyncMock(
            return_value={
                "uuid": "panel-1",
                "description": "linked@example.com\nalice\nAlice",
                "email": "linked@example.com",
                "telegramId": 42,
            }
        )
    )
    user = SimpleNamespace(
        email="linked@example.com",
        telegram_id=42,
        username="alice",
        first_name="Alice",
        last_name=None,
    )

    panel_user, missing_fields_match = asyncio.run(
        _panel_identity_view_for_comparison(
            panel_service,
            "panel-1",
            {
                "uuid": "panel-1",
                "description": "alice\nAlice",
                "email": "linked@example.com",
                "telegramId": 42,
            },
            user,
            _panel_description_for_user(user),
        )
    )

    assert panel_user["description"] == "linked@example.com\nalice\nAlice"
    assert not missing_fields_match
    assert not _panel_identity_matches_user(
        panel_user,
        user,
        _panel_description_for_user(user),
        missing_identity_fields_match=missing_fields_match,
    )
    panel_service.get_user_by_uuid.assert_awaited_once_with("panel-1")


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
