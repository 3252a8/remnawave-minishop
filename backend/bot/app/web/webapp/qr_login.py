"""QR sign-in: a browser is signed in by approving it from a signed-in device.

The waiting browser only ever talks to this shop, so it works on a device that
cannot reach Telegram at all. It asks for a QR code, keeps a signed cookie naming
its request, and polls. A device that already holds a session scans the code -
with Telegram's scanner inside the Mini App, or with the camera in a browser - and
confirms by typing the number the waiting screen shows. The session is then handed
to the browser that holds the request cookie, exactly once.
"""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.webapp_auth import (
    create_signed_telegram_oauth_state,
    create_webapp_session_token,
    verify_signed_telegram_oauth_state,
)
from bot.utils.user_agent import describe_user_agent
from config.settings import Settings
from db.dal import qr_login_dal, user_dal

from .auth_common import _build_webapp_auth_response, _public_webapp_base_url
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _parse_model_payload,
    _require_user_id,
    _telegram_id_for_user,
)
from .payloads import (
    WebAppQrLoginApprovePayload,
    WebAppQrLoginClaimPayload,
    WebAppQrLoginRequestPayload,
)
from .rate_limits import check_request_limits, client_ip, enforce_action_limit
from .response_helpers import json_response

logger = logging.getLogger(__name__)

QR_LOGIN_COOKIE_NAME = "rw_qr_login"
QR_LOGIN_COOKIE_PATH = "/api/auth/qr"
QR_LOGIN_COOKIE_TTL_SECONDS = 600
# An existing page route, so the link opens the app on every deployed frontend;
# the code travels in the fragment and never reaches server logs.
QR_LOGIN_URL_PATH = "/settings"
QR_LOGIN_URL_FRAGMENT_KEY = "qrlogin"
QR_LOGIN_POLL_INTERVAL_SECONDS = 2
_COOKIE_PURPOSE = "qr_login"
_START_LIMIT_PER_IP = 20
_START_WINDOW_SECONDS = 600
_POLL_LIMIT_PER_REQUEST = 90
_POLL_WINDOW_SECONDS = 60
_FINISHED_POLL_STATUSES = frozenset({"denied", "expired"})


def qr_login_url(settings: Settings, request: web.Request, code: str) -> str:
    base_url = _public_webapp_base_url(settings, request)
    return f"{base_url}{QR_LOGIN_URL_PATH}#{QR_LOGIN_URL_FRAGMENT_KEY}={code}"


def _disabled_response() -> web.Response:
    return _json_error(404, "qr_login_not_enabled", "QR login is not enabled")


def _set_request_cookie(response: web.StreamResponse, settings: Settings, request_id: str) -> None:
    response.set_cookie(
        QR_LOGIN_COOKIE_NAME,
        create_signed_telegram_oauth_state(
            settings,
            {"purpose": _COOKIE_PURPOSE, "request_id": request_id},
            ttl_seconds=QR_LOGIN_COOKIE_TTL_SECONDS,
        ),
        httponly=True,
        secure=True,
        samesite="Strict",
        path=QR_LOGIN_COOKIE_PATH,
        max_age=QR_LOGIN_COOKIE_TTL_SECONDS,
    )


def _clear_request_cookie(response: web.StreamResponse) -> None:
    response.set_cookie(
        QR_LOGIN_COOKIE_NAME,
        "",
        httponly=True,
        secure=True,
        samesite="Strict",
        path=QR_LOGIN_COOKIE_PATH,
        max_age=0,
    )


def _read_request_cookie(request: web.Request) -> str | None:
    payload = verify_signed_telegram_oauth_state(
        get_settings(request), request.cookies.get(QR_LOGIN_COOKIE_NAME, "")
    )
    if not payload or payload.get("purpose") != _COOKIE_PURPOSE:
        return None
    request_id = str(payload.get("request_id") or "")
    return request_id if qr_login_dal.is_token(request_id) else None


def _seconds_left(expires_at: datetime | None, now: datetime) -> int | None:
    if expires_at is None:
        return None
    return max(0, int((qr_login_dal.as_utc(expires_at) - now).total_seconds()))


def _status_response(
    status: str,
    *,
    now: datetime,
    expires_at: datetime | None = None,
    match_number: int | None = None,
) -> web.Response:
    payload: dict[str, Any] = {"ok": True, "status": status}
    if match_number is not None:
        payload["match_number"] = match_number
    seconds_left = _seconds_left(expires_at, now)
    if seconds_left is not None:
        payload["expires_in"] = seconds_left
    response = json_response(payload)
    response.headers["Cache-Control"] = "no-store"
    if status in _FINISHED_POLL_STATUSES:
        _clear_request_cookie(response)
    return response


async def qr_login_start_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.QR_LOGIN_ENABLED:
        return _disabled_response()
    ip = client_ip(request)
    limited = await check_request_limits(
        request,
        ((f"qr_login_start:ip:{ip}", _START_LIMIT_PER_IP),),
        window_seconds=_START_WINDOW_SECONDS,
    )
    if limited is not None:
        return limited
    now = datetime.now(UTC)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            started = await qr_login_dal.start_request(
                session,
                now=now,
                requester_ip=ip,
                requester_user_agent=request.headers.get("User-Agent"),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Could not start a QR login request")
            return _json_error(500, "qr_login_failed", "Could not start QR login")
    response = json_response(
        {
            "ok": True,
            "request_id": started.request_id,
            "qr_url": qr_login_url(settings, request, started.code),
            "expires_in": qr_login_dal.CODE_TTL_SECONDS,
            "poll_interval": QR_LOGIN_POLL_INTERVAL_SECONDS,
        }
    )
    response.headers["Cache-Control"] = "no-store"
    _set_request_cookie(response, settings, started.request_id)
    return response


async def qr_login_poll_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.QR_LOGIN_ENABLED:
        disabled = _disabled_response()
        _clear_request_cookie(disabled)
        return disabled
    payload = await _parse_model_payload(request, WebAppQrLoginRequestPayload)
    now = datetime.now(UTC)
    request_id = _read_request_cookie(request)
    if not request_id or not hmac.compare_digest(request_id, payload.request_id):
        # Another tab started a newer request, or the cookie expired.
        return _status_response("expired", now=now)
    limited = await check_request_limits(
        request,
        ((f"qr_login_poll:{request_id}", _POLL_LIMIT_PER_REQUEST),),
        window_seconds=_POLL_WINDOW_SECONDS,
    )
    if limited is not None:
        return limited
    user_id: int | None = None
    telegram_id: int | None = None
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            result = await qr_login_dal.poll_request(session, request_id, now=now)
            if result.status == "approved" and result.user_id is not None:
                user = await user_dal.get_user_by_id(session, result.user_id)
                if user is None or user.is_banned:
                    await session.commit()
                    return _status_response("denied", now=now)
                user_id = int(user.user_id)
                telegram_id = _telegram_id_for_user(user)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("QR login poll failed")
            return _json_error(500, "qr_login_failed", "QR login failed")
    if user_id is None:
        return _status_response(
            result.status,
            now=now,
            expires_at=result.expires_at,
            match_number=result.match_number,
        )
    await _invalidate_webapp_user_caches(settings, user_id)
    response = _build_webapp_auth_response(
        settings,
        {"ok": True, "status": "approved", "user_id": user_id, "telegram_id": telegram_id},
        token=create_webapp_session_token(settings, user_id),
    )
    response.headers["Cache-Control"] = "no-store"
    _clear_request_cookie(response)
    return response


async def qr_login_cancel_route(request: web.Request) -> web.Response:
    request_id = _read_request_cookie(request)
    response = json_response({"ok": True})
    _clear_request_cookie(response)
    if not request_id:
        return response
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            await qr_login_dal.cancel_request(session, request_id, now=datetime.now(UTC))
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("QR login cancel failed")
    return response


async def account_qr_login_claim_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.QR_LOGIN_ENABLED:
        return _disabled_response()
    limited = await enforce_action_limit(request, user_id=user_id, action="qr_login_claim")
    if limited is not None:
        return limited
    payload = await _parse_model_payload(request, WebAppQrLoginClaimPayload)
    now = datetime.now(UTC)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            user = await user_dal.get_user_by_id(session, user_id)
            if user is None or user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            result = await qr_login_dal.claim_request(
                session, payload.code, user_id=user_id, now=now
            )
            record = result.request
            if record is None:
                await session.rollback()
                if result.error == "already_claimed":
                    return _json_error(
                        409, "qr_login_already_claimed", "This code was scanned by another account"
                    )
                return _json_error(410, "qr_login_expired", "This code has expired")
            browser, system = describe_user_agent(record.requester_user_agent)
            response_payload: dict[str, Any] = {
                "ok": True,
                "request_id": str(record.request_id),
                "browser": browser,
                "os": system,
                "ip": str(record.requester_ip or ""),
                "expires_in": _seconds_left(record.expires_at, now) or 0,
            }
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("QR login claim failed")
            return _json_error(500, "qr_login_failed", "QR login failed")
    return json_response(response_payload)


async def account_qr_login_approve_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.QR_LOGIN_ENABLED:
        return _disabled_response()
    limited = await enforce_action_limit(request, user_id=user_id, action="qr_login_approve")
    if limited is not None:
        return limited
    payload = await _parse_model_payload(request, WebAppQrLoginApprovePayload)
    now = datetime.now(UTC)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            user = await user_dal.get_user_by_id(session, user_id)
            if user is None or user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            result = await qr_login_dal.approve_request(
                session, payload.request_id, user_id=user_id, number=payload.number, now=now
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("QR login approval failed")
            return _json_error(500, "qr_login_failed", "QR login failed")
    if result.outcome == "approved":
        logger.info("QR login approved by user %s", user_id)
        return json_response({"ok": True, "status": "approved"})
    if result.outcome == "wrong_number":
        return json_response(
            {
                "ok": False,
                "error": "qr_login_wrong_number",
                "message": "The number does not match the other screen",
                "attempts_left": result.attempts_left,
            },
            status=400,
        )
    if result.outcome == "denied":
        return _json_error(410, "qr_login_denied", "Too many wrong numbers")
    return _json_error(410, "qr_login_expired", "This code has expired")


async def account_qr_login_deny_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.QR_LOGIN_ENABLED:
        return _disabled_response()
    payload = await _parse_model_payload(request, WebAppQrLoginRequestPayload)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            await qr_login_dal.deny_request(
                session, payload.request_id, user_id=user_id, now=datetime.now(UTC)
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("QR login denial failed")
            return _json_error(500, "qr_login_failed", "QR login failed")
    return json_response({"ok": True})
