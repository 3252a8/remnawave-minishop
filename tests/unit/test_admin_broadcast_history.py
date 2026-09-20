import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import BufferedInputFile
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services import admin_broadcast_delivery as delivery_module
from bot.services.admin_broadcast_delivery import AdminBroadcastDeliveryService
from bot.services.broadcast_personalization import BroadcastUserContext
from bot.utils.message_queue import MessageQueueManager, QueuedMessage, TelegramMessageQueue
from db.broadcast_models import AdminBroadcast, AdminBroadcastDelivery
from tests.support.settings_stub import settings_stub

REPO_ROOT = Path(__file__).resolve().parents[2]


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _SessionFactory:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class _Queue:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, **kwargs: Any) -> None:
        self.messages.append({"chat_id": chat_id, **kwargs})

    async def send_photo(self, chat_id: int, **kwargs: Any) -> None:
        self.messages.append({"chat_id": chat_id, **kwargs})


def _service(queue: _Queue | None = None) -> AdminBroadcastDeliveryService:
    settings = settings_stub(
        SUBSCRIPTION_MINI_APP_URL="https://app.example.test/",
        DEFAULT_LANGUAGE="ru",
    )
    return AdminBroadcastDeliveryService(
        settings=settings,
        session_factory=cast(sessionmaker, _SessionFactory()),
        i18n=JsonI18n(str(REPO_ROOT / "locales"), default="ru"),
        audience_service=cast(Any, SimpleNamespace(panel_service=None)),
        queue_manager=cast(Any, queue),
        bot_username="demo_bot",
    )


def _broadcast(**overrides: Any) -> AdminBroadcast:
    values: dict[str, Any] = {
        "broadcast_id": 1,
        "created_by_admin_id": 99,
        "target": "all",
        "channels": ["telegram", "email"],
        "exclude_blocked_telegram": False,
        "texts": {"ru": "Привет {first_name}", "en": "Hello {first_name}"},
        "email_subjects": {"ru": "Новости", "en": "News"},
        "buttons": [],
    }
    values.update(overrides)
    return cast(AdminBroadcast, SimpleNamespace(**values))


def _delivery(**overrides: Any) -> AdminBroadcastDelivery:
    values: dict[str, Any] = {
        "delivery_id": 1,
        "broadcast_id": 1,
        "user_id": 1,
        "channel": "telegram",
        "destination": "111",
        "language_code": "en",
    }
    values.update(overrides)
    return cast(AdminBroadcastDelivery, SimpleNamespace(**values))


class AdminBroadcastDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_photo_is_prepared_once_and_reused_for_all_recipients(self) -> None:
        queue = _Queue()
        service = _service(queue)
        stored = SimpleNamespace(path=REPO_ROOT / "pyproject.toml")
        photo = BufferedInputFile(b"prepared JPEG", filename="message.jpg")
        prepare = AsyncMock(return_value=photo)
        deliveries = [
            _delivery(),
            _delivery(delivery_id=2, user_id=2, destination="222"),
        ]
        with (
            patch.object(delivery_module, "load_message_image", AsyncMock(return_value=stored)),
            patch.object(delivery_module, "prepare_telegram_photo", prepare),
            patch.object(service, "_mark_queued", AsyncMock()),
            patch.object(delivery_module.broadcast_dal, "refresh_broadcast_stats", AsyncMock()),
        ):
            result = await service._queue_deliveries(
                _broadcast(image_id="1" * 32, texts={"en": "Hello"}),
                deliveries,
                [1, 2],
                ["telegram"],
            )

        prepare.assert_awaited_once_with(stored)
        self.assertEqual(result.queued, 2)
        self.assertEqual(len(queue.messages), 2)
        self.assertTrue(all(message["photo"] is photo for message in queue.messages))

    async def test_recipient_destinations_are_snapshotted_per_channel(self) -> None:
        captured: list[dict[str, Any]] = []

        async def add_deliveries(
            _session: object,
            _broadcast: AdminBroadcast,
            deliveries: list[dict[str, Any]],
        ) -> list[AdminBroadcastDelivery]:
            captured.extend(deliveries)
            return []

        telegram_recipients = AsyncMock(return_value=[(-555, 123456789)])
        with (
            patch.object(
                delivery_module.user_dal,
                "get_language_codes_for_broadcast",
                AsyncMock(return_value={-555: "ru"}),
            ),
            patch.object(
                delivery_module.user_dal,
                "get_telegram_recipients_for_broadcast",
                telegram_recipients,
            ),
            patch.object(
                delivery_module.user_dal,
                "get_email_recipients_for_broadcast",
                AsyncMock(return_value=[(-555, "linked@example.com", "ru")]),
            ),
            patch.object(
                delivery_module.broadcast_dal,
                "add_deliveries",
                side_effect=add_deliveries,
            ),
        ):
            await _service()._prepare_deliveries(
                _broadcast(),
                [-555],
                ["telegram", "email"],
            )

        self.assertEqual(
            [(item["channel"], item["destination"]) for item in captured],
            [("telegram", "123456789"), ("email", "linked@example.com")],
        )
        telegram_recipients.assert_awaited_once_with(
            unittest.mock.ANY,
            [-555],
            exclude_blocked=False,
        )

    async def test_blocked_filter_keeps_unknown_raw_ids_outside_the_database(self) -> None:
        result = SimpleNamespace(
            all=lambda: [
                (1, 101, "blocked", False, True),
                (2, 202, "enabled", False, True),
                (4, 404, "enabled", True, True),
                (5, 505, "enabled", False, False),
            ]
        )
        session = SimpleNamespace(execute=AsyncMock(return_value=result))

        recipients = await delivery_module.user_dal.get_telegram_recipients_for_broadcast(
            session,
            [1, 2, 303, 4, 5],
            exclude_blocked=True,
        )

        self.assertEqual(recipients, [(2, 202), (303, 303)])

    async def test_personalization_is_rendered_for_telegram_and_email(self) -> None:
        queue = _Queue()
        service = _service(queue)
        contexts = {
            1: BroadcastUserContext(user_id=1, first_name="Ann", language_code="en"),
            2: BroadcastUserContext(user_id=2, first_name="Борис", language_code="ru"),
        }
        scheduled: list[Any] = []

        def schedule(**kwargs: Any) -> int:
            scheduled.extend(kwargs["recipients"])
            return len(kwargs["recipients"])

        deliveries = [
            _delivery(delivery_id=1, user_id=1, destination="111", language_code="en"),
            _delivery(delivery_id=2, user_id=2, destination="222", language_code="ru"),
            _delivery(
                delivery_id=3,
                user_id=1,
                channel="email",
                destination="ann@example.test",
                language_code="en",
            ),
            _delivery(
                delivery_id=4,
                user_id=2,
                channel="email",
                destination="boris@example.test",
                language_code="ru",
            ),
        ]

        with (
            patch.object(
                delivery_module, "load_broadcast_contexts", AsyncMock(return_value=contexts)
            ),
            patch.object(delivery_module, "schedule_broadcast_emails", side_effect=schedule),
            patch.object(delivery_module.broadcast_dal, "mark_delivery_queued", AsyncMock()),
            patch.object(delivery_module.broadcast_dal, "refresh_broadcast_stats", AsyncMock()),
        ):
            result = await service._queue_deliveries(
                _broadcast(
                    buttons=[
                        {
                            "kind": "url",
                            "label": "Profile",
                            "url": "https://example.test/users/{user_id}",
                        }
                    ]
                ),
                deliveries,
                [1, 2],
                ["telegram", "email"],
            )

        self.assertEqual([item["text"] for item in queue.messages], ["Hello Ann", "Привет Борис"])
        self.assertEqual(
            [item["reply_markup"].inline_keyboard[0][0].url for item in queue.messages],
            ["https://example.test/users/1", "https://example.test/users/2"],
        )
        self.assertEqual([item.message_text for item in scheduled], ["Hello Ann", "Привет Борис"])
        self.assertEqual(
            [item.buttons for item in scheduled],
            [
                [("Profile", "https://example.test/users/1")],
                [("Profile", "https://example.test/users/2")],
            ],
        )
        self.assertEqual(result.queued, 2)
        self.assertEqual(result.email_queued, 2)

    async def test_image_and_text_are_queued_as_one_photo_with_caption(self) -> None:
        queue = _Queue()
        service = _service(queue)
        image = BufferedInputFile(b"prepared JPEG", filename="test-image.jpg")

        with (
            patch.object(service, "_mark_queued", AsyncMock()) as mark_queued,
            patch.object(service, "_mark_result", AsyncMock()) as mark_result,
        ):
            await service._queue_telegram(
                _delivery(),
                "Hello",
                [],
                image=image,
            )

            self.assertEqual(len(queue.messages), 1)
            queued = queue.messages[0]
            self.assertIs(queued["photo"], image)
            self.assertEqual(queued["caption"], "Hello")
            self.assertEqual(queued["parse_mode"], "HTML")
            self.assertIsNone(queued["reply_markup"])
            self.assertNotIn("text", queued)
            await queued["callback"](object())

        mark_queued.assert_awaited_once_with(1)
        mark_result.assert_awaited_once_with(1, success=True, error=None)


class MessageQueueDeliveryCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_photo_routes_delivery_callbacks_outside_bot_kwargs(self) -> None:
        photo_result = object()
        bot = SimpleNamespace(send_photo=AsyncMock(return_value=photo_result))
        manager = MessageQueueManager(cast(Bot, bot))
        success = AsyncMock()
        failure = AsyncMock()

        await manager.send_photo(
            42,
            photo="photo-id",
            callback=success,
            error_callback=failure,
        )
        if manager.user_queue._processing_task is not None:
            await manager.user_queue._processing_task

        bot.send_photo.assert_awaited_once_with(chat_id=42, photo="photo-id")
        success.assert_awaited_once_with(photo_result)
        failure.assert_not_awaited()

    async def test_failure_callback_receives_terminal_send_error(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("offline")))
        queue = TelegramMessageQueue(cast(Bot, bot), messages_per_second=1000)
        failures: list[str] = []

        async def on_failure(exc: Exception) -> None:
            failures.append(str(exc))

        await queue.add_message(
            QueuedMessage(
                chat_id=42,
                method_name="send_message",
                kwargs={"text": "Hello"},
                error_callback=on_failure,
            )
        )
        if queue._processing_task is not None:
            await queue._processing_task

        self.assertEqual(failures, ["offline"])
        self.assertEqual(queue.total_failed, 1)

    async def test_forbidden_delivery_is_logged_without_traceback(self) -> None:
        error = TelegramForbiddenError(
            method=SendMessage(chat_id=42, text="Hello"),
            message="Forbidden: bot was blocked by the user",
        )
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=error))
        queue = TelegramMessageQueue(cast(Bot, bot), messages_per_second=1000)
        failure = AsyncMock()

        with self.assertLogs("bot.utils.message_queue", level="INFO") as logs:
            await queue.add_message(
                QueuedMessage(
                    chat_id=42,
                    method_name="send_message",
                    kwargs={"text": "Hello"},
                    error_callback=failure,
                )
            )
            if queue._processing_task is not None:
                await queue._processing_task

        failure.assert_awaited_once_with(error)
        rendered_logs = "\n".join(logs.output)
        self.assertIn("chat_id=42", rendered_logs)
        self.assertNotIn("Traceback", rendered_logs)

    async def test_broadcast_failure_records_blocked_user_status(self) -> None:
        queue = _Queue()
        service = _service(queue)
        error = TelegramForbiddenError(
            method=SendMessage(chat_id=111, text="Hello"),
            message="Forbidden: bot was blocked by the user",
        )

        with (
            patch.object(
                delivery_module,
                "record_telegram_notification_failure",
                AsyncMock(return_value="blocked"),
            ) as record_failure,
            patch.object(service, "_mark_queued", AsyncMock()),
            patch.object(service, "_mark_result", AsyncMock()) as mark_result,
        ):
            await service._queue_telegram(_delivery(user_id=7), "Hello", [])
            await queue.messages[0]["error_callback"](error)

        record_failure.assert_awaited_once_with(service.session_factory, 7, error)
        mark_result.assert_awaited_once_with(1, success=False, error=str(error))
