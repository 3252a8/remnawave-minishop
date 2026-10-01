import time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.dispatcher.event.bases import SkipHandler

from bot.handlers.user.subscription import core_device_names, core_status
from bot.handlers.user.subscription.core_common import _hwid_callback_token
from bot.states.user_states import UserDeviceRenameStates


class _FakeI18n:
    def gettext(self, lang, key, **kwargs):
        args = ", ".join(f"{name}={value}" for name, value in sorted(kwargs.items()))
        return f"{key}({args})"


SETTINGS = SimpleNamespace(DEFAULT_LANGUAGE="ru", MY_DEVICES_SECTION_ENABLED=True)
I18N_DATA = {"current_language": "ru", "i18n_instance": _FakeI18n()}
TOKEN = _hwid_callback_token("HW-1")


def _services(devices):
    subscription_service = SimpleNamespace(
        get_active_subscription_details=AsyncMock(
            return_value={"user_id": "panel-user", "max_devices": None}
        )
    )
    return subscription_service, SimpleNamespace(get_user_devices=AsyncMock(return_value=devices))


def _state(data=None):
    return SimpleNamespace(
        get_data=AsyncMock(return_value=data or {}),
        clear=AsyncMock(),
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )


class BotDeviceListTests(IsolatedAsyncioTestCase):
    async def test_list_shows_saved_names_escapes_panel_fields_and_offers_rename(self):
        subscription_service, panel_service = _services(
            [
                {
                    "hwid": "HW-1",
                    "deviceModel": "iPhone <15>",
                    "platform": "iOS",
                    "osVersion": "18",
                    "userAgent": "Happ/<1>",
                }
            ]
        )
        message = SimpleNamespace(answer=AsyncMock())
        with (
            patch.object(core_status, "_event_user_id", AsyncMock(return_value=42)),
            patch.object(
                core_status.device_name_dal,
                "get_device_names",
                AsyncMock(return_value={TOKEN: "Work <laptop>"}),
            ) as get_names,
            patch.object(
                core_status,
                "resolve_device_topup_availability",
                return_value=SimpleNamespace(allowed=False, reason=None),
            ),
        ):
            await core_status.my_devices_command_handler(
                message, I18N_DATA, SETTINGS, panel_service, subscription_service, object(), None
            )

        text = message.answer.await_args.args[0]
        self.assertIn("device_model=Work &lt;laptop&gt; · iPhone &lt;15&gt;", text)
        self.assertIn("user_agent=Happ/&lt;1&gt;", text)
        self.assertNotIn("<laptop>", text)
        get_names.assert_awaited_once()
        markup = message.answer.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("rename_device:list", callbacks)
        self.assertLess(
            callbacks.index("rename_device:list"), callbacks.index(f"disconnect_device:{TOKEN}")
        )


class BotDeviceRenameFlowTests(IsolatedAsyncioTestCase):
    def setUp(self):
        cache_patch = patch.object(core_device_names, "invalidate_webapp_user_caches", AsyncMock())
        self.invalidate_caches = cache_patch.start()
        self.addCleanup(cache_patch.stop)

    def _patches(self, names=None):
        self.save = AsyncMock()
        self.show_devices = AsyncMock()
        return (
            patch.object(
                core_device_names, "require_telegram_account_id", AsyncMock(return_value=42)
            ),
            patch.object(
                core_device_names, "message_from_user", return_value=SimpleNamespace(id=777)
            ),
            patch.object(core_device_names.device_name_dal, "set_device_name", self.save),
            patch.object(
                core_device_names.device_name_dal,
                "get_device_names",
                AsyncMock(return_value=names or {}),
            ),
            patch.object(core_device_names, "my_devices_command_handler", self.show_devices),
        )

    async def _send_name(self, text, state, settings=SETTINGS):
        subscription_service, panel_service = _services([{"hwid": "HW-1", "deviceModel": "Pixel"}])
        session = SimpleNamespace(commit=AsyncMock())
        message = SimpleNamespace(text=text, answer=AsyncMock())
        p1, p2, p3, p4, p5 = self._patches()
        with p1, p2, p3, p4, p5:
            await core_device_names.rename_device_name_message(
                message,
                state,
                settings,
                I18N_DATA,
                session,
                subscription_service,
                panel_service,
                None,
            )
        return message, session

    async def test_typed_name_is_normalized_saved_and_ends_the_prompt(self):
        state = _state({"device_rename_token": TOKEN, "device_rename_requested_at": time.time()})

        message, session = await self._send_name("  Work\n laptop ", state)

        self.save.assert_awaited_once_with(session, 42, TOKEN, "Work laptop")
        session.commit.assert_awaited_once()
        state.clear.assert_awaited_once()
        self.assertIn("rename_device_saved(name=Work laptop)", message.answer.await_args.args[0])
        self.show_devices.assert_awaited_once()
        self.invalidate_caches.assert_awaited_once_with(
            SETTINGS, 42, include_devices=True, include_me=False
        )

    async def test_disabled_section_releases_the_pending_message_without_saving(self):
        state = _state({"device_rename_token": TOKEN, "device_rename_requested_at": time.time()})
        settings = SimpleNamespace(DEFAULT_LANGUAGE="ru", MY_DEVICES_SECTION_ENABLED=False)

        with self.assertRaises(SkipHandler):
            await self._send_name("Unrelated message", state, settings)

        state.clear.assert_awaited_once()
        self.save.assert_not_awaited()
        self.invalidate_caches.assert_not_awaited()

    async def test_reset_refreshes_the_owners_webapp_device_cache(self):
        subscription_service, panel_service = _services([{"hwid": "HW-1"}])
        state = _state()
        session = SimpleNamespace(commit=AsyncMock())
        callback = SimpleNamespace(from_user=SimpleNamespace(id=777), answer=AsyncMock())
        p1, p2, p3, p4, p5 = self._patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch.object(
                core_device_names, "callback_data", return_value=f"rename_device:reset:{TOKEN}"
            ),
        ):
            await core_device_names.rename_device_reset_callback(
                callback,
                state,
                SETTINGS,
                I18N_DATA,
                session,
                subscription_service,
                panel_service,
                None,
            )

        self.save.assert_awaited_once_with(session, 42, TOKEN, "")
        session.commit.assert_awaited_once()
        self.invalidate_caches.assert_awaited_once_with(
            SETTINGS, 42, include_devices=True, include_me=False
        )

    async def test_disabled_section_rejects_an_old_reset_button(self):
        subscription_service, panel_service = _services([{"hwid": "HW-1"}])
        state = _state()
        session = SimpleNamespace(commit=AsyncMock())
        callback = SimpleNamespace(from_user=SimpleNamespace(id=777), answer=AsyncMock())
        settings = SimpleNamespace(DEFAULT_LANGUAGE="ru", MY_DEVICES_SECTION_ENABLED=False)
        p1, p2, p3, p4, p5 = self._patches()
        with p1, p2, p3, p4, p5:
            await core_device_names.rename_device_reset_callback(
                callback,
                state,
                settings,
                I18N_DATA,
                session,
                subscription_service,
                panel_service,
                None,
            )

        state.clear.assert_awaited_once()
        self.save.assert_not_awaited()
        panel_service.get_user_devices.assert_not_awaited()
        self.assertIn("my_devices_feature_disabled", callback.answer.await_args.args[0])

    async def test_too_long_name_keeps_waiting_for_another_one(self):
        state = _state({"device_rename_token": TOKEN, "device_rename_requested_at": time.time()})

        message, _ = await self._send_name("x" * 33, state)

        self.save.assert_not_awaited()
        state.clear.assert_not_awaited()
        self.assertIn("rename_device_invalid(max=32)", message.answer.await_args.args[0])

    async def test_forgotten_prompt_releases_the_message_to_other_handlers(self):
        state = _state(
            {"device_rename_token": TOKEN, "device_rename_requested_at": time.time() - 3600}
        )

        with self.assertRaises(SkipHandler):
            await self._send_name("hello support", state)

        state.clear.assert_awaited_once()
        self.save.assert_not_awaited()

    async def test_picking_an_owned_device_prompts_with_reset_when_named(self):
        subscription_service, panel_service = _services([{"hwid": "HW-1", "deviceModel": "Pixel"}])
        state = _state()
        shown = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())
        callback = SimpleNamespace(from_user=SimpleNamespace(id=777), answer=AsyncMock())
        p1, p2, p3, p4, p5 = self._patches(names={TOKEN: "Old <name>"})
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch.object(
                core_device_names, "callback_data", return_value=f"rename_device:pick:{TOKEN}"
            ),
            patch.object(core_device_names, "callback_message", return_value=shown),
        ):
            await core_device_names.rename_device_pick_callback(
                callback, state, SETTINGS, I18N_DATA, object(), subscription_service, panel_service
            )

        state.set_state.assert_awaited_once_with(UserDeviceRenameStates.waiting_for_name)
        self.assertEqual(state.update_data.await_args.kwargs["device_rename_token"], TOKEN)
        text = shown.edit_text.await_args.args[0]
        self.assertIn("device=Old &lt;name&gt;", text)
        rows = shown.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(rows[0][0].callback_data, f"rename_device:reset:{TOKEN}")
        self.assertEqual(rows[-1][0].callback_data, "rename_device:cancel")

    async def test_picking_someone_elses_device_is_refused(self):
        subscription_service, panel_service = _services([{"hwid": "HW-1"}])
        state = _state()
        callback = SimpleNamespace(from_user=SimpleNamespace(id=777), answer=AsyncMock())
        p1, p2, p3, p4, p5 = self._patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch.object(
                core_device_names, "callback_data", return_value="rename_device:pick:" + "0" * 32
            ),
        ):
            await core_device_names.rename_device_pick_callback(
                callback, state, SETTINGS, I18N_DATA, object(), subscription_service, panel_service
            )

        state.set_state.assert_not_awaited()
        self.assertIn("error_try_again", callback.answer.await_args.args[0])
