import unittest

from bot.payment_providers.shared.http_client import HttpClientMixin


class _DummyHttpClient(HttpClientMixin):
    def __init__(self):
        self._init_http_client(total_timeout=20)


class PaymentHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_client_does_not_reuse_provider_tcp_connections(self):
        client = _DummyHttpClient()
        try:
            session = await client._get_session()
            self.assertTrue(session.connector.force_close)
        finally:
            await client.close()
