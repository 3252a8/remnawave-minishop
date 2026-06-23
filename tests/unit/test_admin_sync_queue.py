"""Verifies that the admin sync endpoint hands work to the worker via Redis.

After the container split, /api/admin/sync no longer runs ``perform_sync``
in-process; it enqueues a ``panel_sync`` event onto the webhook queue and
returns a fast ack. These tests pin that contract.
"""

import json
import unittest
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import patch

from aiohttp import web

# Importing the facade populates each admin_api_impl submodule's globals with
# helpers like ``_require_admin_user_id`` and ``_ok``/``_error``. Without this
# side effect, ``sync_module._require_admin_user_id`` does not exist yet.
import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.admin_api_impl import sync as sync_module


class _FakeRequest:
    """The shape ``admin_sync_route`` reads from the aiohttp request."""

    def __init__(self, settings: SimpleNamespace, admin_telegram_id: int = 42) -> None:
        self.app = {"settings": settings}
        self._store = {"admin_telegram_id": admin_telegram_id}

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)


def _make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        ADMIN_IDS=[42],
        REDIS_KEY_PREFIX="shop",
        WEBHOOK_QUEUE_NAME="webhook-events",
        REDIS_URL="redis://r:6379/0",
    )


def _parse(response: web.Response) -> dict:
    return json.loads(response.body.decode())


def _patch_admin_auth(monkeypatch_target: Any) -> None:
    """``_require_admin_user_id`` looks up session state we don't have here."""
    monkeypatch_target.side_effect = lambda request: int(request.get("admin_telegram_id"))


class AdminSyncQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_queued_when_redis_accepts_event(self):
        recorded: List[dict] = []

        async def fake_enqueue(settings, provider, payload, *, event_id=None):
            recorded.append(
                {
                    "settings": settings,
                    "provider": provider,
                    "payload": payload,
                    "event_id": event_id,
                }
            )
            return True

        with (
            patch.object(sync_module, "enqueue_webhook_event", fake_enqueue),
            patch.object(sync_module, "_require_admin_user_id") as auth,
        ):
            _patch_admin_auth(auth)
            response = await sync_module.admin_sync_route(_FakeRequest(_make_settings()))

        self.assertEqual(response.status, 200)
        body = _parse(response)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"], {"status": "queued"})

        self.assertEqual(len(recorded), 1)
        entry = recorded[0]
        self.assertEqual(entry["provider"], "panel_sync")
        self.assertEqual(entry["payload"], {"requested_by": 42})
        # event_id=None lets Redis enqueue every admin request (no dedupe key).
        self.assertIsNone(entry["event_id"])

    async def test_returns_503_when_queue_is_unavailable(self):
        async def fake_enqueue(settings, provider, payload, *, event_id=None):
            return False

        with (
            patch.object(sync_module, "enqueue_webhook_event", fake_enqueue),
            patch.object(sync_module, "_require_admin_user_id") as auth,
        ):
            _patch_admin_auth(auth)
            response = await sync_module.admin_sync_route(_FakeRequest(_make_settings()))

        self.assertEqual(response.status, 503)
        body = _parse(response)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "queue_unavailable")

    async def test_non_admin_is_rejected_before_enqueueing(self):
        async def fake_enqueue(*args, **kwargs):
            raise AssertionError("enqueue must not be called for non-admin requests")

        def deny(_request):
            raise web.HTTPForbidden(
                text=json.dumps({"ok": False, "error": "forbidden"}),
                content_type="application/json",
            )

        with (
            patch.object(sync_module, "enqueue_webhook_event", fake_enqueue),
            patch.object(sync_module, "_require_admin_user_id", side_effect=deny),
        ):
            with self.assertRaises(web.HTTPForbidden):
                await sync_module.admin_sync_route(_FakeRequest(_make_settings()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
