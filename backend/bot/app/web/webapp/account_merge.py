"""Explicit two-account Telegram merge with fresh proof of both identities."""

import logging
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_email_auth_service, get_session_factory, get_settings
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.infra import events
from bot.infra.event_payloads import AccountTelegramLinkedPayload
from config.settings import Settings
from db.dal import user_dal
from db.dal.user_dal import UserMergeConflictError

from .auth import (
    _build_account_merge_notice,
    _build_webapp_auth_response,
    _merge_users_for_web,
    _request_email_code,
    _sync_merged_panel_identity_for_user,
    _validate_telegram_auth_payload,
)
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _normalize_language,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import WebAppTelegramMergePayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def account_telegram_merge_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.TELEGRAM_ENABLED:
        return _json_error(404, "telegram_disabled", "Telegram is disabled")
    if not settings.email_auth_configured:
        return _json_error(409, "email_auth_not_configured", "Email auth is required")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        current = await user_dal.get_user_by_id(session, user_id)
        if not current or current.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if not current.email or not current.email_verified_at:
            return _json_error(
                409, "verified_email_required", "Verify this account's email before merging"
            )
        email = str(current.email)
        language = _normalize_language(current.language_code or settings.DEFAULT_LANGUAGE)

    return await _request_email_code(
        request,
        email=email,
        purpose="merge_telegram",
        language_code=language,
        target_user_id=user_id,
    )


async def account_telegram_merge_confirm_route(request: web.Request) -> web.Response:
    current_user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.TELEGRAM_ENABLED:
        return _json_error(404, "telegram_disabled", "Telegram is disabled")
    if not settings.email_auth_configured:
        return _json_error(409, "email_auth_not_configured", "Email auth is required")

    merge_payload = await _parse_model_payload(request, WebAppTelegramMergePayload)
    telegram_user = await _validate_telegram_auth_payload(
        request, merge_payload.model_dump(mode="json", exclude_none=True)
    )
    if not telegram_user:
        return _json_error(401, "invalid_auth", "Invalid Telegram auth data")
    telegram_id = int(telegram_user["id"])

    async_session_factory: sessionmaker = get_session_factory(request)
    email_service = get_email_auth_service(request)
    source_user_id: int | None = None
    notice: dict[str, Any] | None = None
    async with async_session_factory() as session:
        try:
            current = await user_dal.get_user_by_id(session, current_user_id)
            if not current or current.is_banned:
                return _json_error(403, "access_denied", "Access denied")
            if not current.email or not current.email_verified_at:
                return _json_error(
                    409, "verified_email_required", "Verify this account's email before merging"
                )
            verified = await email_service.verify_code(
                session,
                email=str(current.email),
                purpose="merge_telegram",
                code=str(merge_payload.email_code),
                target_user_id=current_user_id,
            )
            if not verified.ok:
                await session.commit()
                return json_response(
                    {"ok": False, "error": verified.error or "invalid_code"},
                    status=429 if verified.error == "rate_limited" else 400,
                )

            source = await user_dal.get_user_by_telegram_id(session, telegram_id)
            if not source or source.user_id == current_user_id:
                await session.rollback()
                return _json_error(
                    409, "account_merge_not_required", "Telegram is not linked to another account"
                )
            source_user_id = int(source.user_id)
            source_panel_uuid = source.panel_user_uuid
            merged = await _merge_users_for_web(
                request,
                session,
                source_user_id=source_user_id,
                target_user_id=current_user_id,
                reason="explicit_telegram_merge",
                send_user_email=True,
            )
            notice = await _build_account_merge_notice(
                session,
                merged_user=merged,
                source_user_id=source_user_id,
                source_panel_uuid=source_panel_uuid,
                settings=settings,
            )
            await session.commit()

            try:
                reconciled = await _sync_merged_panel_identity_for_user(
                    request,
                    merged,
                    source_panel_uuid=source_panel_uuid,
                    final_panel_uuid=merged.panel_user_uuid,
                    session=session,
                )
                if not reconciled:
                    notice["panel_reconciliation_pending"] = True
            except Exception:
                logger.exception("Panel reconciliation pending after explicit account merge")
                notice["panel_reconciliation_pending"] = True
        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, exc.code, str(exc))
        except Exception:
            await session.rollback()
            logger.exception("Explicit Telegram account merge failed")
            return _json_error(500, "account_merge_failed", "Account merge failed")

    await _invalidate_webapp_user_caches(
        settings, current_user_id, source_user_id, include_devices=True
    )
    await events.emit_model(
        AccountTelegramLinkedPayload(
            user_id=current_user_id,
            telegram_id=telegram_id,
            first_link=True,
            email=merged.email,
            username=merged.username,
            first_name=merged.first_name,
        )
    )
    token = create_webapp_session_token(settings, current_user_id)
    return _build_webapp_auth_response(
        settings,
        {
            "ok": True,
            "user_id": current_user_id,
            "telegram_id": telegram_id,
            "account_merge": notice,
        },
        token=token,
    )
