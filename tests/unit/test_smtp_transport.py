import socket
from unittest.mock import MagicMock, patch

import pytest

from bot.utils.outbound_network import OutboundPolicy
from bot.utils.smtp_transport import connect_socket


def test_smtp_dns_cannot_rebind_into_a_private_service() -> None:
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 587))]
    with (
        patch("bot.utils.outbound_network.socket.getaddrinfo", return_value=answers),
        patch("bot.utils.outbound_network.socket.create_connection") as connect,
        pytest.raises(ValueError),
    ):
        connect_socket(OutboundPolicy(), "smtp.test", 587, 10)
    connect.assert_not_called()


def test_smtp_connects_to_the_validated_ip_and_keeps_operator_internal_smtp() -> None:
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 587))]
    policy = OutboundPolicy([("smtp.internal", 587)])
    with (
        patch("bot.utils.outbound_network.socket.getaddrinfo", return_value=answers),
        patch(
            "bot.utils.outbound_network.socket.create_connection", return_value=MagicMock()
        ) as connect,
    ):
        connect_socket(policy, "smtp.internal", 587, 10)
    connect.assert_called_once_with(("10.0.0.2", 587), 10, None)
