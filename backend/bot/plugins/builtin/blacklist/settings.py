"""Configuration values shared by the admin API and the worker."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from yarl import URL

from bot.plugins.capabilities import CORE_PLUGIN_CAPABILITIES
from bot.utils.outbound_network import OutboundPolicy

MAX_SOURCES = 20
MAX_URL_LENGTH = 2048
MAX_REFRESH_HOURS = 8760
SUPPORTS_USERS_TABLE = CORE_PLUGIN_CAPABILITIES.get("admin_users_table", 0) >= 1
_TRANSLATED_V6 = ipaddress.IPv6Network("64:ff9b::/96"), ipaddress.IPv6Network("64:ff9b:1::/48")
DEFAULT_SOURCES = (
    "https://raw.githubusercontent.com/Blin4ickUSE/ban-vpn/refs/heads/main/blacklist.txt",
    "https://raw.githubusercontent.com/BEDOLAGA-DEV/VPN-BLACKLIST/refs/heads/main/blacklist.txt",
)

EventName = Literal["register", "trial", "payment", "expired"]
EVENT_NAMES: tuple[EventName, ...] = ("register", "trial", "payment", "expired")


@dataclass(frozen=True)
class DisplaySettings:
    users: bool = True
    user_card: bool = True
    ticket: bool = True
    users_table: bool = True


@dataclass(frozen=True)
class Settings:
    sources: tuple[str, ...] = DEFAULT_SOURCES
    refresh_hours: int = 24
    display: DisplaySettings = DisplaySettings()
    chat_id: int | None = None
    topic_id: int | None = None
    events: tuple[EventName, ...] = ()


DEFAULT_SETTINGS = Settings()


class SourceURLValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SourceNetworkPolicy(OutboundPolicy):
    def check_address(self, host: str, port: int, address: str) -> None:
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and (
            ip.sixtofour is not None
            or ip.teredo is not None
            or any(ip in net for net in _TRANSLATED_V6)
        ):
            raise ValueError("unsafe_outbound_address")
        super().check_address(host, port, address)


def source_url(value: str, policy: OutboundPolicy) -> URL:
    try:
        if len(value) > MAX_URL_LENGTH or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError("invalid URL characters")
        url = URL(value)
        host = (url.host or "").rstrip(".")
        if (
            url.scheme != "https"
            or not host
            or host == "localhost"
            or host.endswith(".localhost")
            or url.user is not None
            or url.password is not None
            or url.fragment
            or url.port is None
            or not 0 < url.port <= 65535
            or len(str(url)) > MAX_URL_LENGTH
        ):
            raise ValueError("invalid source URL")
        policy.check_url(str(url))
    except ValueError as exc:
        raise SourceURLValidationError("invalid_source_url") from exc
    return url


def validate_source_urls(values: Iterable[str]) -> tuple[str, ...]:
    policy = SourceNetworkPolicy()
    urls: dict[str, None] = {}
    for value in values:
        clean = value.strip()
        if not clean:
            continue
        urls[str(source_url(clean, policy))] = None
        if len(urls) > MAX_SOURCES:
            raise SourceURLValidationError("too_many_sources")
    return tuple(urls)
