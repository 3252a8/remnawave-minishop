"""Parity tests for the admin user response contract.

``_serialize_user`` now routes through ``AdminUserOut`` and the avatar variant
through ``AdminUserWithAvatarOut``; these pin the serialized JSON (keys, order,
values) byte-shape identical to the legacy dicts the admin clients consume.
"""

from datetime import datetime
from types import SimpleNamespace

from bot.app.web.admin_api_impl.common import _serialize_user
from bot.app.web.admin_api_impl.users_common import _serialize_admin_user_with_avatar
from bot.app.web.admin_api_impl.users_detail import _serialize_trial_summary


def _user(**overrides):
    values = {
        "user_id": 42,
        "telegram_id": 123,
        "telegram_photo_url": "http://example.test/p.jpg",
        "username": "bob",
        "first_name": "Bob",
        "last_name": "Lee",
        "email": "b@example.test",
        "language_code": "ru",
        "is_banned": False,
        "registration_date": datetime(2026, 1, 1, 12, 0, 0),
        "panel_user_uuid": "puuid",
        "referral_code": "ref1",
        "referred_by_id": 7,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


_EXPECTED_BASE = {
    "user_id": 42,
    "telegram_id": 123,
    "telegram_photo_url": "http://example.test/p.jpg",
    "username": "bob",
    "first_name": "Bob",
    "last_name": "Lee",
    "email": "b@example.test",
    "language_code": "ru",
    "is_banned": False,
    "registration_date": "2026-01-01T12:00:00",
    "panel_user_uuid": "puuid",
    "referral_code": "ref1",
    "referred_by_id": 7,
}


def test_serialize_user_matches_legacy_contract():
    result = _serialize_user(_user())
    assert result == _EXPECTED_BASE
    assert list(result.keys()) == list(_EXPECTED_BASE.keys())


def test_serialize_user_nullable_ids_stay_none():
    result = _serialize_user(_user(telegram_id=None, referred_by_id=None, registration_date=None))
    assert result["telegram_id"] is None
    assert result["referred_by_id"] is None
    assert result["registration_date"] is None


def test_serialize_admin_user_with_avatar_appends_avatar_url():
    result = _serialize_admin_user_with_avatar(_user(), {42: "v1"})
    expected = {**_EXPECTED_BASE, "avatar_url": "/api/admin/users/42/avatar?v=v1"}
    assert result == expected
    # avatar_url is the last key (appended after the base user fields).
    assert list(result.keys()) == list(expected.keys())


def test_serialize_admin_user_with_avatar_without_cached_avatar():
    result = _serialize_admin_user_with_avatar(_user(), {})
    assert result["avatar_url"] is None


def test_serialize_trial_summary_matches_legacy_contract():
    user = SimpleNamespace(trial_eligibility_reset_at=datetime(2026, 3, 1, 0, 0, 0))
    sub1 = SimpleNamespace(
        start_date=datetime(2026, 1, 1), end_date=datetime(2026, 1, 8), is_active=False
    )
    sub2 = SimpleNamespace(
        start_date=datetime(2026, 2, 1), end_date=datetime(2026, 2, 8), is_active=True
    )
    result = _serialize_trial_summary(user, [sub1, sub2])
    expected = {
        "used": True,
        "count": 2,
        "first_activated_at": "2026-01-01T00:00:00",
        "latest_activated_at": "2026-02-01T00:00:00",
        "latest_end_date": "2026-02-08T00:00:00",
        "active": True,
        "last_reset_at": "2026-03-01T00:00:00",
    }
    assert result == expected
    assert list(result.keys()) == list(expected.keys())


def test_serialize_trial_summary_empty():
    result = _serialize_trial_summary(SimpleNamespace(trial_eligibility_reset_at=None), [])
    assert result == {
        "used": False,
        "count": 0,
        "first_activated_at": None,
        "latest_activated_at": None,
        "latest_end_date": None,
        "active": False,
        "last_reset_at": None,
    }
