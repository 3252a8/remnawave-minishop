"""Shared conversion helpers for admin API response models.

Small, self-contained functions used by the ``from_orm_*`` constructors in
``schemas.py`` to derive display labels and coerce loosely-typed ORM scalars.
Kept in a dedicated module so ``schemas.py`` stays focused on the contracts
themselves.
"""

from __future__ import annotations

from typing import Any


def traffic_gb_split(payment: Any) -> tuple[float | None, float | None]:
    if payment.purchased_gb is None:
        return None, None
    try:
        gb = float(payment.purchased_gb)
    except (TypeError, ValueError):
        return None, None
    sale_mode = (payment.sale_mode or "").strip()
    if not sale_mode:
        return None, None
    base = sale_mode.split("@", 1)[0].split("|", 1)[0].lower()
    if base == "premium_topup":
        return None, gb
    if base in {"traffic", "traffic_package", "topup"}:
        return gb, None
    return None, None


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
    return str(fallback_user_id)


def payment_user_display_label(loaded_user: Any, payment_user_id: int) -> str:
    label = display_label(loaded_user, payment_user_id)
    return label or str(payment_user_id)


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
