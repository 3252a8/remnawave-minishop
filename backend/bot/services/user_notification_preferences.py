"""Per-user notification preferences and signed email preference links."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from bot.services.email_templates_common import EmailContent, add_email_preferences_footer

_TOKEN_VERSION = 1
_TOKEN_DOMAIN = b"remnawave-minishop:notification-preferences:v1\0"


@dataclass(frozen=True)
class UserNotificationPreferences:
    marketing_email: bool = True
    marketing_telegram: bool = True
    system_email: bool = True
    system_telegram: bool = True

    @classmethod
    def from_user(cls, user: Any) -> UserNotificationPreferences:
        return cls(
            marketing_email=bool(getattr(user, "marketing_notifications_email_enabled", True)),
            marketing_telegram=bool(
                getattr(user, "marketing_notifications_telegram_enabled", True)
            ),
            system_email=bool(getattr(user, "system_notifications_email_enabled", True)),
            system_telegram=bool(getattr(user, "system_notifications_telegram_enabled", True)),
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            "marketing_email": self.marketing_email,
            "marketing_telegram": self.marketing_telegram,
            "system_email": self.system_email,
            "system_telegram": self.system_telegram,
        }


def user_notification_preferences_enabled(settings: Any) -> bool:
    try:
        return bool(settings.USER_NOTIFICATION_PREFERENCES_ENABLED)
    except AttributeError:
        return True


def apply_user_notification_preferences(
    user: Any,
    preferences: UserNotificationPreferences,
) -> None:
    user.marketing_notifications_email_enabled = preferences.marketing_email
    user.marketing_notifications_telegram_enabled = preferences.marketing_telegram
    user.system_notifications_email_enabled = preferences.system_email
    user.system_notifications_telegram_enabled = preferences.system_telegram


def notification_email_for_user(user: Any) -> str:
    return (
        str(getattr(user, "notification_email", None) or getattr(user, "email", "") or "")
        .strip()
        .lower()
    )


def _email_digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_email_preferences_token(settings: Any, user: Any, *, email: str | None = None) -> str:
    recipient = (email or notification_email_for_user(user)).strip().lower()
    if not recipient:
        return ""
    payload = json.dumps(
        {
            "email_digest": _email_digest(recipient),
            "user_id": int(user.user_id),
            "version": _TOKEN_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    try:
        session_secret = str(settings.WEBAPP_SESSION_SECRET)
    except AttributeError:
        return ""
    signature = hmac.new(
        session_secret.encode("utf-8"),
        _TOKEN_DOMAIN + payload,
        hashlib.sha256,
    ).digest()
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def verify_email_preferences_token(settings: Any, token: str) -> tuple[int, str] | None:
    try:
        payload_part, signature_part = str(token or "").split(".", 1)
        payload = _b64decode(payload_part)
        signature = _b64decode(signature_part)
        expected = hmac.new(
            str(settings.WEBAPP_SESSION_SECRET).encode("utf-8"),
            _TOKEN_DOMAIN + payload,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        decoded = json.loads(payload)
        if int(decoded.get("version", 0)) != _TOKEN_VERSION:
            return None
        return int(decoded["user_id"]), str(decoded["email_digest"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def token_matches_user_email(user: Any, email_digest: str) -> bool:
    email = notification_email_for_user(user)
    return bool(email) and hmac.compare_digest(_email_digest(email), email_digest)


def build_email_preferences_url(
    settings: Any,
    user: Any,
    *,
    email: str | None = None,
) -> str:
    if not user_notification_preferences_enabled(settings):
        return ""
    try:
        base_url = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    except AttributeError:
        return ""
    if not base_url:
        return ""
    token = create_email_preferences_token(settings, user, email=email)
    if not token:
        return ""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = f"{parsed.path.rstrip('/')}/unsubscribe"
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"token": token}), ""))


def _translate(i18n: Any, language: str, key: str, fallback: str) -> str:
    if i18n is None:
        return fallback
    value = str(i18n.gettext(language, key) or "")
    return fallback if value == key else value


def add_user_email_preferences_footer(
    content: EmailContent,
    *,
    settings: Any,
    i18n: Any,
    user: Any,
    email: str | None = None,
    language_code: str | None = None,
) -> EmailContent:
    preferences_url = build_email_preferences_url(settings, user, email=email)
    if not preferences_url:
        return content
    try:
        default_language = settings.DEFAULT_LANGUAGE
    except AttributeError:
        default_language = "ru"
    language = str(language_code or getattr(user, "language_code", "") or default_language or "ru")
    return add_email_preferences_footer(
        content,
        url=preferences_url,
        label=_translate(
            i18n,
            language,
            "email_unsubscribe_button",
            "Manage email notifications",
        ),
        hint=_translate(
            i18n,
            language,
            "email_unsubscribe_hint",
            "Choose which marketing and system emails you want to receive.",
        ),
    )
