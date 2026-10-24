import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramForbiddenError

from bot.services import required_channel_diagnostics as diagnostics
from tests.support.settings_stub import settings_stub


def test_rights_changes_recheck_and_throttle_role_owned_notifications(monkeypatch):
    async def run():
        diagnostics._states.clear()
        clock = [1000.0]
        monkeypatch.setattr(diagnostics.time, "monotonic", lambda: clock[0])
        bot = SimpleNamespace(
            id=123,
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
            send_message=AsyncMock(),
        )
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(one=lambda: (10, 2))),
            scalars=AsyncMock(return_value=[77]),
        )
        i18n = SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key)
        settings = settings_stub(REQUIRED_CHANNEL_ID=-1001234567890)
        now = datetime.now(UTC)
        initial = await diagnostics.check_required_channel(
            bot, settings, session=session, i18n=i18n
        )
        assert initial.status == "available"
        assert initial.checked_at is not None
        bot.send_message.assert_not_awaited()
        bot.get_chat_member.return_value = SimpleNamespace(status="member")
        kwargs = {"session": session, "i18n": i18n, "force": True, "event_order": (now, 10)}
        lost = await diagnostics.check_required_channel(bot, settings, **kwargs)
        assert lost.status == "missing_rights"
        bot.send_message.assert_awaited_once_with(77, "required_channel_status_changed")
        await diagnostics.check_required_channel(bot, settings, **kwargs)
        assert bot.get_chat_member.await_count == 2  # duplicate event does not recheck
        bot.get_chat_member.return_value = SimpleNamespace(status="administrator")
        restored = await diagnostics.check_required_channel(
            bot,
            settings,
            session=session,
            i18n=i18n,
            force=True,
            event_order=(now + timedelta(seconds=1), 11),
        )
        assert restored.status == "available"
        assert bot.send_message.await_count == 1
        clock[0] += 301
        await diagnostics.check_required_channel(
            bot, settings, session=session, i18n=i18n, force=True
        )
        assert bot.send_message.await_count == 2
        bot.get_chat_member.side_effect = TelegramForbiddenError(method=None, message="Forbidden")
        unavailable = await diagnostics.check_required_channel(bot, settings, force=True)
        assert unavailable.status == "unavailable"
        settings.REQUIRED_CHANNEL_ID = None
        assert (await diagnostics.check_required_channel(bot, settings)).status == "disabled"

    asyncio.run(run())
