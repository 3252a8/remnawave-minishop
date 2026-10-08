"""Shared conversion helpers for admin API response models.

Small, self-contained functions used by the ``from_orm_*`` constructors in
``schemas.py`` to derive display labels and coerce loosely-typed ORM scalars.
Kept in a dedicated module so ``schemas.py`` stays focused on the contracts
themselves.
"""

from __future__ import annotations

from typing import Any

from bot.app.web.payment_purchases import traffic_gb_split as traffic_gb_split


def display_label(
    loaded_user: Any,
    fallback_user_id: int | None,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    email: str | None = None,
) -> str | None:
    telegram_id = getattr(loaded_user, "telegram_id", None)
    if loaded_user is not None and telegram_id is not None:
        first = (getattr(loaded_user, "first_name", None) or "").strip()
        last = (getattr(loaded_user, "last_name", None) or "").strip()
        full_name = f"{first} {last}".strip()
        if full_name:
            return full_name
        loaded_username = (getattr(loaded_user, "username", None) or "").strip()
        if loaded_username:
            return loaded_username if loaded_username.startswith("@") else f"@{loaded_username}"
    elif loaded_user is not None:
        loaded_email = (getattr(loaded_user, "email", None) or "").strip()
        if loaded_email:
            return loaded_email
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    full_name = f"{first} {last}".strip()
    if full_name:
        return full_name
    username_value = (username or "").strip()
    if username_value:
        return username_value if username_value.startswith("@") else f"@{username_value}"
    email_value = (email or "").strip()
    if email_value:
        return email_value
    if fallback_user_id is None:
        return None
    return str(getattr(loaded_user, "minishop_id", None) or "—")


def payment_user_display_label(loaded_user: Any, payment_user_id: int) -> str:
    label = display_label(loaded_user, payment_user_id)
    return label or "—"


def float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_float_or_none(*values: Any) -> float | None:
    for value in values:
        parsed = float_or_none(value)
        if parsed is not None:
            return parsed
    return None
