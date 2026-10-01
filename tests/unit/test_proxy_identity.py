import socket
from types import SimpleNamespace
from unittest.mock import patch

from bot.utils.request_security import _proxy_host_networks, request_client_ip
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
