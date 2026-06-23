import unittest
from types import SimpleNamespace

from bot.payment_providers.shared.http_client import (
    HttpClientMixin,
    _should_retry_transport_error,
)


class _DummyHttpClient(HttpClientMixin):
    def __init__(self, total_timeout=20):
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
