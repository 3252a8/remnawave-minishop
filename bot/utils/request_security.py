from __future__ import annotations

import ipaddress
from typing import Optional, Sequence

from aiohttp import web


def parse_ip_entries(raw_values: Optional[Sequence[str] | str]) -> list[ipaddress._BaseNetwork]:
    if raw_values is None:
        return []
    if isinstance(raw_values, str):
        values = [item.strip() for item in raw_values.split(",")]
    else:
        values = [str(item).strip() for item in raw_values]

    parsed: list[ipaddress._BaseNetwork] = []
    for value in values:
        if not value:
            continue
        try:
            parsed.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return parsed


def _parse_ip(value: Optional[str]) -> Optional[ipaddress._BaseAddress]:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _last_forwarded_ip(header_value: str) -> Optional[str]:
    candidates = [item.strip() for item in header_value.split(",") if item.strip()]
    if not candidates:
        return None
    candidate = candidates[-1]
    return candidate if _parse_ip(candidate) is not None else None


def request_client_ip(
    request: web.Request,
    *,
    trusted_proxies: Optional[Sequence[str] | str] = None,
) -> Optional[str]:
    remote_ip = _parse_ip(request.remote or "")
    forwarded_for = request.headers.get("X-Forwarded-For", "")

    if remote_ip and forwarded_for:
        trusted_networks = parse_ip_entries(trusted_proxies)
        if any(remote_ip in network for network in trusted_networks):
            forwarded_ip = _last_forwarded_ip(forwarded_for)
            if forwarded_ip:
                return forwarded_ip

    if remote_ip:
        return str(remote_ip)

    forwarded_ip = _last_forwarded_ip(forwarded_for)
    return forwarded_ip


def ip_in_allowlist(ip_value: Optional[str], allowed_entries: Optional[Sequence[str] | str]) -> bool:
    parsed_ip = _parse_ip(ip_value)
    if parsed_ip is None:
        return False

    allowed_networks = parse_ip_entries(allowed_entries)
    return any(parsed_ip in network for network in allowed_networks)
