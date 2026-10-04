"""Provider-independent explicit merge, with fresh proof of both accounts."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.context import get_email_auth_service, get_session_factory, get_settings
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from db.dal import user_dal, user_email_dal
from db.dal.user_dal import UserMergeConflictError
from db.models import User, UserExternalIdentity, UserPasskeyCredential

from .account_merge_proof import clear_merge_proof, read_merge_proof
from .auth_common import _build_webapp_auth_response
from .auth_email import _request_email_code
from .auth_panel import (
    _build_account_merge_notice,
    _merge_users_for_web,
    _sync_merged_panel_identity_for_user,
)
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _normalize_language,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import WebAppAccountMergePayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)


async def _identity_owner(session: AsyncSession, proof: dict[str, Any]) -> User | None:
    provider, subject = str(proof["provider"]), str(proof["subject"])
    if provider == "telegram":
        try:
            telegram_id = int(subject)
        except ValueError:
            return None
        return await user_dal.get_user_by_telegram_id(session, telegram_id)
    if provider == "email":
        return await user_email_dal.get_user_by_verified_email_address(session, subject) or (
            await user_dal.get_user_by_email(session, subject)
        )
    identity = (
        await session.execute(
            select(UserExternalIdentity).where(
                UserExternalIdentity.provider == provider,
                UserExternalIdentity.subject == subject,
            )
        )
    ).scalar_one_or_none()
    return await user_dal.get_user_by_id(session, int(identity.user_id)) if identity else None


async def merge_source(session: AsyncSession, proof: dict[str, Any]) -> User | None:
    source = await _identity_owner(session, proof)
    return source if source and int(source.user_id) == int(proof["source_user_id"]) else None


def _email_available(settings: Settings, user: User) -> bool:
    return bool(settings.email_auth_configured and user.email and user.email_verified_at)


async def account_merge_status_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    proof = read_merge_proof(request, user_id)
    if not proof:
        return _json_error(410, "account_merge_proof_expired", "Repeat account linking")
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        source = await merge_source(session, proof)
        if not user or user.is_banned or not source or source.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if int(source.user_id) == user_id:
            return _json_error(409, "account_merge_not_required", "Accounts already linked")
        providers = list(
            (
                await session.execute(
                    select(UserExternalIdentity.provider).where(
                        UserExternalIdentity.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        providers = [str(key) for key in providers if key in settings.webapp_auth_providers]
        if settings.TELEGRAM_ENABLED and settings.TELEGRAM_LOGIN_ENABLED and user.telegram_id:
            providers.append("telegram")
        if (
            settings.PASSKEY_LOGIN_ENABLED
            and (
                await session.execute(
                    select(UserPasskeyCredential.credential_id)
                    .where(UserPasskeyCredential.user_id == user_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
        ):
            providers.append("passkey")
        return json_response(
            {
                "ok": True,
                "provider": proof["provider"],
                "target_confirmed": bool(proof.get("target_confirmed")),
                "providers": sorted(set(providers)),
                "email_available": _email_available(settings, user),
                "email": str(user.email or ""),
            }
        )


async def account_merge_request_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    proof = read_merge_proof(request, user_id)
    if not proof:
        return _json_error(410, "account_merge_proof_expired", "Repeat account linking")
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        if not _email_available(settings, user):
            return _json_error(409, "account_merge_confirmation_required", "Confirm account login")
        email, language = (
            str(user.email),
            _normalize_language(user.language_code or settings.DEFAULT_LANGUAGE),
        )
    return await _request_email_code(
        request,
        email=email,
        purpose=f"merge_account:{proof['challenge']}",
        language_code=language,
        target_user_id=user_id,
    )


async def account_merge_cancel_route(request: web.Request) -> web.Response:
    _require_user_id(request)
    response = json_response({"ok": True})
    clear_merge_proof(response)
    return response


async def account_merge_confirm_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    proof = read_merge_proof(request, user_id)
    if not proof:
        return _json_error(410, "account_merge_proof_expired", "Repeat account linking")
    payload = await _parse_model_payload(request, WebAppAccountMergePayload)
    settings = get_settings(request)
    async with get_session_factory(request)() as session:
        try:
            for participant_id in sorted({user_id, int(proof["source_user_id"])}):
                await user_dal.lock_user_by_id(session, participant_id)
            user = await user_dal.get_user_by_id(session, user_id)
            if not user or user.is_banned:
                return _json_error(403, "access_denied", "Access denied")
            if not proof.get("target_confirmed"):
                if not payload.email_code or not _email_available(settings, user):
                    return _json_error(
                        409, "account_merge_confirmation_required", "Confirm account login"
                    )
                verified = await get_email_auth_service(request).verify_code(
                    session,
                    email=str(user.email),
                    purpose=f"merge_account:{proof['challenge']}",
                    code=str(payload.email_code),
                    target_user_id=user_id,
                )
                if not verified.ok:
                    await session.commit()
                    return _json_error(
                        429 if verified.error == "rate_limited" else 400,
                        verified.error or "invalid_code",
                        "Invalid code",
                    )
            source = await merge_source(session, proof)
            if not source or int(source.user_id) == user_id:
                return _json_error(409, "account_merge_not_required", "Accounts already linked")
            source_user_id, source_panel_uuid = int(source.user_id), source.panel_user_uuid
            merged = await _merge_users_for_web(
                request,
                session,
                source_user_id=source_user_id,
                target_user_id=user_id,
                reason=f"explicit_{proof['provider']}_merge",
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
        except UserMergeConflictError as exc:
            await session.rollback()
            return _json_error(409, exc.code, str(exc))
        except Exception:
            await session.rollback()
            logger.exception("Explicit account merge failed")
            return _json_error(500, "account_merge_failed", "Account merge failed")
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
    await _invalidate_webapp_user_caches(settings, user_id, source_user_id, include_devices=True)
    response = _build_webapp_auth_response(
        settings,
        {"ok": True, "user_id": user_id, "account_merge": notice},
        token=create_webapp_session_token(settings, user_id),
    )
    clear_merge_proof(response)
    return response
