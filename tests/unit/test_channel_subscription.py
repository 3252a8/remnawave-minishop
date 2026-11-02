import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.handlers.user.start import ensure_required_channel_subscription
from bot.services import channel_membership as membership
from bot.utils.channel_subscription import (
    is_required_channel_access_error,
    normalize_required_channel_id,
    normalize_required_channel_link,
)


class I18nStub:
    def gettext(self, _lang, key, **_kwargs):
        return {
            "channel_subscription_required": "subscribe first",
            "channel_subscription_check_failed": "check failed",
        }.get(key, key)


class FakeBot:
    def __init__(self, *, status="member", error=None, chat=None, chat_error=None):
        self.id = 123456
        self.status = status
        self.error = error
        self.chat = chat
        self.chat_error = chat_error
        self.calls = []
        self.get_chat_calls = []

    async def get_chat_member(self, chat_id, user_id):
        self.calls.append((chat_id, user_id))
        if self.error:
            raise self.error
        return SimpleNamespace(status=self.status, is_member=getattr(self, "is_member", False))

    async def get_chat(self, chat_id):
        self.get_chat_calls.append(chat_id)
        if self.chat_error:
            raise self.chat_error
        return self.chat or SimpleNamespace(username="required_channel")


def _settings(required_channel_id, required_channel_link="https://t.me/example"):
    return SimpleNamespace(
        REQUIRED_CHANNEL_ID=required_channel_id,
        REQUIRED_CHANNEL_LINK=required_channel_link,
        ADMIN_IDS=[],
        REQUIRED_CHANNEL_VERIFICATION_TTL_SECONDS=900,
        DEFAULT_LANGUAGE="en",
    )


def _message_event(bot, user_id=42):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        bot=bot,
        answer=AsyncMock(),
    )


def _db_user(*, verified=False, verified_for=None):
    return SimpleNamespace(
        user_id=7,
        telegram_id=42,
        channel_subscription_checked_at=datetime.now(UTC),
        channel_subscription_verified=verified,
        channel_subscription_verified_for=verified_for,
    )


class RequiredChannelIdNormalizationTests(unittest.TestCase):
    def test_normalizes_raw_channel_ids_to_bot_api_chat_ids(self):
        self.assertEqual(normalize_required_channel_id(1234567890), -1001234567890)
        self.assertEqual(normalize_required_channel_id("1234567890"), -1001234567890)
        self.assertEqual(normalize_required_channel_id(-1234567890), -1001234567890)
        self.assertEqual(normalize_required_channel_id(-1001234567890), -1001234567890)
        self.assertEqual(normalize_required_channel_id(-123456789), -123456789)

    def test_ignores_empty_channel_ids(self):
        self.assertIsNone(normalize_required_channel_id(None))
        self.assertIsNone(normalize_required_channel_id(""))
        self.assertIsNone(normalize_required_channel_id(0))

    def test_normalizes_channel_links_for_join_button(self):
        self.assertEqual(
            normalize_required_channel_link("@required_channel"), "https://t.me/required_channel"
        )
        self.assertEqual(
            normalize_required_channel_link("required_channel"), "https://t.me/required_channel"
        )
        self.assertEqual(
            normalize_required_channel_link("t.me/required_channel"),
            "https://t.me/required_channel",
        )
        self.assertEqual(
            normalize_required_channel_link("https://t.me/required_channel"),
            "https://t.me/required_channel",
        )
        self.assertEqual(normalize_required_channel_link("+inviteHash"), "https://t.me/+inviteHash")
        self.assertIsNone(normalize_required_channel_link("not a valid link"))

    def test_detects_channel_configuration_errors(self):
        self.assertTrue(
            is_required_channel_access_error(
                TelegramBadRequest(method=None, message="Bad Request: chat not found")
            )
        )
        self.assertFalse(
            is_required_channel_access_error(
                TelegramBadRequest(method=None, message="Bad Request: user not found")
            )
        )


@pytest.fixture(autouse=True)
def available_channel(monkeypatch):
    membership._recent.clear()
    membership._pending.clear()
    monkeypatch.setattr(
        membership,
        "check_required_channel",
        AsyncMock(return_value=SimpleNamespace(status="available")),
    )
    monkeypatch.setattr("bot.handlers.user.start_channel.is_admin", AsyncMock(return_value=False))


@pytest.mark.parametrize(
    "status,is_member,expected",
    [
        ("creator", False, True),
        ("administrator", False, True),
        ("member", False, True),
        ("restricted", True, True),
        ("restricted", False, False),
        ("left", False, False),
        ("kicked", False, False),
        ("unexpected", True, False),
    ],
)
def test_membership_rules_and_internal_identity(monkeypatch, status, is_member, expected):
    bot = FakeBot(status=status)
    bot.is_member = is_member
    user = _db_user()
    record = AsyncMock(return_value=user)
    monkeypatch.setattr(membership, "record_channel_membership", record)
    result = asyncio.run(
        ensure_required_channel_subscription(
            _message_event(bot),
            _settings(1234567890),
            I18nStub(),
            "en",
            AsyncMock(),
            user,
        )
    )
    assert result is expected
    assert record.await_args.args[1:5] == (7, 42, -1001234567890, expected)
    assert bot.calls == [(-1001234567890, 42)]


@pytest.mark.parametrize("message", ["chat not found", "user not found", "not enough rights"])
def test_api_error_does_not_record_false_membership(monkeypatch, message):
    bot = FakeBot(error=TelegramBadRequest(method=None, message=message))
    event = _message_event(bot)
    record = AsyncMock()
    monkeypatch.setattr(membership, "record_channel_membership", record)
    assert (
        asyncio.run(
            ensure_required_channel_subscription(
                event,
                _settings(1234567890),
                I18nStub(),
                "en",
                AsyncMock(),
                _db_user(),
            )
        )
        is False
    )
    record.assert_not_awaited()
    event.answer.assert_awaited_once_with("check failed")


def test_fresh_cache_expires_and_explicit_check_bypasses_positive(monkeypatch):
    async def run():
        bot = FakeBot(status="left")
        user = _db_user(verified=True, verified_for=-1001234567890)
        record = AsyncMock(return_value=user)
        monkeypatch.setattr(membership, "record_channel_membership", record)
        assert await membership.check_membership(AsyncMock(), bot, _settings(1234567890), user)
        assert not bot.calls
        assert (
            await membership.check_membership(
                AsyncMock(), bot, _settings(1234567890), user, force=True
            )
            is False
        )
        membership._recent.clear()
        user.channel_subscription_checked_at -= timedelta(seconds=901)
        assert (
            await membership.check_membership(AsyncMock(), bot, _settings(1234567890), user)
            is False
        )
        assert len(bot.calls) == 2

    asyncio.run(run())


def test_parallel_checks_share_request_and_manual_clicks_are_throttled(monkeypatch):
    async def run():
        bot = FakeBot()
        user = _db_user()
        monkeypatch.setattr(membership, "record_channel_membership", AsyncMock(return_value=user))
        results = await asyncio.gather(
            *[
                membership.check_membership(
                    AsyncMock(), bot, _settings(1234567890), user, force=True
                )
                for _ in range(10)
            ]
        )
        assert results == [True] * 10
        assert len(bot.calls) == 1
        assert await membership.check_membership(
            AsyncMock(), bot, _settings(1234567890), user, force=True
        )
        assert len(bot.calls) == 1
        assert await membership.check_membership(AsyncMock(), bot, _settings(1234567891), user)
        assert len(bot.calls) == 2

    asyncio.run(run())


def test_newer_leave_event_wins_over_in_flight_check(monkeypatch):
    async def run():
        bot = FakeBot()
        user = _db_user(verified=False, verified_for=-1001234567890)
        session = AsyncMock()
        monkeypatch.setattr(membership, "record_channel_membership", AsyncMock(return_value=None))
        assert (
            await membership.check_membership(session, bot, _settings(1234567890), user, force=True)
            is False
        )
        session.refresh.assert_awaited_once_with(user)

    asyncio.run(run())


def test_lost_bot_rights_does_not_trust_cached_positive(monkeypatch):
    monkeypatch.setattr(
        membership,
        "check_required_channel",
        AsyncMock(return_value=SimpleNamespace(status="missing_rights")),
    )
    assert (
        asyncio.run(
            membership.check_membership(
                AsyncMock(),
                FakeBot(),
                _settings(1234567890),
                _db_user(verified=True, verified_for=-1001234567890),
            )
        )
        is None
    )


def test_join_prompt_prefers_link_resolved_from_required_channel(monkeypatch):
    bot = FakeBot(status="left", chat=SimpleNamespace(username="actual_channel"))
    event = _message_event(bot)
    user = _db_user()
    monkeypatch.setattr(membership, "record_channel_membership", AsyncMock(return_value=user))
    assert (
        asyncio.run(
            ensure_required_channel_subscription(
                event,
                _settings(1234567890, "https://t.me/unrelated_bot"),
                I18nStub(),
                "en",
                AsyncMock(),
                user,
            )
        )
        is False
    )
    assert (
        event.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].url
        == "https://t.me/actual_channel"
    )
