"""Behaviour of ``PanelWebhookService.handle_webhook``.

The service must:
  * reject requests without the configured shared secret or a missing/bad
    signature header — otherwise an attacker could forge panel events;
  * acknowledge an event with HTTP 200 once it is on the queue (the worker
    container does the heavy lifting);
  * fall back to in-process background dispatch when Redis is unreachable so
    a single-node deploy still processes events.
"""

import asyncio
import hashlib
import hmac
import json
import unittest
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import patch

from bot.services import panel_webhook_service as pws
from tests.support.settings_stub import settings_stub

SECRET = "panel-shared-secret"


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _make_service():
    settings = settings_stub(
        PANEL_WEBHOOK_SECRET=SECRET,
        SUBSCRIPTION_NOTIFICATIONS_ENABLED=True,
        SUBSCRIPTION_NOTIFY_DAYS_BEFORE=3,
        SUBSCRIPTION_NOTIFY_ON_EXPIRE=True,
        SUBSCRIPTION_NOTIFY_AFTER_EXPIRE=True,
        DEFAULT_LANGUAGE="ru",
        email_auth_configured=False,
    )
    # Build minimally with object() placeholders — handle_webhook does not
    # touch the bot/i18n/db/panel collaborators on its enqueue path.
    return pws.PanelWebhookService(
        bot=object(),
        settings=settings,
        i18n=object(),
        async_session_factory=object(),
        panel_service=object(),
    )


class HandleWebhookSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_unauthorized_when_secret_not_configured(self):
        service = _make_service()
        service.settings.PANEL_WEBHOOK_SECRET = ""
        response = await service.handle_webhook(b"{}", _sign(b"{}"))
        self.assertEqual(response.status, 401)

    async def test_unauthorized_when_signature_header_missing(self):
        service = _make_service()
        response = await service.handle_webhook(b'{"name":"user.expired"}', None)
        self.assertEqual(response.status, 401)

    async def test_unauthorized_on_signature_mismatch(self):
        service = _make_service()
        body = b'{"name":"user.expired"}'
        response = await service.handle_webhook(body, "deadbeef")
        self.assertEqual(response.status, 401)

    async def test_bad_request_for_invalid_json(self):
        service = _make_service()
        body = b"not-json"
        response = await service.handle_webhook(body, _sign(body))
        self.assertEqual(response.status, 400)

    async def test_ok_no_event_when_name_missing(self):
        service = _make_service()
        body = json.dumps({"payload": {"telegramId": 1}}).encode()
        response = await service.handle_webhook(body, _sign(body))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.text, "ok_no_event")


class HandleWebhookQueueingTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueues_to_redis_and_returns_ok(self):
        service = _make_service()
        captured: List[dict] = []

        async def fake_enqueue(settings, provider, payload, *, event_id=None):
            captured.append({"provider": provider, "payload": payload, "event_id": event_id})
            return True

        body = json.dumps(
            {
                "name": "user.expires_in_24_hours",
                "payload": {"telegramId": 99, "uuid": "abc"},
            }
        ).encode()

        with patch.object(pws, "enqueue_webhook_event", fake_enqueue):
            response = await service.handle_webhook(body, _sign(body))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.text, "ok")
        self.assertEqual(len(captured), 1)
        entry = captured[0]
        self.assertEqual(entry["provider"], "panel")
        self.assertEqual(entry["payload"]["event"], "user.expires_in_24_hours")
        self.assertEqual(entry["payload"]["user"], {"telegramId": 99, "uuid": "abc"})
        # event_id combines event name with the strongest available identifier.
        self.assertEqual(entry["event_id"], "user.expires_in_24_hours:99")

    async def test_enqueues_new_expiration_event_with_signed_hours_meta(self):
        service = _make_service()
        captured: List[dict] = []

        async def fake_enqueue(settings, provider, payload, *, event_id=None):
            captured.append({"provider": provider, "payload": payload, "event_id": event_id})
            return True

        body = json.dumps(
            {
                "event": "user.expiration",
                "data": {
                    "user": {"telegramId": 99, "uuid": "abc"},
                    "_meta": {"expiration": -12},
                },
            }
        ).encode()

        with patch.object(pws, "enqueue_webhook_event", fake_enqueue):
            response = await service.handle_webhook(body, _sign(body))

        self.assertEqual(response.status, 200)
        entry = captured[0]
        self.assertEqual(entry["payload"]["event"], "user.expiration")
        self.assertEqual(entry["payload"]["user"], {"telegramId": 99, "uuid": "abc"})
        self.assertEqual(entry["payload"]["meta"], {"expiration": -12})
        self.assertEqual(entry["event_id"], "user.expiration:99:expiration:-12")

    async def test_expiration_event_id_keeps_different_offsets_distinct(self):
        service = _make_service()
        self.assertEqual(
            service._webhook_event_id(
                "user.expiration",
                {"telegramId": 99, "uuid": "abc"},
                {"expiration": -1},
            ),
            "user.expiration:99:expiration:-1",
        )
        self.assertEqual(
            service._webhook_event_id(
                "user.expiration",
                {"telegramId": 99, "uuid": "abc"},
                {"expiration": 72},
            ),
            "user.expiration:99:expiration:72",
        )

    async def test_falls_back_to_background_task_when_redis_unavailable(self):
        service = _make_service()
        background_seen: List[Any] = []

        async def fake_enqueue(*args, **kwargs):
            return False

        async def fake_handle_event(event_name, user_payload, *, meta=None):
            background_seen.append((event_name, user_payload, meta))

        body = json.dumps({"name": "user.expired", "payload": {"telegramId": 7}}).encode()

        with (
            patch.object(pws, "enqueue_webhook_event", fake_enqueue),
            patch.object(service, "handle_event", fake_handle_event),
        ):
            response = await service.handle_webhook(body, _sign(body))
            # Yield to the event loop so the scheduled background task runs.
            await asyncio.sleep(0)

        self.assertEqual(response.status, 200)
        self.assertEqual(background_seen, [("user.expired", {"telegramId": 7}, {})])


class ExpirationStageMappingTests(unittest.TestCase):
    def test_legacy_offsets_keep_legacy_notification_stages(self):
        stage = pws.PanelWebhookService._stage_for_event(
            "user.expiration",
            {"uuid": "abc"},
            {"expiration": -72},
        )

        self.assertIsNotNone(stage)
        self.assertEqual(stage.key, "before_3d")
        self.assertEqual(stage.message_key, "subscription_72h_notification")

    def test_custom_negative_offset_uses_hours_before_notification(self):
        stage = pws.PanelWebhookService._stage_for_event(
            "user.expiration",
            {"uuid": "abc"},
            {"expiration": "-12"},
        )

        self.assertIsNotNone(stage)
        self.assertEqual(stage.key, "before_12h")
        self.assertEqual(stage.message_key, "subscription_hours_notification")
        self.assertEqual(stage.hours_before, 12)

    def test_custom_positive_offset_uses_hours_after_notification(self):
        stage = pws.PanelWebhookService._stage_for_event(
            "user.expiration",
            {"uuid": "abc"},
            {"expiration": 72},
        )

        self.assertIsNotNone(stage)
        self.assertEqual(stage.key, "expired_72h_after")
        self.assertEqual(stage.message_key, "subscription_expired_hours_ago_notification")
        self.assertEqual(stage.hours_after, 72)


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSessionFactory:
    def __call__(self):
        return _FakeSessionContext()


class HandleEventLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_event_is_logged_as_ignored(self):
        service = _make_service()

        with self.assertLogs(level="INFO") as logs:
            await service.handle_event(
                "user.modified",
                {"uuid": "panel-user-1", "email": "client@example.com"},
            )

        message = "\n".join(logs.output)
        self.assertIn("Panel webhook event user.modified ignored", message)
        self.assertIn("event is not used for subscription notifications", message)
        self.assertIn("panel_uuid=panel-user-1", message)
        self.assertIn("email=cl***@example.com", message)

    async def test_missing_subscription_warning_includes_payload_context(self):
        service = _make_service()
        service.async_session_factory = _FakeSessionFactory()

        async def fake_user_for_payload(session, user_payload):
            return SimpleNamespace(user_id=123, language_code=None)

        async def fake_subscription_for_payload(session, user_payload, db_user):
            return None

        with (
            patch.object(service, "_user_for_payload", fake_user_for_payload),
            patch.object(service, "_subscription_for_payload", fake_subscription_for_payload),
            self.assertLogs(level="WARNING") as logs,
        ):
            await service.handle_event(
                "user.expired",
                {
                    "uuid": "panel-user-2",
                    "email": "person@example.com",
                    "expireAt": "2026-05-30T07:18:32Z",
                },
            )

        message = "\n".join(logs.output)
        self.assertIn("cannot be matched to a local subscription", message)
        self.assertIn("notification skipped", message)
        self.assertIn("telegramId=N/A", message)
        self.assertIn("panel_uuid=panel-user-2", message)
        self.assertIn("email=pe***@example.com", message)
        self.assertIn("expireAt=2026-05-30T07:18:32Z", message)
        self.assertIn("local_user_id=123", message)
        self.assertIn("subscription was deleted or not synced", message)


class HandleEventSupersessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_event_skipped_when_user_has_newer_active_subscription(self):
        service = _make_service()
        service.async_session_factory = _FakeSessionFactory()
        service.i18n = SimpleNamespace(gettext=lambda lang, key, **kwargs: key)
        sent: List[Any] = []

        async def fake_user_for_payload(session, user_payload):
            return SimpleNamespace(user_id=123, language_code="ru")

        async def fake_subscription_for_payload(session, user_payload, db_user):
            return SimpleNamespace(
                subscription_id=244,
                user_id=123,
                end_date=None,
            )

        async def fake_send_stage(*args, **kwargs):
            sent.append((args, kwargs))

        async def fake_has_active(session, user_id, after, *, exclude_subscription_id=None):
            # The user renewed into another active subscription row.
            return True

        with (
            patch.object(service, "_user_for_payload", fake_user_for_payload),
            patch.object(service, "_subscription_for_payload", fake_subscription_for_payload),
            patch.object(service.lifecycle_notifications, "send_stage", fake_send_stage),
            patch.object(
                pws.subscription_dal,
                "user_has_active_subscription_after",
                fake_has_active,
            ),
            self.assertLogs(level="INFO") as logs,
        ):
            await service.handle_event(
                "user.expired_24_hours_ago",
                {"telegramId": 555, "uuid": "panel-user-3", "expireAt": "2026-06-16T00:00:00Z"},
            )

        self.assertEqual(sent, [])
        message = "\n".join(logs.output)
        self.assertIn("is superseded by a newer active subscription", message)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
