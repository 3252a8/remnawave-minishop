from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from db.models import User

_ZERO_SCALE_CURRENCIES = {"CLP", "ISK", "JPY", "KRW", "PYG", "VND", "XTR"}
_THREE_SCALE_CURRENCIES = {"BHD", "JOD", "KWD", "OMR", "TND"}


@dataclass(slots=True)
class PartnerError(Exception):
    code: str
    status: int = 400
    message: str = ""

    def __str__(self) -> str:
        return self.message or self.code


def currency_scale(currency: str) -> int:
    normalized = str(currency or "").strip().upper()
    if normalized in _ZERO_SCALE_CURRENCIES:
        return 0
    if normalized in _THREE_SCALE_CURRENCIES:
        return 3
    return 2


def amount_to_minor(amount: Any, *, scale: int) -> int:
    factor = Decimal(10) ** scale
    return int((Decimal(str(amount)) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def commission_minor(gross_minor: int, commission_bps: int) -> int:
    return int(
        (Decimal(gross_minor) * Decimal(commission_bps) / Decimal(10000)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def minor_to_decimal_string(amount_minor: int, *, scale: int) -> str:
    return format(Decimal(amount_minor) / (Decimal(10) ** scale), f".{scale}f")


def safe_user_label(user: User | None, fallback: str = "User") -> str:
    if user is None:
        return fallback
    full_name = " ".join(
        part.strip()
        for part in (str(user.first_name or ""), str(user.last_name or ""))
        if part.strip()
    )
    if full_name:
        return full_name[:255]
    if user.username:
        return f"@{str(user.username).strip().lstrip('@')}"[:255]
    if user.email:
        local, _, domain = str(user.email).partition("@")
        masked = f"{local[:2]}***@{domain}" if domain else "Email user"
        return masked[:255]
    return f"{fallback} {int(user.user_id)}"[:255]


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
