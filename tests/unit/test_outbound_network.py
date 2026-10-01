import asyncio
import socket
from unittest.mock import patch

import pytest
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver

from bot.utils.outbound_network import (
    CredentialPolicy,
    GuardedResolver,
    OutboundPolicy,
    approved_endpoints,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "http://10.1.2.3/a",
        "http://169.254.169.254/latest",
        "http://[::1]/a",
        "http://[::ffff:127.0.0.1]/a",
        "file:///etc/passwd",
        "https://user:secret@public.test/a",
    ],
)
def test_unapproved_internal_or_non_http_targets_are_blocked(url: str) -> None:
    with pytest.raises(ValueError):
        OutboundPolicy().check_url(url)


def test_operator_approval_is_for_an_exact_endpoint() -> None:
    policy = OutboundPolicy(approved_endpoints(["http://10.1.2.3:8000/status"]))
    policy.check_url("http://10.1.2.3:8000/api")
    with pytest.raises(ValueError):
        policy.check_url("http://10.1.2.3:8001/api")


def test_dns_rebinding_is_checked_in_the_resolver_used_by_the_connection() -> None:
    async def run() -> None:
        answer: ResolveResult = {
            "hostname": "status.test",
            "host": "10.1.2.3",
            "port": 443,
            "family": socket.AF_INET,
            "proto": socket.IPPROTO_TCP,
            "flags": 0,
        }
        resolver = GuardedResolver(OutboundPolicy())
        try:
            with (
                patch.object(ThreadedResolver, "resolve", return_value=[answer]),
                pytest.raises(ValueError),
            ):
                await resolver.resolve("status.test", 443)
        finally:
            await resolver.close()

    asyncio.run(run())


def test_official_api_origin_does_not_implicitly_approve_private_dns_answers() -> None:
    policy = CredentialPolicy(["https://api.cloudpayments.ru"])
    with pytest.raises(ValueError):
        policy.check_address("api.cloudpayments.ru", 443, "10.0.0.2")
    with pytest.raises(ValueError):
        policy.check_url("http://api.cloudpayments.ru:443/orders")
