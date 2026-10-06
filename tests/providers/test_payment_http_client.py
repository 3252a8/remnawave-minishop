import unittest
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestServer

from bot.payment_providers.paykilla.config import PaykillaConfig
from bot.payment_providers.shared.http_client import (
    HttpClientMixin,
    _should_retry_transport_error,
)


class _DummyHttpClient(HttpClientMixin):
    def __init__(self, total_timeout=20, config=None):
        self.config = config
        self._init_http_client(total_timeout=total_timeout)


class PaymentHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_client_tracks_sent_headers_for_safe_retries(self):
        client = _DummyHttpClient()
        try:
            session = await client._get_session()
            self.assertFalse(session.connector.force_close)
            self.assertTrue(session.trace_configs)
        finally:
            await client.close()

    async def test_http_client_retries_only_before_headers_are_sent(self):
        self.assertTrue(_should_retry_transport_error(TimeoutError(), {"headers_sent": False}))
        self.assertFalse(_should_retry_transport_error(TimeoutError(), {"headers_sent": True}))

    async def test_http_client_applies_runtime_timeout_changes(self):
        settings = SimpleNamespace(PAYMENT_REQUEST_TIMEOUT_SECONDS=20)
        client = _DummyHttpClient(total_timeout=lambda: settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)
        try:
            first = await client._get_session()
            self.assertEqual(first.timeout.total, 20)
            self.assertIs(await client._get_session(), first)

            settings.PAYMENT_REQUEST_TIMEOUT_SECONDS = 5
            second = await client._get_session()
            self.assertIsNot(second, first)
            self.assertEqual(second.timeout.total, 5)
            # The replaced session must stay usable for in-flight requests;
            # it is closed later, and close() always sweeps it up.
            self.assertFalse(first.closed)
        finally:
            await client.close()
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    async def test_http_client_falls_back_to_default_timeout_on_bad_source(self):
        client = _DummyHttpClient(total_timeout=lambda: None)
        try:
            session = await client._get_session()
            self.assertEqual(session.timeout.total, 20.0)
        finally:
            await client.close()

    async def test_admin_api_url_change_updates_connections_and_keeps_keys_on_origin(self):
        received = []

        async def api(request):
            received.append(request.headers.get("X-API-Key"))
            return web.json_response({"host": request.host})

        first_app = web.Application()
        first_app.router.add_get("/api", api)
        second_app = web.Application()
        second_app.router.add_get("/api", api)
        first_server = TestServer(first_app)
        second_server = TestServer(second_app)
        await first_server.start_server()
        await second_server.start_server()
        config = PaykillaConfig()
        client = _DummyHttpClient(config=config)
        try:
            first_url = str(first_server.make_url("/api"))
            second_url = str(second_server.make_url("/api"))
            config.BASE_URL = first_url
            first = await client._get_session()
            async with first.get(first_url, headers={"X-API-Key": "test-key"}) as response:
                self.assertEqual(response.status, 200)
                await response.read()
            config.BASE_URL = second_url
            second = await client._get_session()
            self.assertIsNot(second, first)
            self.assertFalse(first.closed)
            async with second.get(second_url, headers={"X-API-Key": "test-key"}) as response:
                self.assertEqual(response.status, 200)
                await response.read()
            with self.assertRaises(ValueError):
                await second.get(first_url, headers={"X-API-Key": "test-key"})
            self.assertEqual(received, ["test-key", "test-key"])
        finally:
            await client.close()
            await first_server.close()
            await second_server.close()
