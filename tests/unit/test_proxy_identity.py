import ipaddress
import socket
from types import SimpleNamespace
from unittest.mock import patch

from bot.utils.request_security import _proxy_host_networks, parse_ip_entries, request_client_ip
from config.settings_defaults import DEFAULT_TRUSTED_PROXIES


def test_unrelated_private_client_cannot_spoof_a_forwarded_address() -> None:
    _proxy_host_networks.cache_clear()
    with patch(
        "bot.utils.request_security.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.2", 0)),
        ],
    ):
        request = SimpleNamespace(remote="172.20.0.99", headers={"X-Forwarded-For": "8.8.8.8"})
        assert request_client_ip(request, trusted_proxies=DEFAULT_TRUSTED_PROXIES) == "172.20.0.99"
        request.remote = "172.20.0.2"
        request.headers["X-Forwarded-For"] = "8.8.8.8, 192.168.1.99"
        assert request_client_ip(request, trusted_proxies=DEFAULT_TRUSTED_PROXIES) == "192.168.1.99"
    _proxy_host_networks.cache_clear()


def test_standard_proxy_chain_keeps_the_client_ip_and_rejects_spoofed_prefixes() -> None:
    services = {
        "frontend": "172.20.0.2",
        "caddy": "172.20.0.3",
        "newt": "172.20.0.4",
        "newt-2": "172.20.0.5",
    }

    def resolve(host, port, *, type):
        if host not in services:
            raise socket.gaierror()
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (services[host], port or 0))]

    _proxy_host_networks.cache_clear()
    try:
        with patch("bot.utils.request_security.socket.getaddrinfo", side_effect=resolve):
            for service in services:
                request = SimpleNamespace(
                    remote=services[service],
                    headers={"X-Forwarded-For": "1.1.1.1, 8.8.8.8, 172.20.0.5, 172.20.0.3"},
                )
                assert (
                    request_client_ip(request, trusted_proxies=DEFAULT_TRUSTED_PROXIES) == "8.8.8.8"
                )
            request.remote = "172.20.0.99"
            assert (
                request_client_ip(request, trusted_proxies=DEFAULT_TRUSTED_PROXIES) == "172.20.0.99"
            )
    finally:
        _proxy_host_networks.cache_clear()


def test_proxy_recreation_refreshes_only_the_named_service_address() -> None:
    addresses = ["172.20.0.2"]

    def resolve(host, port, *, type):
        if host != "frontend":
            raise socket.gaierror()
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addresses[0], port or 0))]

    _proxy_host_networks.cache_clear()
    try:
        with (
            patch("bot.utils.request_security.socket.getaddrinfo", side_effect=resolve),
            patch("bot.utils.request_security.time.monotonic", return_value=60) as clock,
        ):
            assert ipaddress.ip_network("172.20.0.2") in parse_ip_entries(DEFAULT_TRUSTED_PROXIES)
            addresses[0] = "172.20.0.8"
            clock.return_value = 120
            networks = parse_ip_entries(DEFAULT_TRUSTED_PROXIES)
            assert ipaddress.ip_network("172.20.0.8") in networks
            assert ipaddress.ip_network("172.20.0.2") not in networks
    finally:
        _proxy_host_networks.cache_clear()
