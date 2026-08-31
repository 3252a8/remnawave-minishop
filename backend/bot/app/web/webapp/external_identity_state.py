"""Shared decisions for safely unlinking external login identities."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def normalized_identity_email(identity: Any) -> str:
    if not bool(getattr(identity, "email_verified", False)):
        return ""
    return str(getattr(identity, "email", None) or "").strip().lower()


def external_identity_replacement_email(
    identity: Any,
    email_addresses: Sequence[Any],
) -> Any | None:
    provider_email = normalized_identity_email(identity)
    if not provider_email:
        return None
    return next(
        (
            address
            for address in email_addresses
            if getattr(address, "verified_at", None)
            and str(getattr(address, "email", None) or "").strip().lower() != provider_email
        ),
        None,
    )


def external_identity_email_survives(
    identity: Any,
    email_addresses: Sequence[Any],
    external_identities: Sequence[Any],
) -> bool:
    provider_email = normalized_identity_email(identity)
    if not provider_email:
        return True
    provider = str(getattr(identity, "provider", None) or "")
    address = next(
        (
            item
            for item in email_addresses
            if str(getattr(item, "email", None) or "").strip().lower() == provider_email
        ),
        None,
    )
    if address is not None and str(getattr(address, "source", None) or "") == "email":
        return True
    return any(
        str(getattr(item, "provider", None) or "") != provider
        and normalized_identity_email(item) == provider_email
        for item in external_identities
    )


def external_identity_can_unlink(
    identity: Any,
    email_addresses: Sequence[Any],
    external_identities: Sequence[Any],
    *,
    user: Any,
    has_other_external_identity: bool,
    has_passkey_login: bool,
    has_telegram_login: bool,
    email_login_enabled: bool,
) -> bool:
    provider_email = normalized_identity_email(identity)
    replacement = external_identity_replacement_email(identity, email_addresses)
    email_survives = external_identity_email_survives(
        identity,
        email_addresses,
        external_identities,
    )
    if provider_email and not email_survives and replacement is None:
        return False

    current_email = str(getattr(user, "email", None) or "").strip().lower()
    current_email_survives = bool(
        current_email
        and getattr(user, "email_verified_at", None)
        and (current_email != provider_email or email_survives)
    )
    has_email_login = bool(email_login_enabled and (current_email_survives or replacement))
    return bool(
        has_other_external_identity or has_passkey_login or has_telegram_login or has_email_login
    )


def external_identity_can_unlink_for_account(
    identity: Any,
    email_addresses: Sequence[Any],
    external_identities: Sequence[Any],
    passkey_credentials: Sequence[Any],
    *,
    user: Any,
    settings: Any,
) -> bool:
    return external_identity_can_unlink(
        identity,
        email_addresses,
        external_identities,
        user=user,
        has_other_external_identity=any(
            str(other.provider) != str(identity.provider)
            and str(other.provider) in settings.webapp_auth_providers
            for other in external_identities
        ),
        has_passkey_login=bool(settings.PASSKEY_LOGIN_ENABLED and passkey_credentials),
        has_telegram_login=bool(settings.TELEGRAM_LOGIN_ENABLED and user.telegram_id),
        email_login_enabled=bool(settings.email_auth_configured),
    )
