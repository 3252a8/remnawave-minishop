"""SMTP sockets with destination validation and a pinned DNS answer."""

import smtplib
import socket
import ssl

from bot.utils.outbound_network import OutboundPolicy, connect_socket


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
