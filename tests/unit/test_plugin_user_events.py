from __future__ import annotations

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from bot.infra import events
from bot.plugins import PluginContext, user_events
from config.settings import Settings


class PluginUserEventsTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        events.reset_subscribers()
        self.factory = MagicMock()
        self.session = object()
        self.factory.return_value.__aenter__ = AsyncMock(return_value=self.session)
        self.ctx = PluginContext(
            settings=Settings(
                _env_file=None,
                BOT_TOKEN="x",
                POSTGRES_USER="u",
                POSTGRES_PASSWORD="p",
                ADMIN_IDS="1",
            ),
            session_factory=self.factory,
        )
        self.user = SimpleNamespace(username="alice", first_name="Alice")
        self.addCleanup(events.reset_subscribers)

    async def test_audits_once_and_keeps_original_subscriber_contract(self) -> None:
        subscriber = AsyncMock()
        second_subscriber = AsyncMock()
        events.subscribe("sample.completed", subscriber)
        events.subscribe("sample.completed", second_subscriber)
        payload = {"user_id": -42, "token": "private", "email": "private@example.test"}
        with (
            patch.object(user_events.user_dal, "get_user_by_id", AsyncMock(return_value=self.user)),
            patch.object(user_events.message_log_dal, "create_message_log", AsyncMock()) as write,
        ):
            await self.ctx.emit_event("sample", "sample.completed", payload, content="Completed")

        write.assert_awaited_once()
        assert write.await_args is not None
        log = write.await_args.args[1]
        self.assertEqual(log["user_id"], -42)
        self.assertEqual(log["event_type"], "plugin:sample:sample.completed")
        self.assertEqual(log["content"], "Completed")
        self.assertFalse(log["is_admin_event"])
        self.assertNotIn("raw_update_preview", log)
        self.assertNotIn("private", str(log))
        for handler in (subscriber, second_subscriber):
            handler.assert_awaited_once_with("sample.completed", payload)
            assert handler.await_args is not None
            self.assertIs(handler.await_args.args[1], payload)

    async def test_default_summary_does_not_copy_payload(self) -> None:
        with (
            patch.object(user_events.user_dal, "get_user_by_id", AsyncMock(return_value=self.user)),
            patch.object(user_events.message_log_dal, "create_message_log", AsyncMock()) as write,
        ):
            await self.ctx.emit_event("sample", "sample.completed", {"user_id": 42, "secret": "x"})
        assert write.await_args is not None
        self.assertEqual(write.await_args.args[1]["content"], "sample.completed")

    async def test_unattributed_events_still_reach_subscribers_without_audit(self) -> None:
        subscriber = AsyncMock()
        events.subscribe("sample.completed", subscriber)
        with patch.object(user_events.message_log_dal, "create_message_log", AsyncMock()) as write:
            for user_id in (None, True, "42", 1.5, 2**63, -(2**63) - 1):
                await self.ctx.emit_event("sample", "sample.completed", {"user_id": user_id})
            self.ctx.session_factory = None
            await self.ctx.emit_event("sample", "sample.completed", {"user_id": 42})
        write.assert_not_awaited()
        self.assertEqual(subscriber.await_count, 7)

    async def test_missing_user_is_not_misattributed(self) -> None:
        subscriber = AsyncMock()
        events.subscribe("sample.completed", subscriber)
        with (
            patch.object(user_events.user_dal, "get_user_by_id", AsyncMock(return_value=None)),
            patch.object(user_events.message_log_dal, "create_message_log", AsyncMock()) as write,
        ):
            await self.ctx.emit_event("sample", "sample.completed", {"user_id": 42})
        write.assert_not_awaited()
        subscriber.assert_awaited_once()

    async def test_audit_failure_does_not_break_event_delivery(self) -> None:
        subscriber = AsyncMock()
        events.subscribe("sample.completed", subscriber)
        with (
            patch.object(
                user_events.user_dal, "get_user_by_id", AsyncMock(side_effect=RuntimeError)
            ),
            self.assertLogs(user_events.logger, level="ERROR"),
        ):
            await self.ctx.emit_event("sample", "sample.completed", {"user_id": 42})
        subscriber.assert_awaited_once()

    async def test_invalid_source_cannot_spoof_another_log_prefix(self) -> None:
        with patch.object(events, "emit", AsyncMock()) as emit:
            for plugin, event in (("", "sample"), ("a:b", "sample"), ("a\n", "sample"), ("a", "")):
                with self.assertRaises(ValueError):
                    await self.ctx.emit_event(plugin, event, {})
        emit.assert_not_awaited()
