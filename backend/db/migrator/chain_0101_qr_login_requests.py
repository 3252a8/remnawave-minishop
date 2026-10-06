"""Persist pending QR sign-in requests confirmed from another session."""

from sqlalchemy.engine import Connection

from db.auth_models import QrLoginRequest

from .engine import Migration


def _migration_0101_qr_login_requests(connection: Connection) -> None:
    QrLoginRequest.__table__.create(connection, checkfirst=True)


CHAIN_0101_QR_LOGIN_REQUESTS = [
    Migration(
        id="0101_qr_login_requests",
        description="Store QR sign-in requests confirmed from a signed-in device",
        upgrade=_migration_0101_qr_login_requests,
    )
]
