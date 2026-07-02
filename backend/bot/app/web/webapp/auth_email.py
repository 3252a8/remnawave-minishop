import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_email_auth_service,
    get_session_factory,
    get_settings,
)
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.email_auth_service import EmailAuthService
from bot.services.registration_invite_gate import evaluate_registration_invite
from config.settings import Settings
from db.dal import security_dal, user_dal
from db.models import User

from .auth_common import (
    _build_webapp_auth_response,
    _verify_email_password,
)
from .auth_referral import (
    _apply_referral_to_existing_user,
    _apply_referral_welcome_bonus_if_needed,
)
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _normalize_language,
    _parse_model_payload,
    _telegram_id_for_user,
)
from .payloads import (
    WebAppEmailCodeAuthPayload,
    WebAppEmailMagicAuthPayload,
    WebAppEmailPasswordPayload,
    WebAppEmailRequestPayload,
)
from .response_helpers import json_response

logger = logging.getLogger(__name__)


def _password_login_failure_response(
    *,
    status: int = 401,
    retry_after: int | None = None,
) -> web.Response:
    payload: dict[str, Any] = {
        "ok": False,
        "error": "password_login_failed",
        "fallback": "email_code",
        "message": "Password login failed",
    }
    if retry_after is not None:
        payload["retry_after"] = retry_after
    return json_response(payload, status=status)


def _registration_invite_required_response() -> web.Response:
    return _json_error(
        403,
        "registration_invite_required",
        "Registration requires an invitation",
    )


async def email_password_auth_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.email_auth_configured:
        return _json_error(503, "email_auth_not_configured", "Email auth is not configured")

    password_payload = await _parse_model_payload(request, WebAppEmailPasswordPayload)

    email = password_payload.email
    password = str(password_payload.password or "")
    now = datetime.now(UTC)

    async_session_factory: sessionmaker = get_session_factory(request)
    authenticated_user_id: int | None = None
    authenticated_telegram_id: int | None = None
    async with async_session_factory() as session:
        try:
            throttle = await security_dal.check_throttle(
                session,
                scope=security_dal.EMAIL_PASSWORD_LOGIN_SCOPE,
                identifier=email,
                now=now,
            )
            if throttle.locked:
                await session.commit()
                return _json_error(
                    429,
                    "rate_limited",
                    "Too many password attempts",
                )

            db_user = await user_dal.get_user_by_email(session, email)
            password_ok = bool(
                db_user
                and db_user.email_verified_at
                and db_user.password_hash
                and _verify_email_password(password, db_user.password_hash)
            )

            if not password_ok:
                throttle_result = await security_dal.record_throttle_failure(
                    session,
                    scope=security_dal.EMAIL_PASSWORD_LOGIN_SCOPE,
                    identifier=email,
                    max_failures=settings.BRUTE_FORCE_MAX_FAILURES,
                    window_seconds=settings.BRUTE_FORCE_WINDOW_SECONDS,
                    lock_seconds=settings.BRUTE_FORCE_LOCK_SECONDS,
                    now=now,
                )
                await session.commit()
                if throttle_result.locked:
                    return _json_error(
                        429,
                        "rate_limited",
                        "Too many password attempts",
                    )
                return _password_login_failure_response()

            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            await security_dal.clear_throttle_state(
                session,
                scope=security_dal.EMAIL_PASSWORD_LOGIN_SCOPE,
                identifier=email,
            )
            authenticated_user_id = int(db_user.user_id)
            authenticated_telegram_id = _telegram_id_for_user(db_user)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Email password auth failed")
            return _json_error(500, "auth_failed", "Auth failed")

    token = create_webapp_session_token(settings, int(authenticated_user_id))
    return _build_webapp_auth_response(
        settings,
        {
            "ok": True,
            "user_id": int(authenticated_user_id),
            "telegram_id": authenticated_telegram_id,
        },
        token=token,
    )


async def email_auth_request_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    email_payload = await _parse_model_payload(request, WebAppEmailRequestPayload)
    email = email_payload.email
    lang = _normalize_language(str(email_payload.language or settings.DEFAULT_LANGUAGE))
    referral_param = str(email_payload.referral_code or email_payload.start_param or "")
    return await _request_email_code(
        request,
        email=email,
        purpose="login",
        language_code=lang,
        target_user_id=None,
        referral_param=referral_param,
    )


async def email_auth_verify_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    email_payload = await _parse_model_payload(request, WebAppEmailCodeAuthPayload)
    email = email_payload.email
    code = str(email_payload.code or "")
    referral_param = str(email_payload.referral_code or email_payload.start_param or "")
    email_service: EmailAuthService = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    created_user = False

    async with async_session_factory() as session:
        try:
            verify_result = await email_service.verify_code(
                session,
                email=email,
                purpose="login",
                code=code,
                target_user_id=None,
            )
            if not verify_result.ok:
                await session.commit()
                status = 429 if verify_result.error == "rate_limited" else 400
                return json_response(
                    {
                        "ok": False,
                        "error": verify_result.error or "invalid_code",
                        "retry_after": verify_result.retry_after,
                        "message": "Invalid code",
                    },
                    status=status,
                )

            db_user = await user_dal.get_user_by_email(session, email)
            if not db_user:
                invite_check = await evaluate_registration_invite(
                    session,
                    referral_param,
                    current_user_id=None,
                    settings=settings,
                    source="webapp",
                )
                if invite_check.requires_invite:
                    await session.rollback()
                    return _registration_invite_required_response()
                db_user, _ = await user_dal.create_email_user(
                    session,
                    email=email,
                    language_code=_normalize_language(settings.DEFAULT_LANGUAGE),
                    email_verified_at=datetime.now(UTC),
                    referred_by_id=invite_check.referrer_user_id,
                )
                created_user = True
            elif not db_user.email_verified_at:
                db_user.email_verified_at = datetime.now(UTC)

            referral_applied = await _apply_referral_to_existing_user(
                request,
                session,
                db_user,
                referral_param,
            )
            if created_user or referral_applied:
                await _apply_referral_welcome_bonus_if_needed(
                    request,
                    session,
                    db_user,
                    referral_param,
                )

            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Email WebApp auth failed")
            return _json_error(500, "auth_failed", "Auth failed")

    await _invalidate_webapp_user_caches(settings, int(db_user.user_id), include_devices=True)

    token = create_webapp_session_token(settings, int(db_user.user_id))
    return _build_webapp_auth_response(
        settings,
        {
            "ok": True,
            "user_id": int(db_user.user_id),
            "telegram_id": _telegram_id_for_user(db_user),
        },
        token=token,
    )


async def email_auth_magic_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    magic_payload = await _parse_model_payload(request, WebAppEmailMagicAuthPayload)
    token_value = str(magic_payload.token).strip()
    referral_param = str(magic_payload.referral_code or magic_payload.start_param or "")
    email_service: EmailAuthService = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    created_user = False
    verified_email: str | None = None

    async with async_session_factory() as session:
        try:
            magic_result = await email_service.verify_magic_token(
                session,
                token=token_value,
                purpose="login",
                target_user_id=None,
            )
            if not magic_result.ok:
                await session.commit()
                return json_response(
                    {
                        "ok": False,
                        "error": magic_result.error or "invalid_token",
                        "message": "Invalid login link",
                    },
                    status=400,
                )

            verified_email = magic_result.email or ""
            db_user = await user_dal.get_user_by_email(session, verified_email)
            if not db_user:
                invite_check = await evaluate_registration_invite(
                    session,
                    referral_param,
                    current_user_id=None,
                    settings=settings,
                    source="webapp",
                )
                if invite_check.requires_invite:
                    await session.rollback()
                    return _registration_invite_required_response()
                db_user, _ = await user_dal.create_email_user(
                    session,
                    email=verified_email,
                    language_code=_normalize_language(settings.DEFAULT_LANGUAGE),
                    email_verified_at=datetime.now(UTC),
                    referred_by_id=invite_check.referrer_user_id,
                )
                created_user = True
            elif not db_user.email_verified_at:
                db_user.email_verified_at = datetime.now(UTC)

            referral_applied = await _apply_referral_to_existing_user(
                request,
                session,
                db_user,
                referral_param,
            )
            if created_user or referral_applied:
                await _apply_referral_welcome_bonus_if_needed(
                    request,
                    session,
                    db_user,
                    referral_param,
                )

            if db_user.is_banned:
                await session.rollback()
                return _json_error(403, "banned", "Access denied")

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Email magic-link auth failed")
            return _json_error(500, "auth_failed", "Auth failed")

    await _invalidate_webapp_user_caches(settings, int(db_user.user_id), include_devices=True)

    session_token = create_webapp_session_token(settings, int(db_user.user_id))
    return _build_webapp_auth_response(
        settings,
        {
            "ok": True,
            "user_id": int(db_user.user_id),
            "telegram_id": _telegram_id_for_user(db_user),
        },
        token=session_token,
    )


async def _request_email_code(
    request: web.Request,
    *,
    email: str,
    purpose: str,
    language_code: str,
    target_user_id: int | None,
    referral_param: str | None = None,
) -> web.Response:
    email_service: EmailAuthService = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            result = await email_service.request_code(
                session,
                email=email,
                purpose=purpose,
                language_code=language_code,
                target_user_id=target_user_id,
                referral_param=referral_param,
            )
            if not result.ok:
                await session.rollback()
                status = 429 if result.error == "rate_limited" else 400
                if result.error == "email_auth_not_configured":
                    status = 503
                return json_response(
                    {
                        "ok": False,
                        "error": result.error,
                        "retry_after": result.retry_after,
                    },
                    status=status,
                )
            await session.commit()
            payload: dict[str, Any] = {"ok": True}
            if result.code:
                payload["code"] = result.code
                payload["email_code"] = result.code
            if result.magic_link:
                payload["magic_link"] = result.magic_link
            return json_response(payload)
        except Exception:
            await session.rollback()
            logger.exception("Failed to send email verification code")
            return _json_error(502, "email_send_failed", "Failed to send email")


def _user_has_linked_telegram(user: User) -> bool:
    return bool(getattr(user, "telegram_id", None))
