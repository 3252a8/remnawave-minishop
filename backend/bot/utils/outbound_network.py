"""Validate outbound destinations and the DNS answers actually used to connect."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from types import SimpleNamespace
from urllib.parse import urlsplit

from aiohttp import ClientSession, TraceConfig, TraceRequestRedirectParams, TraceRequestStartParams
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver
from yarl import URL

Endpoint = tuple[str, int]


def url_endpoint(url: str) -> Endpoint:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(ord(char) < 32 for char in url)
        ):
            raise ValueError("unsafe_outbound_url")
        return parsed.hostname.lower().rstrip("."), parsed.port or (
            443 if parsed.scheme == "https" else 80
        )
    except ValueError as exc:
        raise ValueError("unsafe_outbound_url") from exc


def approved_endpoints(urls: Iterable[str]) -> frozenset[Endpoint]:
    endpoints = set()
    for url in urls:
        try:
            endpoints.add(url_endpoint(url))
        except ValueError:
            continue
    return frozenset(endpoints)


class OutboundPolicy:
    def __init__(self, trusted: Iterable[Endpoint] = ()) -> None:
        self.trusted = frozenset(trusted)

    def check_address(self, host: str, port: int, address: str) -> None:
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        trusted = (host.lower().rstrip("."), port) in self.trusted
        if (
            ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or (ip.is_reserved and not ip.is_loopback)
        ):
            raise ValueError("unsafe_outbound_address")
        if not ip.is_global and not trusted:
            raise ValueError("unsafe_outbound_address")

    def check_url(self, url: str) -> None:
        host, port = url_endpoint(url)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return
        self.check_address(host, port, host)


def connect_socket(
    policy: OutboundPolicy,
    host: str,
    port: int,
    timeout: float,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    if not 0 < port <= 65535:
        raise ValueError("unsafe_outbound_port")
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
    for address in addresses:
        policy.check_address(host, port, address)
    error: OSError = OSError("No usable destination address")
    for address in addresses:
        try:
            return socket.create_connection((address, port), timeout, source_address)
        except OSError as exc:
            error = exc
    raise error


class GuardedResolver(ThreadedResolver):
    def __init__(self, policy: OutboundPolicy) -> None:
        super().__init__()
        self.policy = policy

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        answers = await super().resolve(host, port, family)
        for answer in answers:
            self.policy.check_address(host, port, answer["host"])
        return answers


def outbound_trace(policy: OutboundPolicy) -> TraceConfig:
    trace = TraceConfig()

    async def start(
        _session: ClientSession, _context: SimpleNamespace, params: TraceRequestStartParams
    ) -> None:
        policy.check_url(str(params.url))

    async def redirect(
        _session: ClientSession, _context: SimpleNamespace, params: TraceRequestRedirectParams
    ) -> None:
        response = params.response
        location = response.headers.get("Location") or response.headers.get("URI")
        if location:
            policy.check_url(str(response.url.join(URL(location))))

    trace.on_request_start.append(start)
    trace.on_request_redirect.append(redirect)
    return trace
