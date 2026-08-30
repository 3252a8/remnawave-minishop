"""Verified two-address email change flow for authenticated accounts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_email_auth_service, get_i18n, get_session_factory, get_settings
from bot.app.web.webapp_auth import (
    create_signed_telegram_oauth_state,
    create_webapp_session_token,
    verify_signed_telegram_oauth_state,
)
from bot.services.email_auth_service import EmailAuthService
from config.settings import Settings
from db.dal import user_dal, user_email_dal

from .auth import _build_webapp_auth_response, _request_email_code, _sync_panel_identity_for_user
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _normalize_language,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import (
    WebAppEmailChangeConfirmPayload,
    WebAppEmailChangeCurrentPayload,
    WebAppEmailChangeNewPayload,
)
from .response_helpers import json_response

logger = logging.getLogger(__name__)


def _change_token(settings: Settings, *, user_id: int, email: str) -> str:
    return create_signed_telegram_oauth_state(
        settings,
        {"kind": "email_change", "user_id": user_id, "email": email},
        ttl_seconds=max(300, int(settings.WEBAPP_LOGIN_TOKEN_TTL_SECONDS)),
    )


def _verify_change_token(
    settings: Settings, token: str, *, user_id: int, current_email: str
) -> bool:
    payload = verify_signed_telegram_oauth_state(settings, token)
    return bool(
        payload
        and payload.get("kind") == "email_change"
        and int(payload.get("user_id") or 0) == user_id
        and str(payload.get("email") or "") == current_email
    )


def _verification_error(result: Any) -> web.Response:
    status = 429 if result.error == "rate_limited" else 400
    return json_response(
        {
            "ok": False,
            "error": result.error or "invalid_code",
            "retry_after": result.retry_after,
            "message": "Invalid code",
        },
        status=status,
    )


async def account_email_change_current_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.email_auth_configured:
        return _json_error(503, "email_auth_not_configured", "Email auth is not configured")
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if not user.email or not user.email_verified_at:
            return _json_error(400, "email_not_linked", "Email is not linked")
        email = str(user.email)
        language = _normalize_language(user.language_code or settings.DEFAULT_LANGUAGE)
    return await _request_email_code(
        request,
        email=email,
        purpose="change_email_current",
        language_code=language,
        target_user_id=user_id,
    )


async def account_email_change_current_verify_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppEmailChangeCurrentPayload)
    email_service: EmailAuthService = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned or not user.email or not user.email_verified_at:
            return _json_error(403, "access_denied", "Access denied")
        result = await email_service.verify_code(
            session,
            email=str(user.email),
            purpose="change_email_current",
            code=str(payload.code),
            target_user_id=user_id,
        )
        if not result.ok:
            await session.commit()
            return _verification_error(result)
        await session.commit()
        token = _change_token(settings, user_id=user_id, email=str(user.email))
    return json_response({"ok": True, "change_token": token})


async def account_email_change_new_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppEmailChangeNewPayload)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned or not user.email:
            return _json_error(403, "access_denied", "Access denied")
        if not _verify_change_token(
            settings, payload.change_token, user_id=user_id, current_email=str(user.email)
        ):
            return _json_error(400, "invalid_change_token", "Email change confirmation expired")
        if payload.email == user.email:
            return _json_error(400, "email_unchanged", "Enter a different email")
        existing = await user_dal.get_user_by_email(session, payload.email) or (
            await user_email_dal.get_user_by_verified_email_address(session, payload.email)
        )
        if existing and int(existing.user_id) != user_id:
            return _json_error(409, "email_already_in_use", "Email is already in use")
        language = _normalize_language(user.language_code or settings.DEFAULT_LANGUAGE)
    return await _request_email_code(
        request,
        email=payload.email,
        purpose="change_email_new",
        language_code=language,
        target_user_id=user_id,
    )


async def account_email_change_confirm_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppEmailChangeConfirmPayload)
    email_service: EmailAuthService = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    old_email = ""
    language = _normalize_language(settings.DEFAULT_LANGUAGE)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned or not user.email:
            return _json_error(403, "access_denied", "Access denied")
        if not _verify_change_token(
            settings, payload.change_token, user_id=user_id, current_email=str(user.email)
        ):
            return _json_error(400, "invalid_change_token", "Email change confirmation expired")
        existing = await user_dal.get_user_by_email(session, payload.email) or (
            await user_email_dal.get_user_by_verified_email_address(session, payload.email)
        )
        if existing and int(existing.user_id) != user_id:
            return _json_error(409, "email_already_in_use", "Email is already in use")
        result = await email_service.verify_code(
            session,
            email=payload.email,
            purpose="change_email_new",
            code=str(payload.code),
            target_user_id=user_id,
        )
        if not result.ok:
            await session.commit()
            return _verification_error(result)
        old_email = str(user.email)
        language = _normalize_language(user.language_code or settings.DEFAULT_LANGUAGE)
        user.email = payload.email
        user.email_verified_at = datetime.now(UTC)
        user.notification_email = payload.email
        await user_email_dal.upsert_user_email_address(
            session,
            user_id=user_id,
            email=payload.email,
            source="email",
            verified_at=user.email_verified_at,
            is_primary=True,
            is_notification=True,
        )
        await _sync_panel_identity_for_user(request, user)
        await session.commit()
    if old_email and not settings.qa_auth_enabled:
        try:
            i18n = get_i18n(request)
            subject = (
                i18n.gettext(language, "email_change_notice_subject")
                if i18n
                else "Email address changed"
            )
            body = (
                i18n.gettext(
                    language,
                    "email_change_notice_body",
                    old_email=old_email,
                    new_email=payload.email,
                )
                if i18n
                else (
                    f"Your sign-in email was changed from {old_email} to {payload.email}. "
                    "If this was not you, contact support."
                )
            )
            await email_service.send_custom_email(email=old_email, subject=subject, body=body)
        except Exception:
            logger.warning("Failed to send email change notification", exc_info=True)
    await _invalidate_webapp_user_caches(settings, user_id, include_devices=True)
    token = create_webapp_session_token(settings, user_id)
    return _build_webapp_auth_response(settings, {"ok": True}, token=token)
