"""Provider configuration, token exchange, and profile normalization for external OAuth."""

from __future__ import annotations

import asyncio
import hmac
import logging
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

from aiohttp import ClientSession, ClientTimeout

from config.settings import Settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = ClientTimeout(total=15)
_YANDEX_RUSSIAN_AUTHORIZATION_URL = "https://oauth.yandex.ru/authorize"

ExternalProviderKey = Literal["discord", "google", "yandex"]


@dataclass(frozen=True)
class ExternalProvider:
    key: ExternalProviderKey
    authorization_url: str
    token_url: str
    client_id: str
    client_secret: str
    scopes: tuple[str, ...]
    uses_pkce: bool = True


def provider_for_settings(settings: Settings, key: str) -> ExternalProvider | None:
    if key == "discord" and settings.DISCORD_OIDC_ENABLED:
        client_id = str(settings.DISCORD_OIDC_CLIENT_ID or "").strip()
        secret = str(settings.DISCORD_OIDC_CLIENT_SECRET or "").strip()
        if client_id and secret:
            return ExternalProvider(
                key="discord",
                authorization_url="https://discord.com/oauth2/authorize",
                token_url="https://discord.com/api/oauth2/token",
                client_id=client_id,
                client_secret=secret,
                scopes=("identify", "email"),
                uses_pkce=False,
            )
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


def authorization_url(provider: ExternalProvider, language: str) -> str:
    if provider.key == "yandex" and language.split("-", 1)[0] == "ru":
        return _YANDEX_RUSSIAN_AUTHORIZATION_URL
    return provider.authorization_url


async def exchange_token(
    provider: ExternalProvider, *, code: str, redirect_uri: str, verifier: str
) -> dict[str, Any] | None:
    form: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "redirect_uri": redirect_uri,
    }
    if provider.uses_pkce:
        form["code_verifier"] = verifier
    async with (
        ClientSession(timeout=_HTTP_TIMEOUT) as session,
        session.post(provider.token_url, data=form) as response,
    ):
        if response.status != 200:
            logger.warning("%s token exchange failed with HTTP %s", provider.key, response.status)
            return None
        payload = await response.json(content_type=None)
        return payload if isinstance(payload, dict) else None


async def google_profile(
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
            "hosted_domain": str(claims.get("hd") or "").strip().lower() or None,
            "display_name": str(claims.get("name") or "").strip() or None,
            "picture_url": str(claims.get("picture") or "").strip() or None,
        }
    except Exception:
        logger.exception("Google ID token validation failed")
        return None


def google_email_is_authoritative(profile: dict[str, Any]) -> bool:
    email = str(profile.get("email") or "").strip().lower()
    return bool(profile.get("email_verified")) and (
        email.endswith("@gmail.com") or bool(str(profile.get("hosted_domain") or "").strip())
    )


async def yandex_profile(token_payload: dict[str, Any]) -> dict[str, Any] | None:
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


async def discord_profile(token_payload: dict[str, Any]) -> dict[str, Any] | None:
    access_token = str(token_payload.get("access_token") or "")
    if not access_token:
        return None
    async with (
        ClientSession(timeout=_HTTP_TIMEOUT) as session,
        session.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as response,
    ):
        if response.status != 200:
            return None
        claims = await response.json(content_type=None)
    if not isinstance(claims, dict):
        return None
    subject = str(claims.get("id") or "").strip()
    if not subject:
        return None
    email = str(claims.get("email") or "").strip().lower() or None
    avatar_hash = str(claims.get("avatar") or "").strip()
    return {
        "subject": subject,
        "email": email,
        "email_verified": bool(email and claims.get("verified")),
        "display_name": str(claims.get("global_name") or claims.get("username") or "").strip()
        or None,
        "picture_url": (
            "https://cdn.discordapp.com/avatars/"
            f"{quote(subject, safe='')}/{quote(avatar_hash, safe='')}.png?size=256"
            if avatar_hash
            else None
        ),
    }
