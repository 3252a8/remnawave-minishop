from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import Table
from sqlalchemy.sql.dml import Update

from bot.app.web.webapp.auth_panel import _link_telegram_to_user
from db.dal import user_merge_dal


class _Result:
    def __init__(self, values: list[object] | None = None) -> None:
        self._values = values or []

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self._values

    def scalar_one_or_none(self) -> object | None:
        return self._values[0] if self._values else None


def _user(user_id: int, **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "user_id": user_id,
        "email": None,
        "email_verified_at": None,
        "notification_email": None,
        "password_hash": None,
        "password_set_at": None,
        "telegram_id": None,
        "panel_user_uuid": None,
        "referral_code": None,
        "referred_by_id": None,
        "username": None,
        "first_name": None,
        "last_name": None,
        "language_code": "ru",
        "telegram_photo_url": None,
        "telegram_notifications_status": "unknown",
        "telegram_notifications_checked_at": None,
        "telegram_notifications_enabled_at": None,
        "telegram_notifications_blocked_at": None,
        "channel_subscription_verified": None,
        "channel_subscription_checked_at": None,
        "channel_subscription_verified_for": None,
        "lifetime_used_traffic_bytes": None,
        "lifetime_used_traffic_synced_at": None,
        "referral_welcome_bonus_claimed_at": None,
        "is_banned": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _merge(
    source: SimpleNamespace, target: SimpleNamespace
) -> tuple[object, SimpleNamespace]:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Result()),
        delete=AsyncMock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
    )
    with (
        patch.object(
            user_merge_dal,
            "_lock_users_for_merge",
            AsyncMock(return_value=(source, target)),
        ),
        patch.object(
            user_merge_dal,
            "_accounts_share_promo_activation",
            AsyncMock(return_value=False),
        ),
        patch.object(
            user_merge_dal,
            "_get_active_subscription_for_user",
            AsyncMock(return_value=None),
        ),
        patch.object(
            user_merge_dal,
            "_get_latest_subscription_for_user",
            AsyncMock(return_value=None),
        ),
        patch.object(user_merge_dal.events, "emit_model", AsyncMock()),
    ):
        merged = await user_merge_dal.merge_users(
            session,
            source_user_id=int(source.user_id),
            target_user_id=int(target.user_id),
            reason="telegram_link",
        )
    return merged, session


async def _merge_keeps_established_email_and_notification_and_moves_auth_methods() -> None:
    verified_at = datetime.now(UTC)
    source = _user(
        -10,
        email="new-yandex@example.test",
        email_verified_at=verified_at,
        notification_email="new-yandex@example.test",
        password_hash="source-password",
    )
    target = _user(
        42,
        email="original@example.test",
        email_verified_at=verified_at,
        notification_email="original@example.test",
        telegram_id=42,
    )

    merged, session = await _merge(source, target)

    assert merged is target
    assert target.email == "original@example.test"
    assert target.notification_email == "original@example.test"
    assert target.password_hash == "source-password"
    updated_tables = {
        cast(Table, call.args[0].table).name
        for call in session.execute.await_args_list
        if isinstance(call.args[0], Update)
    }
    assert {"user_email_addresses", "user_external_identities", "user_passkey_credentials"} <= (
        updated_tables
    )


def test_merge_keeps_established_email_and_notification_and_moves_auth_methods() -> None:
    asyncio.run(_merge_keeps_established_email_and_notification_and_moves_auth_methods())


async def _merge_promotes_verified_source_over_unverified_target_email() -> None:
    verified_at = datetime.now(UTC)
    source = _user(
        -10,
        email="verified@example.test",
        email_verified_at=verified_at,
        notification_email="verified@example.test",
    )
    target = _user(42, email="unverified@example.test", telegram_id=42)

    await _merge(source, target)

    assert target.email == "verified@example.test"
    assert target.email_verified_at is verified_at
    assert target.notification_email == "verified@example.test"


def test_merge_promotes_verified_source_over_unverified_target_email() -> None:
    asyncio.run(_merge_promotes_verified_source_over_unverified_target_email())


async def _merge_keeps_established_password_when_both_accounts_have_one() -> None:
    source = _user(-10, password_hash="source-password")
    target = _user(42, password_hash="target-password", telegram_id=42)

    await _merge(source, target)

    assert target.password_hash == "target-password"


def test_merge_keeps_established_password_when_both_accounts_have_one() -> None:
    asyncio.run(_merge_keeps_established_password_when_both_accounts_have_one())


async def _merge_reports_the_conflicting_external_provider() -> None:
    source = _user(-10)
    target = _user(42, telegram_id=42)
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[_Result(["google"]), _Result(["google"])]),
    )
    with (
        patch.object(
            user_merge_dal,
            "_lock_users_for_merge",
            AsyncMock(return_value=(source, target)),
        ),
        patch.object(
            user_merge_dal,
            "_accounts_share_promo_activation",
            AsyncMock(return_value=False),
        ),
        pytest.raises(user_merge_dal.UserMergeConflictError) as raised,
    ):
        await user_merge_dal.merge_users(
            session,
            source_user_id=-10,
            target_user_id=42,
        )

    assert raised.value.code == "account_merge_google_conflict"
    assert raised.value.message_key == "account_merge_google_conflict"


def test_merge_reports_the_conflicting_external_provider() -> None:
    asyncio.run(_merge_reports_the_conflicting_external_provider())


async def _telegram_link_allows_distinct_verified_emails_to_merge() -> None:
    current = _user(-10, email="new-yandex@example.test")
    existing = _user(42, email="original@example.test", telegram_id=42)
    merged = _user(
        42,
        email="original@example.test",
        notification_email="original@example.test",
        telegram_id=42,
    )
    session = SimpleNamespace(flush=AsyncMock())
    telegram_profile = {
        "id": 42,
        "username": "alice",
        "first_name": "Alice",
        "last_name": "",
        "language_code": "ru",
    }
    merge_users = AsyncMock(return_value=merged)
    with (
        patch(
            "bot.app.web.webapp.auth_panel.user_dal.get_user_by_id", AsyncMock(return_value=current)
        ),
        patch(
            "bot.app.web.webapp.auth_panel.user_dal.get_user_by_telegram_id",
            AsyncMock(return_value=existing),
        ),
        patch("bot.app.web.webapp.auth_panel.user_dal.merge_users", merge_users),
    ):
        result = await _link_telegram_to_user(
            SimpleNamespace(app={}),
            session,
            current_user_id=-10,
            telegram_user=telegram_profile,
            settings=SimpleNamespace(DEFAULT_LANGUAGE="ru"),
        )

    assert result is merged
    merge_users.assert_awaited_once_with(
        session,
        source_user_id=-10,
        target_user_id=42,
        reason="telegram_link",
        send_user_email=False,
    )


def test_telegram_link_allows_distinct_verified_emails_to_merge() -> None:
    asyncio.run(_telegram_link_allows_distinct_verified_emails_to_merge())
