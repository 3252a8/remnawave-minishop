"""SMTP sockets with destination validation and a pinned DNS answer."""

import smtplib
import socket
import ssl

from bot.utils.outbound_network import OutboundPolicy


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


class GuardedSMTP(smtplib.SMTP):
    def __init__(self, host: str, port: int, *, timeout: float, policy: OutboundPolicy) -> None:
        self.policy = policy
        super().__init__(host, port, timeout=timeout)

    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        try:
            return connect_socket(self.policy, host, port, timeout)
        except ValueError as exc:
            raise smtplib.SMTPConnectError(421, "SMTP destination is not allowed") from exc


class GuardedSMTPSSL(smtplib.SMTP_SSL):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float,
        context: ssl.SSLContext,
        policy: OutboundPolicy,
    ) -> None:
        self.policy = policy
        super().__init__(host, port, timeout=timeout, context=context)

    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        try:
            connection = connect_socket(self.policy, host, port, timeout)
        except ValueError as exc:
            raise smtplib.SMTPConnectError(421, "SMTP destination is not allowed") from exc
        try:
            return self.context.wrap_socket(connection, server_hostname=host)
        except BaseException:
            connection.close()
            raise
