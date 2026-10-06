import socket
from unittest.mock import MagicMock, patch

import pytest

from bot.services.settings_override_service import apply_overrides
from bot.utils.outbound_network import OutboundPolicy
from bot.utils.smtp_transport import connect_socket
from config.settings import Settings


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


def test_admin_smtp_host_and_ports_follow_runtime_overrides() -> None:
    settings = Settings(
        _env_file=None, BOT_TOKEN="token", POSTGRES_USER="test", POSTGRES_PASSWORD="test"
    )
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 2525))]
    assert (
        apply_overrides(
            settings,
            {"SMTP_HOST": "mail.internal", "SMTP_PORT": 2525, "SMTP_FALLBACK_PORTS": "465"},
        )
        == 3
    )
    with (
        patch("bot.utils.outbound_network.socket.getaddrinfo", return_value=answers),
        patch(
            "bot.utils.outbound_network.socket.create_connection", return_value=MagicMock()
        ) as connect,
    ):
        policy = OutboundPolicy(settings._trusted_smtp_endpoints)
        connect_socket(policy, "mail.internal", 2525, 10)
        connect_socket(policy, "mail.internal", 465, 10)
        assert connect.call_count == 2
        assert (
            apply_overrides(
                settings,
                {"SMTP_HOST": "new-mail.internal", "SMTP_PORT": 587, "SMTP_FALLBACK_PORTS": ""},
            )
            == 3
        )
        policy = OutboundPolicy(settings._trusted_smtp_endpoints)
        connect_socket(policy, "new-mail.internal", 587, 10)
        for host, port in (("mail.internal", 2525), ("new-mail.internal", 465)):
            with pytest.raises(ValueError):
                connect_socket(policy, host, port, 10)
        assert connect.call_count == 3
