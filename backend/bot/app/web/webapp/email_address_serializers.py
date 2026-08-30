from collections.abc import Sequence
from typing import Any

from db.models import User, UserEmailAddress, UserExternalIdentity


def serialize_user_email_addresses(
    user: User,
    email_addresses: Sequence[UserEmailAddress],
    external_identities: Sequence[UserExternalIdentity],
) -> tuple[list[dict[str, Any]], str]:
    notification_email = str(user.notification_email or user.email or "").strip().lower()
    serialized: list[dict[str, Any]] = []
    for address in email_addresses:
        normalized_address = str(address.email or "").strip().lower()
        sources = [str(address.source or "email")]
        if user.email and normalized_address == str(user.email).strip().lower():
            sources.insert(0, "email")
        sources.extend(
            str(identity.provider)
            for identity in external_identities
            if identity.email_verified
            and identity.email
            and normalized_address == str(identity.email).strip().lower()
        )
        serialized.append(
            {
                "email": normalized_address,
                "verified": bool(address.verified_at),
                "is_primary": bool(address.is_primary),
                "is_notification": normalized_address == notification_email,
                "sources": list(dict.fromkeys(sources)),
            }
        )
    if not serialized and user.email and user.email_verified_at:
        notification_email = str(user.email).strip().lower()
        serialized.append(
            {
                "email": notification_email,
                "verified": True,
                "is_primary": True,
                "is_notification": True,
                "sources": ["email"],
            }
        )
    return serialized, notification_email
