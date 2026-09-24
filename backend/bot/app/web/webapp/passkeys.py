"""WebAuthn passkey registration, authentication, listing, and removal."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web
from sqlalchemy import delete, func
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from db.dal import user_dal
from db.models import (
    UserExternalIdentity,
    UserPasskeyCredential,
    WebAuthnChallenge,
)

from .auth import _build_webapp_auth_response
from .auth_common import _public_webapp_base_url
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import WebAppPasskeyCredentialPayload, WebAppPasskeyDeletePayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _challenge_hash(challenge: str) -> str:
    return hashlib.sha256(challenge.encode("ascii")).hexdigest()


def _rp_context(settings: Settings, request: web.Request) -> tuple[str, str, str | list[str]]:
    public_origin = _public_webapp_base_url(settings, request)
    rp_id = str(settings.PASSKEY_RP_ID or "").strip() or str(urlsplit(public_origin).hostname or "")
    rp_name = str(settings.PASSKEY_RP_NAME or "").strip() or str(
        settings.WEBAPP_TITLE or "Mini App"
    )
    origins = [
        item.strip().rstrip("/")
        for item in str(settings.PASSKEY_ORIGINS or "").split(",")
        if item.strip()
    ]
    if not origins:
        origins = [public_origin.rstrip("/")]
    return rp_id, rp_name, origins[0] if len(origins) == 1 else origins


def _webauthn() -> tuple[Any, ...] | None:
    try:
        from webauthn import (
            generate_authentication_options,
            generate_registration_options,
            options_to_json,
            verify_authentication_response,
            verify_registration_response,
        )
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )

        return (
            generate_authentication_options,
            generate_registration_options,
            options_to_json,
            verify_authentication_response,
            verify_registration_response,
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )
    except ImportError:
        logger.exception("The webauthn package is unavailable")
        return None


async def _store_challenge(
    session: Any,
    settings: Settings,
    challenge: bytes,
    *,
    ceremony: str,
    user_id: int | None,
) -> None:
    now = datetime.now(UTC)
    await session.execute(
        delete(WebAuthnChallenge).where(
            (WebAuthnChallenge.expires_at < now) | (WebAuthnChallenge.consumed_at.is_not(None))
        )
    )
    session.add(
        WebAuthnChallenge(
            challenge_hash=_challenge_hash(_b64url(challenge)),
            user_id=user_id,
            ceremony=ceremony,
            expires_at=now
            + timedelta(seconds=max(60, int(settings.PASSKEY_CHALLENGE_TTL_SECONDS))),
        )
    )


async def _consume_challenge(
    session: Any,
    challenge: str,
    *,
    ceremony: str,
    user_id: int | None = None,
) -> WebAuthnChallenge | None:
    record = (
        await session.execute(
            select(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.challenge_hash == _challenge_hash(challenge),
                WebAuthnChallenge.ceremony == ceremony,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        not record
        or record.consumed_at is not None
        or record.expires_at < now
        or (user_id is not None and int(record.user_id or 0) != user_id)
    ):
        return None
    record.consumed_at = now
    await session.flush()
    return record


async def passkey_auth_options_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.PASSKEY_LOGIN_ENABLED:
        return _json_error(404, "passkey_not_enabled", "Passkey login is not enabled")
    api = _webauthn()
    if not api:
        return _json_error(503, "passkey_unavailable", "Passkey support is unavailable")
    (
        generate_authentication_options,
        _,
        options_to_json,
        _,
        _,
        _,
        _,
        _,
        UserVerificationRequirement,
    ) = api
    rp_id, _, _ = _rp_context(settings, request)
    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        await _store_challenge(
            session, settings, options.challenge, ceremony="authentication", user_id=None
        )
        await session.commit()
    return json_response({"ok": True, "options": json.loads(options_to_json(options))})


async def passkey_auth_verify_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.PASSKEY_LOGIN_ENABLED:
        return _json_error(404, "passkey_not_enabled", "Passkey login is not enabled")
    payload = await _parse_model_payload(request, WebAppPasskeyCredentialPayload)
    api = _webauthn()
    if not api:
        return _json_error(503, "passkey_unavailable", "Passkey support is unavailable")
    _, _, _, verify_authentication_response, _, _, _, _, _ = api
    credential_id = str(payload.credential.get("id") or "")
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            challenge = await _consume_challenge(
                session, payload.challenge, ceremony="authentication"
            )
            credential = (
                await session.execute(
                    select(UserPasskeyCredential)
                    .where(UserPasskeyCredential.credential_id == credential_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if not challenge or not credential:
                await session.commit()
                return _json_error(400, "invalid_passkey", "Invalid or expired passkey request")
            rp_id, _, origins = _rp_context(settings, request)
            verification = verify_authentication_response(
                credential=payload.credential,
                expected_challenge=base64.urlsafe_b64decode(
                    payload.challenge + "=" * (-len(payload.challenge) % 4)
                ),
                expected_rp_id=rp_id,
                expected_origin=origins,
                credential_public_key=bytes(credential.public_key),
                credential_current_sign_count=int(credential.sign_count or 0),
                require_user_verification=True,
            )
            credential.sign_count = int(verification.new_sign_count)
            credential.last_used_at = datetime.now(UTC)
            user = await user_dal.get_user_by_id(session, int(credential.user_id))
            if not user or user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")
            user_id = int(user.user_id)
            await session.commit()
        except Exception:
            await session.commit()
            logger.exception("Passkey authentication failed")
            return _json_error(400, "invalid_passkey", "Passkey verification failed")
    await _invalidate_webapp_user_caches(settings, user_id)
    token = create_webapp_session_token(settings, user_id)
    return _build_webapp_auth_response(settings, {"ok": True}, token=token)


async def account_passkey_options_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    if not settings.PASSKEY_LOGIN_ENABLED:
        return _json_error(404, "passkey_not_enabled", "Passkey login is not enabled")
    api = _webauthn()
    if not api:
        return _json_error(503, "passkey_unavailable", "Passkey support is unavailable")
    (
        _,
        generate_registration_options,
        options_to_json,
        _,
        _,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    ) = api
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        credentials = (
            (
                await session.execute(
                    select(UserPasskeyCredential).where(UserPasskeyCredential.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        rp_id, rp_name, _ = _rp_context(settings, request)
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=rp_name,
            user_id=hashlib.sha256(
                f"passkey:{settings.WEBAPP_SESSION_SECRET}:{user_id}".encode()
            ).digest(),
            user_name=str(user.email or user.telegram_id or user_id),
            user_display_name=str(user.first_name or user.username or user.email or user_id),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(
                    id=base64.urlsafe_b64decode(
                        item.credential_id + "=" * (-len(item.credential_id) % 4)
                    )
                )
                for item in credentials
            ],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        await _store_challenge(
            session, settings, options.challenge, ceremony="registration", user_id=user_id
        )
        await session.commit()
    return json_response({"ok": True, "options": json.loads(options_to_json(options))})


async def account_passkey_register_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppPasskeyCredentialPayload)
    api = _webauthn()
    if not settings.PASSKEY_LOGIN_ENABLED or not api:
        return _json_error(404, "passkey_not_enabled", "Passkey login is not enabled")
    _, _, _, _, verify_registration_response, _, _, _, _ = api
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            challenge = await _consume_challenge(
                session, payload.challenge, ceremony="registration", user_id=user_id
            )
            if not challenge:
                await session.commit()
                return _json_error(400, "invalid_challenge", "Invalid or expired challenge")
            rp_id, _, origins = _rp_context(settings, request)
            verification = verify_registration_response(
                credential=payload.credential,
                expected_challenge=base64.urlsafe_b64decode(
                    payload.challenge + "=" * (-len(payload.challenge) % 4)
                ),
                expected_rp_id=rp_id,
                expected_origin=origins,
                require_user_verification=True,
            )
            credential_id = _b64url(verification.credential_id)
            exists = (
                await session.execute(
                    select(UserPasskeyCredential.credential_pk).where(
                        UserPasskeyCredential.credential_id == credential_id
                    )
                )
            ).scalar_one_or_none()
            if exists:
                await session.commit()
                return _json_error(409, "passkey_exists", "This passkey is already registered")
            device_type = getattr(
                verification.credential_device_type, "value", verification.credential_device_type
            )
            transports = payload.credential.get("response", {}).get("transports", [])
            session.add(
                UserPasskeyCredential(
                    user_id=user_id,
                    credential_id=credential_id,
                    public_key=verification.credential_public_key,
                    sign_count=int(verification.sign_count),
                    transports=",".join(str(item) for item in transports) or None,
                    device_type=str(device_type or "") or None,
                    backed_up=bool(verification.credential_backed_up),
                    name=str(payload.name or "Passkey").strip()[:80] or "Passkey",
                )
            )
            await session.commit()
        except Exception:
            try:
                await session.commit()
            except Exception:
                await session.rollback()
            logger.exception("Passkey registration failed")
            return _json_error(400, "invalid_passkey", "Passkey registration failed")
    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True})


async def account_passkey_delete_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppPasskeyDeletePayload)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        credential = (
            await session.execute(
                select(UserPasskeyCredential).where(
                    UserPasskeyCredential.user_id == user_id,
                    UserPasskeyCredential.credential_id == payload.credential_id,
                )
            )
        ).scalar_one_or_none()
        if not credential:
            return _json_error(404, "passkey_not_found", "Passkey not found")
        user = await user_dal.get_user_by_id(session, user_id)
        passkey_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(UserPasskeyCredential)
                    .where(UserPasskeyCredential.user_id == user_id)
                )
            ).scalar_one()
        )
        external_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(UserExternalIdentity)
                    .where(
                        UserExternalIdentity.user_id == user_id,
                        UserExternalIdentity.provider.in_(settings.webapp_auth_providers),
                    )
                )
            ).scalar_one()
        )
        has_other_login = bool(
            passkey_count > 1
            or external_count
            or (
                settings.TELEGRAM_ENABLED
                and settings.TELEGRAM_LOGIN_ENABLED
                and user
                and user.telegram_id
            )
            or (user and user.email_verified_at and settings.email_auth_configured)
        )
        if not has_other_login:
            return _json_error(409, "last_login_method", "Add another login method first")
        await session.delete(credential)
        await session.commit()
    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True})
