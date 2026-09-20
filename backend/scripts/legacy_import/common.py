"""Source-agnostic helpers and shared constants for legacy imports."""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


async def _path_exists(path: Path) -> bool:
    return await asyncio.to_thread(path.exists)


async def _path_read_text(path: Path, *, encoding: str) -> str:
    return await asyncio.to_thread(path.read_text, encoding=encoding)


async def _path_write_text(path: Path, value: str, *, encoding: str) -> None:
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, value, encoding=encoding)


SOURCE = "remnashop"
REMNASHOP_ENCRYPTED_PREFIX = "enc_"
PLACEHOLDER_SETTING_VALUES = {"change_me", "changeme"}
GIB = 1024**3
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
SAFE_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REMNASHOP_PAYMENT_WEBHOOK_PATH = "/api/v1/payments/{gateway}"
REMNASHOP_PANEL_WEBHOOK_PATH = "/api/v1/remnawave"

SUPPORTED_REMNASHOP_PROVIDER_TYPES = {
    "TELEGRAM_STARS",
    "YOOKASSA",
    "HELEKET",
    "PAYKILLA",
    "CRYPTOPAY",
    "FREEKASSA",
    "PLATEGA",
    "WATA",
}
UNSUPPORTED_REMNASHOP_PROVIDER_TYPES = {
    "YOOMONEY",
    "CRYPTOMUS",
    "MULENPAY",
    "PAYMASTER",
    "ROBOKASSA",
    "URLPAY",
}
PAYMENT_WEBHOOK_PATHS = {
    "yookassa": "/webhook/yookassa",
    "wata": "/webhook/wata",
    "cryptopay": "/webhook/cryptopay",
    "heleket": "/webhook/heleket",
    "paykilla": "/webhook/paykilla",
    "freekassa": "/webhook/freekassa",
    "platega": "/webhook/platega",
}


def normalize_async_postgres_dsn(dsn: str) -> str:
    value = str(dsn or "").strip()
    if value.startswith("postgresql+asyncpg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if value.startswith("postgres://"):
        return "postgresql+asyncpg://" + value.removeprefix("postgres://")
    return value


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _safe_schema_name(schema: str) -> str:
    value = str(schema or "public").strip()
    if not SAFE_SCHEMA_RE.fullmatch(value):
        raise ValueError(f"Unsafe PostgreSQL schema name: {schema!r}")
    return value


def _qtable(schema: str, table: str) -> str:
    schema = _safe_schema_name(schema)
    return f'"{schema}"."{table}"'


def _as_mapping(row: Any) -> dict[str, Any]:
    return dict(row._mapping if hasattr(row, "_mapping") else row)


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        text_value = str(value).strip()
        if not text_value:
            return None
        try:
            result = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        return result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_decimal(value)
    if number is None:
        return None
    try:
        return int(number)
    except (OverflowError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    number = _to_decimal(value)
    if number is None:
        return None
    try:
        return float(number)
    except (OverflowError, ValueError):
        return None


def _split_name(name: Any) -> tuple[str | None, str | None]:
    value = str(name or "").strip()
    if not value:
        return None, None
    parts = value.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0][:255], None
    return parts[0][:255], parts[1][:255]


def _jsonish(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "active"}


def _listish(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _counter() -> dict[str, int]:
    return defaultdict(int)
