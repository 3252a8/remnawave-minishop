import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_api_impl import broadcast as broadcast_route_module
from bot.app.web.admin_api_impl.broadcast_content import (
    BroadcastValidationError,
    broadcast_promo_codes,
    email_links_for_buttons,
    normalize_broadcast_channels,
    resolve_broadcast_buttons,
    telegram_markup_for_buttons,
)
from bot.app.web.admin_api_impl.schemas import AdminBroadcastBody, AdminBroadcastButtonBody
from bot.middlewares.i18n import JsonI18n
from bot.services import broadcast_email_service
from bot.services.audience_segmentation import AudienceSegmentationService
from bot.services.broadcast_email_service import (
    BroadcastEmailRecipient,
    deliver_broadcast_emails,
)
from bot.services.email_templates import render_broadcast_email
from tests.support.settings_stub import settings_stub

REPO_ROOT = Path(__file__).resolve().parents[2]


def _button(**overrides):
    payload = {"kind": "url", "label": "Open", "url": "https://example.com", "promo_code": ""}
    payload.update(overrides)
    return AdminBroadcastButtonBody.model_validate(payload)


class _FakeBroadcastRequest:
    def __init__(self, payload: dict[str, object], app: dict[str, object]) -> None:
        self._payload = payload
        self.app = app

    async def json(self) -> dict[str, object]:
        return self._payload

    def get(self, key: str, default: object = None) -> object:
        return default


class _FakeSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _FakeSessionFactory:
    def __call__(self) -> _FakeSessionContext:
        return _FakeSessionContext()


class _FakeAudienceService:
    def has_target(self, target: str) -> bool:
        return target == "all"

    def is_target_available(self, target: str) -> bool:
        return target == "all"

    async def resolve_user_ids(self, target: str) -> list[int]:
        return [-555]


class _FakeQueue:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> None:
        self.messages.append(kwargs)


class BroadcastChannelsTest(unittest.TestCase):
    def test_orders_and_dedupes_known_channels(self):
        self.assertEqual(
            normalize_broadcast_channels(["email", "telegram", "email"]),
            ["telegram", "email"],
        )

    def test_empty_channels_rejected(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            normalize_broadcast_channels([])
        self.assertEqual(ctx.exception.code, "no_channels")

    def test_unknown_channel_rejected(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            normalize_broadcast_channels(["telegram", "sms"])
        self.assertEqual(ctx.exception.code, "invalid_channel")
        self.assertEqual(ctx.exception.detail, "sms")


class BroadcastBodyTest(unittest.TestCase):
    def test_defaults_keep_legacy_payload_working(self):
        body = AdminBroadcastBody.model_validate({"text": " hi ", "target": "ALL"})
        self.assertEqual(body.text, "hi")
        self.assertEqual(body.channels, ["telegram"])
        self.assertEqual(body.buttons, [])
        self.assertEqual(body.email_subject, "")

    def test_channels_accept_string_and_null(self):
        self.assertEqual(
            AdminBroadcastBody.model_validate({"channels": "email"}).channels, ["email"]
        )
        self.assertEqual(
            AdminBroadcastBody.model_validate({"channels": None}).channels, ["telegram"]
        )


class BroadcastButtonsTest(unittest.TestCase):
    def setUp(self):
        self.settings = settings_stub(SUBSCRIPTION_MINI_APP_URL="https://app.example.test/")

    def resolve(self, buttons, *, bot_username="demo_bot", settings=None):
        return resolve_broadcast_buttons(
            buttons,
            settings=settings or self.settings,
            bot_username=bot_username,
        )

    def test_url_button_passes_through(self):
        resolved = self.resolve([_button()])
        self.assertEqual(resolved[0].url, "https://example.com")
        self.assertEqual(resolved[0].label, "Open")

    def test_url_button_requires_http_scheme(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve([_button(url="javascript:alert(1)")])
        self.assertEqual(ctx.exception.code, "button_url_invalid")

    def test_url_button_requires_url(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve([_button(url="")])
        self.assertEqual(ctx.exception.code, "button_url_required")

    def test_promo_bot_builds_start_deeplink(self):
        resolved = self.resolve(
            [_button(kind="promo_bot", promo_code="SUMMER25", url="")],
            bot_username="@demo_bot",
        )
        self.assertEqual(resolved[0].url, "https://t.me/demo_bot?start=promo_SUMMER25")
        self.assertEqual(resolved[0].promo_code, "SUMMER25")

    def test_promo_bot_requires_bot_username(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve(
                [_button(kind="promo_bot", promo_code="SUMMER25", url="")],
                bot_username="your_bot_username",
            )
        self.assertEqual(ctx.exception.code, "bot_username_unavailable")

    def test_promo_webapp_prefers_mini_app_url_and_opens_as_web_app(self):
        resolved = self.resolve([_button(kind="promo_webapp", promo_code="SUMMER25", url="")])
        self.assertEqual(resolved[0].url, "https://app.example.test/?startapp=promo_SUMMER25")
        self.assertEqual(
            resolved[0].telegram_web_app_url,
            "https://app.example.test/?startapp=promo_SUMMER25",
        )

    def test_promo_webapp_falls_back_to_startapp_deeplink(self):
        settings = settings_stub(SUBSCRIPTION_MINI_APP_URL="")
        resolved = self.resolve(
            [_button(kind="promo_webapp", promo_code="SUMMER25", url="")],
            settings=settings,
        )
        self.assertEqual(resolved[0].url, "https://t.me/demo_bot?startapp=promo_SUMMER25")
        self.assertIsNone(resolved[0].telegram_web_app_url)

    def test_promo_webapp_http_mini_app_uses_startapp_deeplink(self):
        # Telegram rejects http:// web_app targets; keep the Mini App context
        # via the t.me startapp deep link instead.
        settings = settings_stub(SUBSCRIPTION_MINI_APP_URL="http://app.example.test/")
        resolved = self.resolve(
            [_button(kind="promo_webapp", promo_code="SUMMER25", url="")],
            settings=settings,
        )
        self.assertEqual(resolved[0].url, "https://t.me/demo_bot?startapp=promo_SUMMER25")
        self.assertIsNone(resolved[0].telegram_web_app_url)

    def test_promo_webapp_without_any_entrypoint_rejected(self):
        settings = settings_stub(SUBSCRIPTION_MINI_APP_URL="")
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve(
                [_button(kind="promo_webapp", promo_code="SUMMER25", url="")],
                bot_username="",
                settings=settings,
            )
        self.assertEqual(ctx.exception.code, "webapp_url_unavailable")

    def test_promo_code_charset_enforced(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve([_button(kind="promo_bot", promo_code="ЛЕТО", url="")])
        self.assertEqual(ctx.exception.code, "button_promo_code_invalid")

    def test_label_required_and_bounded(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve([_button(label="")])
        self.assertEqual(ctx.exception.code, "button_label_required")
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve([_button(label="x" * 65)])
        self.assertEqual(ctx.exception.code, "button_label_too_long")

    def test_too_many_buttons_rejected(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve([_button() for _ in range(5)])
        self.assertEqual(ctx.exception.code, "too_many_buttons")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(BroadcastValidationError) as ctx:
            self.resolve([_button(kind="callback")])
        self.assertEqual(ctx.exception.code, "button_kind_invalid")

    def test_markup_and_email_links_mirror_buttons(self):
        resolved = self.resolve(
            [
                _button(),
                _button(kind="promo_bot", label="Activate", promo_code="GIFT", url=""),
                _button(kind="promo_webapp", label="In app", promo_code="GIFT", url=""),
            ]
        )
        markup = telegram_markup_for_buttons(resolved)
        assert markup is not None
        self.assertEqual(len(markup.inline_keyboard), 3)
        self.assertEqual(markup.inline_keyboard[1][0].text, "Activate")
        self.assertEqual(markup.inline_keyboard[1][0].url, "https://t.me/demo_bot?start=promo_GIFT")
        web_app_button = markup.inline_keyboard[2][0]
        self.assertIsNone(web_app_button.url)
        assert web_app_button.web_app is not None
        self.assertEqual(
            web_app_button.web_app.url,
            "https://app.example.test/?startapp=promo_GIFT",
        )
        self.assertIsNone(telegram_markup_for_buttons([]))
        self.assertEqual(
            email_links_for_buttons(resolved),
            [
                ("Open", "https://example.com"),
                ("Activate", "https://t.me/demo_bot?start=promo_GIFT"),
                ("In app", "https://app.example.test/?startapp=promo_GIFT"),
            ],
        )
        self.assertEqual(broadcast_promo_codes(resolved), ["GIFT"])


class AdminsAudienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_admins_target_resolves_without_db(self):
        service = AudienceSegmentationService(
            cast(sessionmaker, None),
            admin_ids=[10, 20, 10],
        )
        self.assertEqual(await service.resolve_user_ids("admins"), [10, 20])


class AdminBroadcastRouteTest(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_audience_is_rejected_instead_of_broadcasting_to_all(self):
        request = _FakeBroadcastRequest(
            {
                "target": "segment:missing",
                "text": "Hello",
                "channels": ["telegram"],
                "buttons": [],
            },
            {
                "settings": settings_stub(),
                "async_session_factory": _FakeSessionFactory(),
                "i18n": None,
                "bot_username": "demo_bot",
            },
        )

        with (
            patch.object(broadcast_route_module, "_require_admin_user_id", return_value=999),
            patch.object(
                broadcast_route_module,
                "_resolve_audience_service",
                return_value=AudienceSegmentationService(cast(sessionmaker, None)),
            ),
            patch.object(broadcast_route_module, "get_queue_manager", return_value=_FakeQueue()),
        ):
            response = await broadcast_route_module.admin_broadcast_route(cast(Any, request))

        self.assertEqual(response.status, 400)
        self.assertEqual(json.loads(response.text)["error"], "invalid_audience")

    async def test_linked_email_user_uses_telegram_id_for_telegram_delivery(self):
        settings = settings_stub(email_auth_configured=True)
        request = _FakeBroadcastRequest(
            {
                "target": "all",
                "text": "Hello",
                "channels": ["telegram", "email"],
                "email_subject": "Subject",
                "buttons": [],
            },
            {
                "settings": settings,
                "async_session_factory": _FakeSessionFactory(),
                "i18n": None,
                "bot_username": "demo_bot",
            },
        )
        queue = _FakeQueue()
        scheduled: list[dict[str, Any]] = []

        def schedule_emails(**kwargs: Any) -> int:
            scheduled.append(kwargs)
            recipients = cast(list[BroadcastEmailRecipient], kwargs["recipients"])
            return len(recipients)

        with (
            patch.object(broadcast_route_module, "_require_admin_user_id", return_value=999),
            patch.object(
                broadcast_route_module,
                "_resolve_audience_service",
                return_value=_FakeAudienceService(),
            ),
            patch.object(broadcast_route_module, "get_queue_manager", return_value=queue),
            patch.object(
                broadcast_route_module.user_dal,
                "get_telegram_recipients_for_broadcast",
                AsyncMock(return_value=[(-555, 123456789)]),
            ) as telegram_recipients,
            patch.object(
                broadcast_route_module.user_dal,
                "get_email_recipients_for_broadcast",
                AsyncMock(return_value=[(-555, "linked@example.com", "ru")]),
            ) as email_recipients,
            patch.object(
                broadcast_route_module.message_log_dal,
                "create_message_log",
                AsyncMock(),
            ),
            patch.object(
                broadcast_route_module,
                "schedule_broadcast_emails",
                side_effect=schedule_emails,
            ),
        ):
            response = await broadcast_route_module.admin_broadcast_route(cast(Any, request))

        self.assertEqual(response.status, 200)
        self.assertEqual(queue.messages[0]["chat_id"], 123456789)
        self.assertEqual(queue.messages[0]["text"], "Hello")
        self.assertEqual(scheduled[0]["recipients"][0].user_id, -555)
        self.assertEqual(scheduled[0]["recipients"][0].email, "linked@example.com")
        telegram_recipients.assert_awaited_once()
        email_recipients.assert_awaited_once()


class BroadcastEmailRenderTest(unittest.TestCase):
    def setUp(self):
        self.settings = settings_stub(WEBAPP_TITLE="Minishop", WEBAPP_LOGO_URL="")
        self.i18n = JsonI18n(str(REPO_ROOT / "locales"), default="en")

    def test_buttons_rendered_in_html_and_text(self):
        content = render_broadcast_email(
            self.settings,
            language_code="en",
            subject="",
            message_text="Hello <b>world</b>",
            buttons=[("Activate", "https://t.me/demo_bot?start=promo_GIFT")],
            i18n=self.i18n,
        )
        self.assertEqual(content.subject, "Service news")
        self.assertIn("https://t.me/demo_bot?start=promo_GIFT", content.html)
        self.assertIn("Activate", content.html)
        self.assertIn("<strong>world</strong>", content.html)
        self.assertIn("Activate: https://t.me/demo_bot?start=promo_GIFT", content.text)

    def test_custom_subject_wins(self):
        content = render_broadcast_email(
            self.settings,
            language_code="en",
            subject="Summer sale",
            message_text="text",
            i18n=self.i18n,
        )
        self.assertEqual(content.subject, "Summer sale")


class BroadcastEmailDeliveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_counts_sent_and_failed(self):
        settings = settings_stub()
        recipients = [
            BroadcastEmailRecipient(user_id=1, email="a@example.com", language_code="ru"),
            BroadcastEmailRecipient(user_id=2, email="b@example.com", language_code="en"),
        ]
        fake_service = SimpleNamespace(
            send_rendered_email=AsyncMock(side_effect=[None, RuntimeError("smtp down")])
        )
        i18n = SimpleNamespace(gettext=lambda lang, key, **kwargs: key)
        with patch.object(broadcast_email_service, "EmailAuthService", return_value=fake_service):
            sent, failed = await deliver_broadcast_emails(
                settings=settings,
                i18n=i18n,
                recipients=recipients,
                subject="Hi",
                message_text="Hello",
                buttons=[("Open", "https://example.com")],
            )
        self.assertEqual((sent, failed), (1, 1))
        self.assertEqual(fake_service.send_rendered_email.await_count, 2)


if __name__ == "__main__":
    unittest.main()
