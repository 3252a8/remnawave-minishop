"""Bounded JSON reads with identical destination policy in sync and async flows."""

import http.client
import json
import ssl
from urllib.parse import urljoin, urlsplit

from aiohttp import ClientSession, ClientTimeout, TCPConnector

from bot.utils.outbound_network import (
    GuardedResolver,
    OutboundPolicy,
    connect_socket,
    outbound_trace,
)

_MAX_JSON_BYTES = 1024 * 1024


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, timeout: float, policy: OutboundPolicy) -> None:
        super().__init__(host, port, timeout=timeout)
        self.policy = policy
        self.connect_timeout = timeout

    def connect(self) -> None:
        self.sock = connect_socket(self.policy, self.host, self.port, self.connect_timeout)


class _PinnedHTTPSConnection(_PinnedHTTPConnection):
    def connect(self) -> None:
        connection = connect_socket(self.policy, self.host, self.port, self.connect_timeout)
        try:
            self.sock = ssl.create_default_context().wrap_socket(
                connection, server_hostname=self.host
            )
        except BaseException:
            connection.close()
            raise


def fetch_json_sync(url: str, *, timeout: float, policy: OutboundPolicy) -> object:
    for _ in range(6):
        policy.check_url(url)
        parsed = urlsplit(url)
        host = parsed.hostname
        assert host is not None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        connection_type = (
            _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
        )
        connection = connection_type(host, port, timeout, policy)
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("GET", path, headers={"Accept": "application/json"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("invalid_outbound_redirect")
                url = urljoin(url, location)
                continue
            if not 200 <= response.status < 300:
                raise ValueError("outbound_http_error")
            body = response.read(_MAX_JSON_BYTES + 1)
            if len(body) > _MAX_JSON_BYTES:
                raise ValueError("outbound_response_too_large")
            payload: object = json.loads(body)
            return payload
        finally:
            connection.close()
    raise ValueError("too_many_outbound_redirects")


async def fetch_json(url: str, *, total_seconds: float, policy: OutboundPolicy) -> object:
    policy.check_url(url)
    async with (
        ClientSession(
            timeout=ClientTimeout(total=total_seconds),
            connector=TCPConnector(resolver=GuardedResolver(policy)),
            trace_configs=[outbound_trace(policy)],
        ) as session,
        session.get(url) as response,
    ):
        if not 200 <= response.status < 300:
            raise ValueError("outbound_http_error")
        body = bytearray()
        while len(body) <= _MAX_JSON_BYTES:
            chunk = await response.content.read(min(65536, _MAX_JSON_BYTES + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        if len(body) > _MAX_JSON_BYTES:
            raise ValueError("outbound_response_too_large")
        payload: object = json.loads(body)
        return payload
