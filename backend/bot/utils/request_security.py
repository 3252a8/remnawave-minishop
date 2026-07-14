from __future__ import annotations

import ipaddress
from collections.abc import Sequence

from aiohttp import web

# Cloudflare publishes these proxy ranges at https://www.cloudflare.com/ips/.
# Keep both address families here so CF-Connecting-IP is accepted only when the
# nearest untrusted hop is verifiably part of Cloudflare's network.
_CLOUDFLARE_PROXY_NETWORKS: tuple[ipaddress._BaseNetwork, ...] = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "173.245.48.0/20",
        "103.21.244.0/22",
        "103.22.200.0/22",
        "103.31.4.0/22",
        "141.101.64.0/18",
        "108.162.192.0/18",
        "190.93.240.0/20",
        "188.114.96.0/20",
        "197.234.240.0/22",
        "198.41.128.0/17",
        "162.158.0.0/15",
        "104.16.0.0/13",
        "104.24.0.0/14",
        "172.64.0.0/13",
        "131.0.72.0/22",
        "2400:cb00::/32",
        "2606:4700::/32",
        "2803:f800::/32",
        "2405:b500::/32",
        "2405:8100::/32",
        "2a06:98c0::/29",
        "2c0f:f248::/32",
    )
)


def parse_ip_entries(raw_values: Sequence[str] | str | None) -> list[ipaddress._BaseNetwork]:
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


def _parse_ip(value: str | None) -> ipaddress._BaseAddress | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _forwarded_ips(header_value: str) -> list[ipaddress._BaseAddress]:
    candidates = [item.strip() for item in header_value.split(",") if item.strip()]
    parsed: list[ipaddress._BaseAddress] = []
    for candidate in candidates:
        parsed_ip = _parse_ip(candidate)
        if parsed_ip is not None:
            parsed.append(parsed_ip)
    return parsed


def _forwarded_client_ip(
    forwarded_ips: Sequence[ipaddress._BaseAddress],
    trusted_networks: Sequence[ipaddress._BaseNetwork],
) -> str | None:
    for forwarded_ip in reversed(forwarded_ips):
        if not any(forwarded_ip in network for network in trusted_networks):
            return str(forwarded_ip)
    if forwarded_ips:
        return str(forwarded_ips[0])
    return None


def _ip_in_networks(
    ip_value: ipaddress._BaseAddress,
    networks: Sequence[ipaddress._BaseNetwork],
) -> bool:
    return any(ip_value in network for network in networks)


def _cloudflare_is_nearest_external_hop(
    remote_ip: ipaddress._BaseAddress,
    forwarded_ips: Sequence[ipaddress._BaseAddress],
    trusted_networks: Sequence[ipaddress._BaseNetwork],
) -> bool:
    for hop in reversed((*forwarded_ips, remote_ip)):
        if _ip_in_networks(hop, _CLOUDFLARE_PROXY_NETWORKS):
            return True
        if not _ip_in_networks(hop, trusted_networks):
            return False
    return False


def request_client_ip(
    request: web.Request,
    *,
    trusted_proxies: Sequence[str] | str | None = None,
) -> str | None:
    remote_ip = _parse_ip(request.remote or "")
    forwarded_ips = _forwarded_ips(request.headers.get("X-Forwarded-For", ""))
    trusted_networks = parse_ip_entries(trusted_proxies)

    cloudflare_ip = _parse_ip(request.headers.get("CF-Connecting-IP"))
    if (
        remote_ip
        and cloudflare_ip
        and _cloudflare_is_nearest_external_hop(
            remote_ip,
            forwarded_ips,
            trusted_networks,
        )
    ):
        return str(cloudflare_ip)

    if remote_ip and forwarded_ips and _ip_in_networks(remote_ip, trusted_networks):
        forwarded_ip = _forwarded_client_ip(forwarded_ips, trusted_networks)
        if forwarded_ip:
            return forwarded_ip

    if remote_ip:
        return str(remote_ip)

    if forwarded_ips:
        return str(forwarded_ips[-1])
    return None


def ip_in_allowlist(ip_value: str | None, allowed_entries: Sequence[str] | str | None) -> bool:
    parsed_ip = _parse_ip(ip_value)
    if parsed_ip is None:
        return False

    allowed_networks = parse_ip_entries(allowed_entries)
    return _ip_in_networks(parsed_ip, allowed_networks)
