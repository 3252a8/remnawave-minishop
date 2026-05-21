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

SECRET = "panel-shared-secret"


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _make_service():
    settings = SimpleNamespace(
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

    async def test_falls_back_to_background_task_when_redis_unavailable(self):
        service = _make_service()
        background_seen: List[Any] = []

        async def fake_enqueue(*args, **kwargs):
            return False

        async def fake_handle_event(event_name, user_payload):
            background_seen.append((event_name, user_payload))

        body = json.dumps({"name": "user.expired", "payload": {"telegramId": 7}}).encode()

        with (
            patch.object(pws, "enqueue_webhook_event", fake_enqueue),
            patch.object(service, "handle_event", fake_handle_event),
        ):
            response = await service.handle_webhook(body, _sign(body))
            # Yield to the event loop so the scheduled background task runs.
            await asyncio.sleep(0)

        self.assertEqual(response.status, 200)
        self.assertEqual(background_seen, [("user.expired", {"telegramId": 7})])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
