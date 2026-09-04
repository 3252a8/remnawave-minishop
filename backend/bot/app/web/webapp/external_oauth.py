"""Google OIDC and Yandex OAuth login/link flows."""

from __future__ import annotations

import asyncio
import base64
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout, web
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_email_auth_service, get_session_factory, get_settings
from bot.app.web.webapp_auth import (
    create_signed_telegram_oauth_state,
    create_webapp_session_token,
    verify_signed_telegram_oauth_state,
)
from bot.infra import events
from bot.infra.event_payloads import (
    AccountExternalIdentityLinkedPayload,
    UserRegisteredPayload,
)
from bot.services.partner_program_service import PartnerProgramService
from bot.services.registration_invite_gate import evaluate_registration_invite
from config.settings import Settings
from db.dal import user_dal, user_email_dal
from db.dal.user_dal import UserMergeConflictError
from db.models import UserExternalIdentity

from .auth import (
    _merge_users_for_web,
    _sync_merged_panel_identity_for_user,
    _sync_panel_identity_for_user,
)
from .auth_common import (
    _build_webapp_auth_response,
    _public_webapp_base_url,
    _set_webapp_auth_cookies,
    _urlsafe_sha256,
)
from .auth_referral import (
    _apply_referral_to_existing_user,
    _apply_referral_welcome_bonus_if_needed,
)
from .common import (
    _extract_authenticated_user_id,
    _invalidate_webapp_user_caches,
    _normalize_language,
    _parse_model_payload,
    _telegram_id_for_user,
)
from .payloads import WebAppEmailChangeCurrentPayload
from .response_helpers import json_response

logger = logging.getLogger(__name__)

_STATE_COOKIE = "rw_external_oauth_state"
_PENDING_COOKIE = "rw_external_oauth_pending"
_PENDING_COOKIE_PATH = "/api/auth/external"
_PENDING_PURPOSE = "external_oauth_link"
_HTTP_TIMEOUT = ClientTimeout(total=15)
_YANDEX_RUSSIAN_AUTHORIZATION_URL = "https://oauth.yandex.ru/authorize"

ExternalProviderKey = Literal["google", "yandex"]
ExternalRegistrationSource = Literal["google_oauth", "yandex_oauth"]
_REGISTRATION_SOURCE_BY_PROVIDER: dict[ExternalProviderKey, ExternalRegistrationSource] = {
    "google": "google_oauth",
    "yandex": "yandex_oauth",
}


@dataclass(frozen=True)
class ExternalProvider:
    key: ExternalProviderKey
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


def _authorization_url(provider: ExternalProvider, language: str) -> str:
    if provider.key == "yandex" and language.split("-", 1)[0] == "ru":
        return _YANDEX_RUSSIAN_AUTHORIZATION_URL
    return provider.authorization_url


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


def _set_pending_cookie(
    response: web.StreamResponse, settings: Settings, payload: dict[str, Any]
) -> None:
    ttl = max(60, int(settings.EMAIL_CODE_TTL_SECONDS))
    response.set_cookie(
        _PENDING_COOKIE,
        create_signed_telegram_oauth_state(settings, payload, ttl_seconds=ttl),
        httponly=True,
        secure=True,
        samesite="Lax",
        path=_PENDING_COOKIE_PATH,
        max_age=ttl,
    )


def _clear_pending_cookie(response: web.StreamResponse) -> None:
    response.set_cookie(
        _PENDING_COOKIE,
        "",
        httponly=True,
        secure=True,
        samesite="Lax",
        path=_PENDING_COOKIE_PATH,
        max_age=0,
    )


def _read_pending(request: web.Request) -> dict[str, Any] | None:
    settings: Settings = get_settings(request)
    payload = verify_signed_telegram_oauth_state(settings, request.cookies.get(_PENDING_COOKIE, ""))
    if not payload:
        return None
    provider = str(payload.get("provider") or "").lower()
    subject = str(payload.get("subject") or "")
    email = str(payload.get("email") or "").strip().lower()
    try:
        target_user_id = int(payload.get("target_user_id") or 0)
    except (TypeError, ValueError):
        return None
    if provider not in {"google", "yandex"} or not subject or not email or not target_user_id:
        return None
    return {**payload, "provider": provider, "email": email, "target_user_id": target_user_id}


def _masked_email(email: str) -> str:
    local, separator, domain = str(email or "").partition("@")
    if not separator or not local or not domain:
        return "***"
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


async def _verified_email_owner(session: Any, email: str) -> Any | None:
    owner = await user_email_dal.get_user_by_verified_email_address(session, email)
    if owner is not None:
        return owner
    legacy_owner = await user_dal.get_user_by_email(session, email)
    if legacy_owner is not None and getattr(legacy_owner, "email_verified_at", None):
        return legacy_owner
    return None


async def _pending_target(
    session: Any,
    pending: dict[str, Any],
    *,
    lock: bool,
) -> tuple[Any | None, UserExternalIdentity | None, str | None]:
    target_user_id = int(pending["target_user_id"])
    user = (
        await user_dal.lock_user_by_id(session, target_user_id)
        if lock
        else await user_dal.get_user_by_id(session, target_user_id)
    )
    if user is None:
        return None, None, "pending_expired"
    if user.is_banned:
        return None, None, "access_denied"
    email_owner = await _verified_email_owner(session, str(pending["email"]))
    if email_owner is None or int(email_owner.user_id) != target_user_id:
        return None, None, "email_owner_changed"

    identity_query = select(UserExternalIdentity).where(
        UserExternalIdentity.provider == pending["provider"],
        UserExternalIdentity.subject == pending["subject"],
    )
    if lock:
        identity_query = identity_query.with_for_update()
    identity = (await session.execute(identity_query)).scalar_one_or_none()
    if identity is not None and int(identity.user_id) != target_user_id:
        return None, None, "identity_conflict"

    provider_identity_query = select(UserExternalIdentity).where(
        UserExternalIdentity.user_id == target_user_id,
        UserExternalIdentity.provider == pending["provider"],
    )
    if lock:
        provider_identity_query = provider_identity_query.with_for_update()
    provider_identity = (await session.execute(provider_identity_query)).scalar_one_or_none()
    if provider_identity is not None and provider_identity.subject != pending["subject"]:
        return None, None, "provider_conflict"
    return user, identity or provider_identity, None


def _pending_error(error: str, *, status: int = 409, clear: bool = False) -> web.Response:
    response = json_response({"ok": False, "error": error}, status=status)
    if clear:
        _clear_pending_cookie(response)
    return response


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

    language = _normalize_language(str(request.query.get("lang") or settings.DEFAULT_LANGUAGE))
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
        "language": language,
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
    response = web.HTTPFound(f"{_authorization_url(provider, language)}?{urlencode(query)}")
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
    identity_was_linked = False
    merged_source_user_ids: list[int] = []
    merged_source_panel_uuids: list[str] = []
    registration_event: UserRegisteredPayload | None = None
    identity_link_event: AccountExternalIdentityLinkedPayload | None = None
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
                await _verified_email_owner(session, verified_email) if verified_email else None
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
                identity_was_linked = identity is None or int(identity.user_id) != requested_user_id
                merge_sources: list[tuple[int, str]] = []
                if email_owner and int(email_owner.user_id) != requested_user_id:
                    merge_sources.append((int(email_owner.user_id), f"{key}_verified_email_link"))
                if identity and int(identity.user_id) != requested_user_id:
                    identity_owner_id = int(identity.user_id)
                    if all(source_id != identity_owner_id for source_id, _ in merge_sources):
                        merge_sources.append((identity_owner_id, f"{key}_oauth_link"))
                for source_user_id, reason in merge_sources:
                    source_user = await user_dal.get_user_by_id(session, source_user_id)
                    source_panel_uuid = (
                        str(getattr(source_user, "panel_user_uuid", ""))
                        if source_user and getattr(source_user, "panel_user_uuid", None)
                        else None
                    )
                    merged_user = await _merge_users_for_web(
                        request,
                        session,
                        source_user_id=source_user_id,
                        target_user_id=requested_user_id,
                        reason=reason,
                        send_user_email=True,
                    )
                    if source_panel_uuid and source_panel_uuid != str(
                        merged_user.panel_user_uuid or ""
                    ):
                        merged_source_panel_uuids.append(source_panel_uuid)
                    merged_source_user_ids.append(source_user_id)
                if email_owner and int(email_owner.user_id) != requested_user_id:
                    email_owner = await user_dal.get_user_by_id(session, requested_user_id)
                if identity:
                    identity.user_id = requested_user_id
                user_id = requested_user_id
            elif identity:
                user_id = int(identity.user_id)
            else:
                email = verified_email or None
                if email_owner:
                    if email_owner.is_banned:
                        return finish("access_denied")
                    await user_email_dal.ensure_primary_user_email_address(session, email_owner)
                    email_service = get_email_auth_service(request)
                    request_result = await email_service.request_code(
                        session,
                        email=email,
                        purpose=_PENDING_PURPOSE,
                        language_code=_normalize_language(
                            str(email_owner.language_code or settings.DEFAULT_LANGUAGE)
                        ),
                        target_user_id=int(email_owner.user_id),
                    )
                    if not request_result.ok and request_result.error != "rate_limited":
                        await session.rollback()
                        logger.info(
                            "External OAuth email confirmation could not start for %s: %s",
                            key,
                            request_result.error,
                        )
                        return finish("email_confirmation_unavailable")
                    await session.commit()
                    now = int(time.time())
                    retry_after = int(
                        request_result.retry_after or settings.EMAIL_CODE_RESEND_SECONDS or 60
                    )
                    pending_payload: dict[str, Any] = {
                        "provider": key,
                        "subject": str(profile["subject"])[:255],
                        "email": email,
                        "target_user_id": int(email_owner.user_id),
                        "display_name": str(profile.get("display_name") or "")[:255],
                        "picture_url": str(profile.get("picture_url") or "")[:1024],
                        "referral": str(state.get("referral") or "")[:128],
                        "resend_at": now + max(0, retry_after),
                    }
                    if request_result.code:
                        pending_payload["email_code"] = str(request_result.code)
                    response = web.HTTPFound(_redirect(key, purpose, "email_confirmation_required"))
                    _clear_state_cookie(response)
                    _set_pending_cookie(response, settings, pending_payload)
                    return response
                user = await user_dal.get_user_by_email(session, email) if email else None
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
                    language_code=_normalize_language(
                        str(state.get("language") or settings.DEFAULT_LANGUAGE)
                    ),
                    email_verified_at=datetime.now(UTC),
                    referred_by_id=invite.referrer_user_id,
                    registered_via=None,
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
            if not merged_source_user_ids:
                await _sync_panel_identity_for_user(request, user)
            if created_user:
                registration_event = UserRegisteredPayload(
                    user_id=int(user.user_id),
                    language=getattr(user, "language_code", None),
                    referred_by_id=getattr(user, "referred_by_id", None),
                    registered_via=_REGISTRATION_SOURCE_BY_PROVIDER[provider.key],
                    telegram_id=getattr(user, "telegram_id", None),
                    username=getattr(user, "username", None),
                    first_name=getattr(user, "first_name", None),
                    email=getattr(user, "email", None),
                )
            elif purpose == "link" and identity_was_linked:
                identity_link_event = AccountExternalIdentityLinkedPayload(
                    user_id=int(user.user_id),
                    provider=provider.key,
                    link_source="settings",
                    email=identity.email or getattr(user, "email", None),
                    telegram_id=getattr(user, "telegram_id", None),
                    username=getattr(user, "username", None),
                    first_name=getattr(user, "first_name", None),
                )
            await session.commit()
            if merged_source_user_ids:
                panel_uuids_to_remove: list[str | None] = list(
                    dict.fromkeys(merged_source_panel_uuids)
                ) or [None]
                for source_panel_uuid in panel_uuids_to_remove:
                    await _sync_merged_panel_identity_for_user(
                        request,
                        user,
                        source_panel_uuid=source_panel_uuid,
                        final_panel_uuid=(
                            str(getattr(user, "panel_user_uuid", ""))
                            if getattr(user, "panel_user_uuid", None)
                            else None
                        ),
                        session=session,
                    )
        except UserMergeConflictError as exc:
            await session.rollback()
            logger.info("External OAuth account merge was rejected for %s", key)
            return finish(exc.code)
        except Exception:
            await session.rollback()
            logger.exception("External OAuth callback failed for %s", key)
            return finish("failed")

    if registration_event is not None:
        await events.emit_model(registration_event)
        logger.info(
            "External OAuth registration committed provider=%s user_id=%s",
            provider.key,
            user_id,
        )
    if identity_link_event is not None:
        await events.emit_model(identity_link_event)
        logger.info(
            "External OAuth identity linked provider=%s user_id=%s merged_source_user_ids=%s",
            provider.key,
            user_id,
            merged_source_user_ids,
        )
    await _invalidate_webapp_user_caches(settings, int(user_id), include_devices=True)
    token = create_webapp_session_token(settings, int(user_id))
    response = web.HTTPFound(_redirect(key, purpose, "success"))
    _clear_state_cookie(response)
    _set_webapp_auth_cookies(response, settings, token, secrets.token_hex(32))
    return response


async def external_oauth_pending_status_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    pending = _read_pending(request)
    if not pending:
        return _pending_error("pending_expired", status=410, clear=True)
    if not _provider(settings, str(pending["provider"])):
        return _pending_error("provider_disabled", status=410, clear=True)

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user, _identity, error = await _pending_target(session, pending, lock=False)
        if error or user is None:
            return _pending_error(error or "pending_expired", status=409, clear=True)

    retry_after = max(0, int(pending.get("resend_at") or 0) - int(time.time()))
    payload: dict[str, Any] = {
        "ok": True,
        "provider": pending["provider"],
        "email": _masked_email(str(pending["email"])),
        "retry_after": retry_after,
    }
    if settings.qa_auth_enabled and pending.get("email_code"):
        payload["email_code"] = str(pending["email_code"])
    return json_response(payload)


async def external_oauth_pending_request_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    pending = _read_pending(request)
    if not pending:
        return _pending_error("pending_expired", status=410, clear=True)
    if not _provider(settings, str(pending["provider"])):
        return _pending_error("provider_disabled", status=410, clear=True)

    email_service = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user, _identity, error = await _pending_target(session, pending, lock=False)
        if error or user is None:
            return _pending_error(error or "pending_expired", status=409, clear=True)
        result = await email_service.request_code(
            session,
            email=str(pending["email"]),
            purpose=_PENDING_PURPOSE,
            language_code=_normalize_language(str(user.language_code or settings.DEFAULT_LANGUAGE)),
            target_user_id=int(user.user_id),
        )
        await session.commit()
    if not result.ok:
        status = 429 if result.error == "rate_limited" else 503
        return json_response(
            {
                "ok": False,
                "error": result.error or "email_confirmation_unavailable",
                "retry_after": result.retry_after,
            },
            status=status,
        )

    retry_after = max(1, int(settings.EMAIL_CODE_RESEND_SECONDS))
    pending["resend_at"] = int(time.time()) + retry_after
    if result.code:
        pending["email_code"] = str(result.code)
    else:
        pending.pop("email_code", None)
    response_payload: dict[str, Any] = {"ok": True, "retry_after": retry_after}
    if settings.qa_auth_enabled and result.code:
        response_payload["email_code"] = str(result.code)
    response = json_response(response_payload)
    _set_pending_cookie(response, settings, pending)
    return response


async def external_oauth_pending_verify_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    pending = _read_pending(request)
    if not pending:
        return _pending_error("pending_expired", status=410, clear=True)
    provider = _provider(settings, str(pending["provider"]))
    if not provider:
        return _pending_error("provider_disabled", status=410, clear=True)

    code_payload = await _parse_model_payload(request, WebAppEmailChangeCurrentPayload)
    email_service = get_email_auth_service(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    user_id: int | None = None
    telegram_id: int | None = None
    identity_link_event: AccountExternalIdentityLinkedPayload | None = None
    async with async_session_factory() as session:
        try:
            user, identity, error = await _pending_target(session, pending, lock=True)
            if error or user is None:
                await session.rollback()
                return _pending_error(error or "pending_expired", status=409, clear=True)

            verify_result = await email_service.verify_code(
                session,
                email=str(pending["email"]),
                purpose=_PENDING_PURPOSE,
                code=str(code_payload.code or ""),
                target_user_id=int(user.user_id),
            )
            if not verify_result.ok:
                await session.commit()
                status = 429 if verify_result.error == "rate_limited" else 400
                return json_response(
                    {
                        "ok": False,
                        "error": verify_result.error or "invalid_code",
                        "retry_after": verify_result.retry_after,
                    },
                    status=status,
                )

            identity_was_linked = identity is None
            if identity_was_linked:
                identity = UserExternalIdentity(
                    user_id=int(user.user_id),
                    provider=str(pending["provider"]),
                    subject=str(pending["subject"]),
                )
                session.add(identity)
            assert identity is not None
            identity.email = str(pending["email"])
            identity.email_verified = True
            identity.display_name = str(pending.get("display_name") or "") or None
            identity.picture_url = str(pending.get("picture_url") or "") or None
            identity.last_used_at = datetime.now(UTC)
            await user_email_dal.upsert_user_email_address(
                session,
                user_id=int(user.user_id),
                email=str(pending["email"]),
                source=str(pending["provider"]),
                verified_at=datetime.now(UTC),
                is_primary=False,
                is_notification=False,
            )
            if not user.first_name and identity.display_name:
                user.first_name = identity.display_name

            referral = str(pending.get("referral") or "")
            referral_applied = await _apply_referral_to_existing_user(
                request, session, user, referral
            )
            if referral_applied:
                await _apply_referral_welcome_bonus_if_needed(request, session, user, referral)
            await _sync_panel_identity_for_user(request, user)
            user_id = int(user.user_id)
            telegram_id = _telegram_id_for_user(user)
            if identity_was_linked:
                identity_link_event = AccountExternalIdentityLinkedPayload(
                    user_id=user_id,
                    provider=provider.key,
                    link_source="email_confirmation",
                    email=str(pending["email"]),
                    telegram_id=telegram_id,
                    username=getattr(user, "username", None),
                    first_name=getattr(user, "first_name", None),
                )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info(
                "External OAuth email confirmation raced with another identity for %s",
                pending["provider"],
            )
            return _pending_error("identity_conflict", status=409, clear=True)
        except Exception:
            await session.rollback()
            logger.exception("External OAuth email confirmation failed for %s", pending["provider"])
            return _pending_error("email_confirmation_failed", status=500)

    if identity_link_event is not None:
        await events.emit_model(identity_link_event)
        logger.info(
            "External OAuth identity linked after email confirmation provider=%s user_id=%s",
            provider.key,
            user_id,
        )
    await _invalidate_webapp_user_caches(settings, int(user_id), include_devices=True)
    token = create_webapp_session_token(settings, int(user_id))
    response = _build_webapp_auth_response(
        settings,
        {"user_id": int(user_id), "telegram_id": telegram_id},
        token=token,
    )
    _clear_pending_cookie(response)
    return response


async def external_oauth_pending_cancel_route(request: web.Request) -> web.Response:
    response = json_response({"ok": True})
    _clear_pending_cookie(response)
    return response
