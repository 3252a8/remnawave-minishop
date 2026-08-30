"""Google OIDC and Yandex OAuth login/link flows."""

from __future__ import annotations

import asyncio
import base64
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout, web
from sqlalchemy import func
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.webapp_auth import (
    create_signed_telegram_oauth_state,
    create_webapp_session_token,
    verify_signed_telegram_oauth_state,
)
from bot.services.partner_program_service import PartnerProgramService
from bot.services.registration_invite_gate import evaluate_registration_invite
from config.settings import Settings
from db.dal import user_dal, user_email_dal
from db.dal.user_dal import UserMergeConflictError
from db.models import UserExternalIdentity, UserPasskeyCredential

from .auth import _sync_panel_identity_for_user
from .auth_common import _public_webapp_base_url, _set_webapp_auth_cookies, _urlsafe_sha256
from .auth_referral import (
    _apply_referral_to_existing_user,
    _apply_referral_welcome_bonus_if_needed,
)
from .common import (
    _extract_authenticated_user_id,
    _invalidate_webapp_user_caches,
    _parse_model_payload,
)
from .payloads import WebAppExternalIdentityPayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)

_STATE_COOKIE = "rw_external_oauth_state"
_HTTP_TIMEOUT = ClientTimeout(total=15)


@dataclass(frozen=True)
class ExternalProvider:
    key: str
    authorization_url: str
    token_url: str
    client_id: str
    client_secret: str
    scopes: tuple[str, ...]


def _provider(settings: Settings, key: str) -> ExternalProvider | None:
    if key == "google" and settings.GOOGLE_OIDC_ENABLED:
        client_id = str(settings.GOOGLE_OIDC_CLIENT_ID or "").strip()
        secret = str(settings.GOOGLE_OIDC_CLIENT_SECRET or "").strip()
        if client_id and secret:
            return ExternalProvider(
                key="google",
                authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=secret,
                scopes=("openid", "email", "profile"),
            )
    if key == "yandex" and settings.YANDEX_OIDC_ENABLED:
        client_id = str(settings.YANDEX_OIDC_CLIENT_ID or "").strip()
        secret = str(settings.YANDEX_OIDC_CLIENT_SECRET or "").strip()
        if client_id and secret:
            return ExternalProvider(
                key="yandex",
                authorization_url="https://oauth.yandex.com/authorize",
                token_url="https://oauth.yandex.com/token",
                client_id=client_id,
                client_secret=secret,
                scopes=("login:email", "login:info", "login:avatar"),
            )
    return None


def _callback_url(settings: Settings, request: web.Request, provider: str) -> str:
    return f"{_public_webapp_base_url(settings, request)}/auth/{provider}/callback"


def _redirect(provider: str, purpose: str, status: str) -> str:
    path = "/settings/security" if purpose == "link" else "/"
    return f"{path}?external_auth={provider}:{status}"


def _set_state_cookie(
    response: web.StreamResponse, settings: Settings, payload: dict[str, Any]
) -> None:
    ttl = max(60, int(settings.WEBAPP_LOGIN_TOKEN_TTL_SECONDS))
    response.set_cookie(
        _STATE_COOKIE,
        create_signed_telegram_oauth_state(settings, payload, ttl_seconds=ttl),
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/auth",
        max_age=ttl,
    )


def _clear_state_cookie(response: web.StreamResponse) -> None:
    response.set_cookie(
        _STATE_COOKIE, "", httponly=True, secure=True, samesite="Lax", path="/auth", max_age=0
    )


def _read_state(request: web.Request) -> dict[str, Any] | None:
    settings: Settings = get_settings(request)
    payload = verify_signed_telegram_oauth_state(settings, request.cookies.get(_STATE_COOKIE, ""))
    if not payload:
        return None
    expected = str(payload.get("state") or "")
    received = str(request.query.get("state") or "")
    if not expected or not hmac.compare_digest(expected, received):
        return None
    return payload


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


async def external_oauth_start_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    key = str(request.match_info.get("provider") or "").lower()
    provider = _provider(settings, key)
    if not provider:
        raise web.HTTPFound(_redirect(key or "external", "login", "not_configured"))

    purpose = str(request.query.get("purpose") or "login").lower()
    if purpose not in {"login", "link"}:
        purpose = "login"
    current_user_id = _extract_authenticated_user_id(request)
    if purpose == "link" and not current_user_id:
        raise web.HTTPFound(_redirect(key, purpose, "unauthorized"))

    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(24)
    payload: dict[str, Any] = {
        "state": state,
        "provider": key,
        "purpose": purpose,
        "user_id": current_user_id,
        "verifier": verifier,
        "nonce": nonce,
        "referral": str(request.query.get("ref") or request.query.get("start_param") or "")[:128],
    }
    query: dict[str, str] = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": _callback_url(settings, request, key),
        "scope": " ".join(provider.scopes),
        "state": state,
        "code_challenge": _urlsafe_sha256(verifier),
        "code_challenge_method": "S256",
    }
    if key == "google":
        query.update({"nonce": nonce, "access_type": "online", "prompt": "select_account"})
    response = web.HTTPFound(f"{provider.authorization_url}?{urlencode(query)}")
    _set_state_cookie(response, settings, payload)
    return response


async def _post_token(
    provider: ExternalProvider, *, code: str, redirect_uri: str, verifier: str
) -> dict[str, Any] | None:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    async with (
        ClientSession(timeout=_HTTP_TIMEOUT) as session,
        session.post(provider.token_url, data=form) as response,
    ):
        if response.status != 200:
            logger.warning("%s token exchange failed with HTTP %s", provider.key, response.status)
            return None
        payload = await response.json(content_type=None)
        return payload if isinstance(payload, dict) else None


async def _google_profile(
    token_payload: dict[str, Any], provider: ExternalProvider, nonce: str
) -> dict[str, Any] | None:
    id_token = str(token_payload.get("id_token") or "")
    if not id_token:
        return None
    try:
        import jwt

        async with (
            ClientSession(timeout=_HTTP_TIMEOUT) as session,
            session.get("https://www.googleapis.com/oauth2/v3/certs") as response,
        ):
            if response.status != 200:
                return None
            jwks = await response.json(content_type=None)
        header = jwt.get_unverified_header(id_token)
        key = next(
            (
                item.key
                for item in jwt.PyJWKSet.from_dict(jwks).keys
                if item.key_id == header.get("kid")
            ),
            None,
        )
        if key is None:
            return None
        claims = await asyncio.to_thread(
            jwt.decode,
            id_token,
            key,
            algorithms=["RS256"],
            audience=provider.client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        if str(claims.get("iss") or "") not in {
            "accounts.google.com",
            "https://accounts.google.com",
        }:
            return None
        if not hmac.compare_digest(str(claims.get("nonce") or ""), nonce):
            return None
        return {
            "subject": str(claims["sub"]),
            "email": str(claims.get("email") or "").strip().lower() or None,
            "email_verified": bool(claims.get("email_verified")),
            "display_name": str(claims.get("name") or "").strip() or None,
            "picture_url": str(claims.get("picture") or "").strip() or None,
        }
    except Exception:
        logger.exception("Google ID token validation failed")
        return None


async def _yandex_profile(token_payload: dict[str, Any]) -> dict[str, Any] | None:
    access_token = str(token_payload.get("access_token") or "")
    if not access_token:
        return None
    async with (
        ClientSession(timeout=_HTTP_TIMEOUT) as session,
        session.get(
            "https://login.yandex.ru/info",
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
        ) as response,
    ):
        if response.status != 200:
            return None
        claims = await response.json(content_type=None)
    subject = str(claims.get("id") or "")
    if not subject:
        return None
    email = str(claims.get("default_email") or "").strip().lower() or None
    avatar_id = str(claims.get("default_avatar_id") or "").strip()
    return {
        "subject": subject,
        "email": email,
        "email_verified": bool(email),
        "display_name": str(claims.get("display_name") or claims.get("real_name") or "").strip()
        or None,
        "picture_url": f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200"
        if avatar_id
        else None,
    }


async def external_oauth_callback_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    key = str(request.match_info.get("provider") or "").lower()
    provider = _provider(settings, key)
    state = _read_state(request)
    purpose = str((state or {}).get("purpose") or "login")

    def finish(status: str) -> web.Response:
        response = web.HTTPFound(_redirect(key, purpose, status))
        _clear_state_cookie(response)
        return response

    if not provider or not state or state.get("provider") != key:
        return finish("invalid_state")
    if request.query.get("error") or not request.query.get("code"):
        return finish("cancelled")

    token_payload = await _post_token(
        provider,
        code=str(request.query["code"]),
        redirect_uri=_callback_url(settings, request, key),
        verifier=str(state.get("verifier") or ""),
    )
    if not token_payload:
        return finish("token_failed")
    profile = (
        await _google_profile(token_payload, provider, str(state.get("nonce") or ""))
        if key == "google"
        else await _yandex_profile(token_payload)
    )
    if not profile:
        return finish("profile_failed")

    async_session_factory: sessionmaker = get_session_factory(request)
    user_id: int | None = None
    created_user = False
    async with async_session_factory() as session:
        try:
            identity = (
                await session.execute(
                    select(UserExternalIdentity).where(
                        UserExternalIdentity.provider == key,
                        UserExternalIdentity.subject == profile["subject"],
                    )
                )
            ).scalar_one_or_none()
            requested_user_id = int(state.get("user_id") or 0) or None
            verified_email = (
                str(profile.get("email") if profile.get("email_verified") else "").strip().lower()
            )
            email_owner = (
                await user_email_dal.get_user_by_verified_email_address(session, verified_email)
                if verified_email
                else None
            )
            if purpose == "link":
                authenticated_user_id = _extract_authenticated_user_id(request)
                if not requested_user_id or authenticated_user_id != requested_user_id:
                    return finish("unauthorized")
                existing_for_user = (
                    await session.execute(
                        select(UserExternalIdentity).where(
                            UserExternalIdentity.user_id == requested_user_id,
                            UserExternalIdentity.provider == key,
                        )
                    )
                ).scalar_one_or_none()
                if existing_for_user and existing_for_user.subject != profile["subject"]:
                    return finish("provider_conflict")
                merge_sources: list[tuple[int, str]] = []
                if email_owner and int(email_owner.user_id) != requested_user_id:
                    merge_sources.append((int(email_owner.user_id), f"{key}_verified_email_link"))
                if identity and int(identity.user_id) != requested_user_id:
                    identity_owner_id = int(identity.user_id)
                    if all(source_id != identity_owner_id for source_id, _ in merge_sources):
                        merge_sources.append((identity_owner_id, f"{key}_oauth_link"))
                for source_user_id, reason in merge_sources:
                    await user_dal.merge_users(
                        session,
                        source_user_id=source_user_id,
                        target_user_id=requested_user_id,
                        reason=reason,
                        send_user_email=True,
                    )
                if email_owner and int(email_owner.user_id) != requested_user_id:
                    email_owner = await user_dal.get_user_by_id(session, requested_user_id)
                if identity:
                    identity.user_id = requested_user_id
                user_id = requested_user_id
            elif identity:
                user_id = int(identity.user_id)
            else:
                email = verified_email or None
                user = email_owner or (
                    await user_dal.get_user_by_email(session, email) if email else None
                )
                if user:
                    return finish("account_exists")
                invite = await evaluate_registration_invite(
                    session,
                    str(state.get("referral") or ""),
                    settings=settings,
                    current_user_id=None,
                    source="webapp",
                )
                if invite.requires_invite:
                    return finish("invite_required")
                if not email:
                    return finish("email_required")
                user, _ = await user_dal.create_email_user(
                    session,
                    email=email,
                    language_code=settings.DEFAULT_LANGUAGE,
                    email_verified_at=datetime.now(UTC),
                    referred_by_id=invite.referrer_user_id,
                    registered_via=f"{key}_oauth",
                    email_source=key,
                )
                created_user = True
                if invite.partner_code:
                    await PartnerProgramService(settings).attribute_user(
                        session,
                        user=user,
                        partner_code=invite.partner_code,
                        source="partner_web_link",
                        registered_via_partner_link=True,
                    )
                user_id = int(user.user_id)

            user = await user_dal.get_user_by_id(session, int(user_id))
            if not user or user.is_banned:
                return finish("access_denied")
            if not identity:
                identity = UserExternalIdentity(
                    user_id=user_id,
                    provider=key,
                    subject=profile["subject"],
                )
                session.add(identity)
            identity.email = profile.get("email")
            identity.email_verified = bool(profile.get("email_verified"))
            identity.display_name = profile.get("display_name")
            identity.picture_url = profile.get("picture_url")
            identity.last_used_at = datetime.now(UTC)
            if not user.email and identity.email_verified and identity.email:
                user.email = identity.email
                user.email_verified_at = datetime.now(UTC)
                user.notification_email = identity.email
            can_attach_identity_email = not email_owner or int(email_owner.user_id) == int(
                user.user_id
            )
            if identity.email_verified and identity.email and can_attach_identity_email:
                await user_email_dal.upsert_user_email_address(
                    session,
                    user_id=int(user.user_id),
                    email=str(identity.email),
                    source=key,
                    verified_at=datetime.now(UTC),
                    is_primary=str(user.email or "").lower() == str(identity.email).lower(),
                    is_notification=(
                        not getattr(user, "notification_email", None)
                        or str(getattr(user, "notification_email", "") or "").lower()
                        == str(identity.email).lower()
                    ),
                )
                if not getattr(user, "notification_email", None):
                    user.notification_email = identity.email
            if not user.first_name and identity.display_name:
                user.first_name = identity.display_name
            if purpose == "login":
                referral = str(state.get("referral") or "")
                referral_applied = await _apply_referral_to_existing_user(
                    request,
                    session,
                    user,
                    referral,
                )
                if created_user or referral_applied:
                    await _apply_referral_welcome_bonus_if_needed(
                        request,
                        session,
                        user,
                        referral,
                    )
            await _sync_panel_identity_for_user(request, user)
            await session.commit()
        except UserMergeConflictError:
            await session.rollback()
            logger.info("External OAuth account merge was rejected for %s", key)
            return finish("merge_conflict")
        except Exception:
            await session.rollback()
            logger.exception("External OAuth callback failed for %s", key)
            return finish("failed")

    await _invalidate_webapp_user_caches(settings, int(user_id), include_devices=True)
    token = create_webapp_session_token(settings, int(user_id))
    response = web.HTTPFound(_redirect(key, purpose, "success"))
    _clear_state_cookie(response)
    _set_webapp_auth_cookies(response, settings, token, secrets.token_hex(32))
    return response


async def external_identity_unlink_route(request: web.Request) -> web.Response:
    user_id = _extract_authenticated_user_id(request)
    if not user_id:
        return json_response({"ok": False, "error": "unauthorized"}, status=401)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppExternalIdentityPayload)
    provider = str(payload.provider)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        identity = (
            await session.execute(
                select(UserExternalIdentity).where(
                    UserExternalIdentity.user_id == user_id,
                    UserExternalIdentity.provider == provider,
                )
            )
        ).scalar_one_or_none()
        if not identity:
            return json_response({"ok": False, "error": "identity_not_found"}, status=404)
        user = await user_dal.get_user_by_id(session, user_id)
        other_external_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(UserExternalIdentity)
                    .where(
                        UserExternalIdentity.user_id == user_id,
                        UserExternalIdentity.provider != provider,
                        UserExternalIdentity.provider.in_(settings.webapp_auth_providers),
                    )
                )
            ).scalar_one()
        )
        passkey_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(UserPasskeyCredential)
                    .where(UserPasskeyCredential.user_id == user_id)
                )
            ).scalar_one()
        )
        has_other_login = bool(
            other_external_count
            or (settings.PASSKEY_LOGIN_ENABLED and passkey_count)
            or (settings.TELEGRAM_LOGIN_ENABLED and user and user.telegram_id)
            or (settings.email_auth_configured and user and user.email_verified_at)
        )
        if not has_other_login:
            return json_response({"ok": False, "error": "last_login_method"}, status=409)
        await session.delete(identity)
        await session.commit()
    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True})
