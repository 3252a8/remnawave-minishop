"""Import data from legacy source bots into the current shop database.

Currently supported source:
    remnashop

Example:
    python backend/scripts/import_legacy.py \
        --source-type remnashop \
        --source-dsn postgresql://user:pass@localhost:5432/remnashop \
        --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import shlex
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.settings import Settings  # noqa: E402
from db.dal import user_dal  # noqa: E402
from db.migrator import run_database_migrations  # noqa: E402
from db.models import (  # noqa: E402
    AppSettingOverride,
    Base,
    LegacyImportMapping,
    LegacyReferralCode,
    MessageLog,
    Payment,
    PromoCode,
    PromoCodeActivation,
    Subscription,
    User,
)

try:  # cryptography is already used by the app for payment webhook validation.
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - defensive fallback for minimal tooling.
    Fernet = None  # type: ignore[assignment]

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
    "freekassa": "/webhook/freekassa",
    "platega": "/webhook/platega",
}

logger = logging.getLogger(__name__)


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


def _as_utc(value: Any) -> Optional[datetime]:
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
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    number = _to_decimal(value)
    if number is None:
        return None
    try:
        return int(number)
    except (OverflowError, ValueError):
        return None


def _split_name(name: Any) -> tuple[Optional[str], Optional[str]]:
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


def _strip_env_value(value: str) -> str:
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        tokens = list(lexer)
    except ValueError:
        return value.strip().strip("\"'")
    return " ".join(tokens).strip()


def parse_remnashop_env_text(text_value: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in str(text_value or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        env[key] = _strip_env_value(value)
    return env


def read_remnashop_env_file(path: Optional[str]) -> dict[str, str]:
    if not path:
        return {}
    return parse_remnashop_env_text(Path(path).read_text(encoding="utf-8"))


def _is_placeholder_setting_value(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in PLACEHOLDER_SETTING_VALUES


def _clean_url(value: Any) -> Optional[str]:
    if _is_placeholder_setting_value(value):
        return None
    text_value = str(value or "").strip().rstrip("/")
    return text_value or None


def _remnashop_panel_api_url(value: Any) -> Optional[str]:
    host = _clean_url(value)
    if not host:
        return None
    if "://" not in host:
        if "." in host:
            host = f"https://{host}"
        else:
            host = f"http://{host}:3000"
    if not host.rstrip("/").endswith("/api"):
        host = f"{host.rstrip('/')}/api"
    return host


def _source_public_base_from_env(env: dict[str, str]) -> Optional[str]:
    domain = _clean_url(env.get("APP_DOMAIN"))
    if not domain:
        return None
    if "://" not in domain:
        domain = f"https://{domain}"
    return domain


def _support_link_from_username(value: Any) -> Optional[str]:
    if _is_placeholder_setting_value(value):
        return None
    username = str(value or "").strip().lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}"


def _add_override(overrides: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return
        if value.lower() in PLACEHOLDER_SETTING_VALUES:
            return
    overrides[key] = value


def remnashop_env_overrides(env: dict[str, str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    _add_override(overrides, "PANEL_API_URL", _remnashop_panel_api_url(env.get("REMNAWAVE_HOST")))
    _add_override(overrides, "PANEL_API_KEY", env.get("REMNAWAVE_TOKEN"))
    _add_override(overrides, "PANEL_WEBHOOK_SECRET", env.get("REMNAWAVE_WEBHOOK_SECRET"))
    _add_override(
        overrides,
        "SUPPORT_LINK",
        _support_link_from_username(env.get("BOT_SUPPORT_USERNAME")),
    )
    _add_override(overrides, "DEFAULT_LANGUAGE", env.get("APP_DEFAULT_LOCALE"))
    return overrides


def remnashop_source_urls_from_env(env: dict[str, str]) -> dict[str, str]:
    base = _source_public_base_from_env(env)
    if not base:
        return {}
    return {
        "telegram": f"{base}/api/v1/telegram",
        "remnawave_panel": f"{base}{REMNASHOP_PANEL_WEBHOOK_PATH}",
        "payments": f"{base}/api/v1/payments/<gateway>",
    }


def _normalize_gateway_type(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    text_value = str(value or "").strip().upper()
    if "." in text_value:
        text_value = text_value.rsplit(".", 1)[-1]
    return re.sub(r"[^A-Z0-9_]+", "_", text_value).strip("_")


def _normalize_currency(value: Any) -> Optional[str]:
    text_value = str(value or "").strip().upper()
    if "." in text_value:
        text_value = text_value.rsplit(".", 1)[-1]
    aliases = {"RUR": "RUB", "STARS": "XTR", "STAR": "XTR"}
    normalized = aliases.get(text_value, text_value)
    return normalized or None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "active"}


def _is_encrypted_remnashop_value(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(REMNASHOP_ENCRYPTED_PREFIX)


def remnashop_decrypt_value(value: Any, crypt_key: Optional[str]) -> tuple[Any, bool]:
    if not _is_encrypted_remnashop_value(value):
        return value, False
    if not crypt_key or Fernet is None:
        return None, True
    try:
        token = str(value).removeprefix(REMNASHOP_ENCRYPTED_PREFIX).encode()
        return Fernet(crypt_key.encode()).decrypt(token).decode(), False
    except Exception:
        return None, True


def remnashop_decrypt_recursive(
    value: Any,
    crypt_key: Optional[str],
    *,
    skipped_paths: Optional[list[str]] = None,
    path: str = "",
) -> Any:
    if isinstance(value, dict):
        return {
            key: remnashop_decrypt_recursive(
                item,
                crypt_key,
                skipped_paths=skipped_paths,
                path=f"{path}.{key}" if path else str(key),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            remnashop_decrypt_recursive(
                item,
                crypt_key,
                skipped_paths=skipped_paths,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]
    decrypted, skipped = remnashop_decrypt_value(value, crypt_key)
    if skipped and skipped_paths is not None:
        skipped_paths.append(path or "<value>")
    return decrypted


def _provider_mapping_result(
    gateway_type: str,
    provider_ids: Iterable[str],
    overrides: dict[str, Any],
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "source_type": gateway_type,
        "provider_ids": [provider for provider in provider_ids if provider],
        "overrides": overrides,
        "warnings": warnings or [],
        "supported": True,
    }


def remnashop_payment_gateway_overrides(
    row: dict[str, Any],
    *,
    crypt_key: Optional[str] = None,
) -> dict[str, Any]:
    gateway_type = _normalize_gateway_type(row.get("type"))
    if gateway_type not in SUPPORTED_REMNASHOP_PROVIDER_TYPES:
        return {
            "source_type": gateway_type,
            "provider_ids": [],
            "overrides": {},
            "warnings": [],
            "supported": False,
        }

    skipped_secret_paths: list[str] = []
    settings = remnashop_decrypt_recursive(
        _jsonish(row.get("settings")),
        crypt_key,
        skipped_paths=skipped_secret_paths,
    )
    active = _truthy(row.get("is_active"))
    currency = _normalize_currency(row.get("currency"))
    overrides: dict[str, Any] = {}
    warnings = [
        (
            f"Skipped encrypted Remnashop {gateway_type} setting '{path}': "
            "APP_CRYPT_KEY is missing or invalid"
        )
        for path in skipped_secret_paths
    ]

    if gateway_type == "TELEGRAM_STARS":
        _add_override(overrides, "STARS_ENABLED", active)
        return _provider_mapping_result(gateway_type, ["stars"], overrides, warnings)

    if gateway_type == "YOOKASSA":
        _add_override(overrides, "YOOKASSA_ENABLED", active)
        _add_override(overrides, "YOOKASSA_SHOP_ID", settings.get("shop_id"))
        _add_override(overrides, "YOOKASSA_SECRET_KEY", settings.get("api_key"))
        _add_override(overrides, "YOOKASSA_DEFAULT_RECEIPT_EMAIL", settings.get("customer"))
        _add_override(overrides, "YOOKASSA_VAT_CODE", settings.get("vat_code"))
        if currency and currency != "RUB":
            warnings.append(
                f"YooKassa supports RUB only in this shop; source currency was {currency}"
            )
        return _provider_mapping_result(gateway_type, ["yookassa"], overrides, warnings)

    if gateway_type == "WATA":
        _add_override(overrides, "WATA_ENABLED", active)
        _add_override(overrides, "WATA_API_TOKEN", settings.get("api_key"))
        return _provider_mapping_result(gateway_type, ["wata"], overrides, warnings)

    if gateway_type == "CRYPTOPAY":
        _add_override(overrides, "CRYPTOPAY_ENABLED", active)
        _add_override(overrides, "CRYPTOPAY_TOKEN", settings.get("api_key"))
        if currency and currency != "RUB":
            warnings.append(
                f"CryptoPay source currency was {currency}; Minishop keeps payment currency "
                "controlled by tariffs/default currency. Configure CRYPTOPAY_ASSET manually "
                "if this instance needs a different default."
            )
        return _provider_mapping_result(gateway_type, ["cryptopay"], overrides, warnings)

    if gateway_type == "HELEKET":
        _add_override(overrides, "HELEKET_ENABLED", active)
        _add_override(overrides, "HELEKET_MERCHANT_ID", settings.get("merchant_id"))
        _add_override(overrides, "HELEKET_API_KEY", settings.get("api_key"))
        if currency and currency != "RUB":
            warnings.append(
                f"Heleket source currency was {currency}; Minishop keeps payment currency "
                "controlled by tariffs/default currency. Configure HELEKET_CURRENCY manually "
                "if this instance needs a different default."
            )
        return _provider_mapping_result(gateway_type, ["heleket"], overrides, warnings)

    if gateway_type == "FREEKASSA":
        _add_override(overrides, "FREEKASSA_ENABLED", active)
        _add_override(overrides, "FREEKASSA_MERCHANT_ID", settings.get("shop_id"))
        _add_override(overrides, "FREEKASSA_API_KEY", settings.get("api_key"))
        _add_override(overrides, "FREEKASSA_SECOND_SECRET", settings.get("secret_word_2"))
        _add_override(overrides, "FREEKASSA_PAYMENT_METHOD_ID", settings.get("payment_system_id"))
        _add_override(overrides, "FREEKASSA_PAYMENT_IP", settings.get("customer_ip"))
        if settings.get("customer_email"):
            warnings.append(
                "FreeKassa customer_email was captured by Remnashop but is not a "
                "Minishop provider setting"
            )
        return _provider_mapping_result(gateway_type, ["freekassa"], overrides, warnings)

    if gateway_type == "PLATEGA":
        _add_override(overrides, "PLATEGA_ENABLED", active)
        _add_override(overrides, "PLATEGA_SBP_ENABLED", active)
        _add_override(overrides, "PLATEGA_MERCHANT_ID", settings.get("merchant_id"))
        _add_override(overrides, "PLATEGA_SECRET", settings.get("api_key"))
        _add_override(overrides, "PLATEGA_PAYMENT_METHOD", settings.get("payment_method"))
        _add_override(overrides, "PLATEGA_SBP_METHOD", settings.get("payment_method"))
        if currency and currency != "RUB":
            warnings.append(
                f"Platega source currency was {currency}; Minishop keeps payment currency "
                "controlled by tariffs/default currency. Configure PLATEGA_SUPPORTED_CURRENCIES "
                "manually if this instance needs a different currency."
            )
        return _provider_mapping_result(gateway_type, ["platega_sbp"], overrides, warnings)

    return _provider_mapping_result(gateway_type, [], overrides, warnings)


def _target_webhook_url(base_url: Optional[str], path: str) -> Optional[str]:
    base = _clean_url(base_url)
    if not base:
        return None
    return f"{base}{path if path.startswith('/') else '/' + path}"


def remnashop_post_migration_actions(
    *,
    target_webhook_base_url: Optional[str],
    imported_provider_ids: Iterable[str],
    source_env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    provider_ids = list(dict.fromkeys(imported_provider_ids))
    payment_actions = []
    seen_paths: set[str] = set()
    for provider_id in provider_ids:
        path = PAYMENT_WEBHOOK_PATHS.get(provider_id)
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        payment_actions.append(
            {
                "provider": provider_id,
                "new_url": _target_webhook_url(target_webhook_base_url, path),
                "where": {
                    "yookassa": "YooKassa merchant cabinet -> HTTP notifications URL",
                    "wata": "WATA merchant dashboard -> webhook/callback URL",
                    "cryptopay": "CryptoBot/Crypto Pay app -> webhook URL",
                    "heleket": "Heleket merchant dashboard -> payment webhook/callback URL",
                    "freekassa": "FreeKassa shop settings -> notification/result URL",
                    "platega": "Platega merchant/project settings -> webhook URL",
                }.get(provider_id, "Payment provider dashboard -> webhook/callback URL"),
            }
        )

    return {
        "webhook_base_url_configured": bool(_clean_url(target_webhook_base_url)),
        "source_urls": remnashop_source_urls_from_env(source_env or {}),
        "remnawave_panel": {
            "new_url": _target_webhook_url(target_webhook_base_url, "/webhook/panel"),
            "where": "Remnawave Panel -> WEBHOOK_URL",
            "secret": (
                "Set the Remnawave webhook secret to the value stored in PANEL_WEBHOOK_SECRET."
            ),
        },
        "payment_providers": payment_actions,
        "telegram": {
            "new_url": _target_webhook_url(target_webhook_base_url, "/tg/webhook"),
            "where": "Telegram webhook is set automatically by Minishop on startup.",
        },
    }


def _listish(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def remnashop_traffic_gb_to_bytes(value: Any) -> Optional[int]:
    number = _to_decimal(value)
    if number is None:
        return None
    return int(number * GIB)


def remnashop_pricing_amount(pricing: Any) -> float:
    data = _jsonish(pricing)
    for key in ("final_amount", "total_amount", "amount", "price"):
        number = _to_decimal(data.get(key))
        if number is not None:
            return float(number)
    return 0.0


def remnashop_pricing_currency(pricing: Any, fallback: Any = None) -> str:
    data = _jsonish(pricing)
    currency = str(data.get("currency") or fallback or "RUB").strip().upper()
    return currency or "RUB"


def remnashop_transaction_status(status: Any, gateway_type: Any = None) -> str:
    source_status = str(status or "").strip().upper()
    provider = str(gateway_type or "").strip().lower()
    if source_status == "COMPLETED":
        return "succeeded"
    if source_status == "PENDING":
        return f"pending_{provider}" if provider else "pending"
    if source_status == "CANCELED":
        return "canceled"
    if source_status == "REFUNDED":
        return "refunded"
    if source_status == "FAILED":
        return "failed"
    return source_status.lower() or "unknown"


def remnashop_sale_mode(purchase_type: Any) -> str:
    source_type = str(purchase_type or "").strip().upper()
    if source_type in {"NEW", "RENEW"}:
        return "subscription"
    if source_type == "CHANGE":
        return "tariff_upgrade"
    return source_type.lower() or "subscription"


def remnashop_months_from_plan_snapshot(
    plan_snapshot: Any,
    *,
    created_at: Any = None,
    expire_at: Any = None,
) -> Optional[int]:
    data = _jsonish(plan_snapshot)
    for key in ("duration_months", "months", "month"):
        months = _to_int(data.get(key))
        if months and months > 0:
            return months

    for key in ("duration_days", "days", "duration"):
        days = _to_int(data.get(key))
        if days and days > 0:
            return max(1, round(days / 30))

    start = _as_utc(created_at)
    end = _as_utc(expire_at)
    if start and end and end > start:
        return max(1, round((end - start).days / 30))
    return None


def remnashop_tariff_key(plan_snapshot: Any, tariff_map: dict[str, str]) -> Optional[str]:
    data = _jsonish(plan_snapshot)
    candidates = [
        data.get("id"),
        data.get("name"),
        data.get("tag"),
        data.get("public_code"),
    ]
    for candidate in candidates:
        key = str(candidate or "").strip()
        if key and key in tariff_map:
            return tariff_map[key]
    return None


def _provider_value(gateway_type: Any) -> str:
    value = str(gateway_type or "remnashop").strip().lower()
    if value == "telegram_stars":
        return "stars"
    return value or "remnashop"


def _extract_panel_subscription_uuid(url: Any, panel_user_uuid: Optional[str]) -> Optional[str]:
    value = str(url or "")
    if not value:
        return None
    panel_user_uuid = str(panel_user_uuid or "").lower()
    for match in UUID_RE.finditer(value):
        candidate = match.group(0).lower()
        if candidate != panel_user_uuid:
            return candidate
    return None


def _legacy_user_metadata(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "points",
        "personal_discount",
        "purchase_discount",
        "role",
        "is_rules_accepted",
        "is_trial_available",
        "language",
        "current_subscription_id",
    )
    return {key: row.get(key) for key in keys if row.get(key) is not None}


def _counter() -> dict[str, int]:
    return defaultdict(int)


class RemnashopImporter:
    def __init__(
        self,
        *,
        source: AsyncConnection,
        target: AsyncSession,
        source_schema: str,
        only: set[str],
        on_conflict: str,
        dry_run: bool,
        created_by_admin_id: int,
        tariff_map: dict[str, str],
        write_admin_compat_overrides: bool,
        source_env: Optional[dict[str, str]] = None,
        source_crypt_key: Optional[str] = None,
        target_webhook_base_url: Optional[str] = None,
    ) -> None:
        self.source = source
        self.target = target
        self.source_schema = _safe_schema_name(source_schema)
        self.only = only
        self.on_conflict = on_conflict
        self.dry_run = dry_run
        self.created_by_admin_id = created_by_admin_id
        self.tariff_map = tariff_map
        self.write_admin_compat_overrides = write_admin_compat_overrides
        self.source_env = source_env or {}
        self.source_crypt_key = source_crypt_key or self.source_env.get("APP_CRYPT_KEY")
        self.target_webhook_base_url = target_webhook_base_url
        self.tables: set[str] = set()
        self.user_map: dict[int, int] = {}
        self.imported_payment_provider_ids: list[str] = []
        self.summary: dict[str, Any] = {
            "source": SOURCE,
            "dry_run": dry_run,
            "on_conflict": on_conflict,
            "users": _counter(),
            "referrals": _counter(),
            "subscriptions": _counter(),
            "payments": _counter(),
            "promocodes": _counter(),
            "payment_provider_settings": _counter(),
            "settings": _counter(),
            "warnings": [],
        }

    async def run(self) -> dict[str, Any]:
        self.tables = await self._source_tables()
        await self._warn_missing_tables()

        if self._should_run("users"):
            await self.import_users()
        if self._should_run("referrals"):
            await self.import_referrals()
        if self._should_run("subscriptions"):
            await self.import_subscriptions()
        if self._should_run("payments"):
            await self.import_payments()
        if self._should_run("promocodes"):
            await self.import_promocodes()
        if self._should_run("settings"):
            await self.import_settings()

        self.summary["post_migration_actions"] = remnashop_post_migration_actions(
            target_webhook_base_url=self.target_webhook_base_url,
            imported_provider_ids=self.imported_payment_provider_ids,
            source_env=self.source_env,
        )

        if self.write_admin_compat_overrides:
            await self._write_admin_overrides()

        return self._plain_summary()

    def _plain_summary(self) -> dict[str, Any]:
        result = dict(self.summary)
        for key, value in list(result.items()):
            if isinstance(value, defaultdict):
                result[key] = dict(value)
        return result

    def _should_run(self, key: str) -> bool:
        return not self.only or key in self.only or "all" in self.only

    async def _source_tables(self) -> set[str]:
        def load_tables(sync_connection: Any) -> set[str]:
            return set(inspect(sync_connection).get_table_names(schema=self.source_schema))

        return await self.source.run_sync(load_tables)

    async def _warn_missing_tables(self) -> None:
        required = {"users", "subscriptions", "transactions", "referrals", "settings"}
        missing = sorted(required - self.tables)
        if missing:
            self.summary["warnings"].append(f"Missing source tables: {', '.join(missing)}")

    async def _fetch_rows(self, table: str, *, order_by: str = "id") -> list[dict[str, Any]]:
        if table not in self.tables:
            return []
        order_sql = f" ORDER BY {order_by}" if order_by else ""
        result = await self.source.execute(
            text(f"SELECT * FROM {_qtable(self.source_schema, table)}{order_sql}")
        )
        return [_as_mapping(row) for row in result.mappings().all()]

    async def _fetch_one(self, table: str) -> Optional[dict[str, Any]]:
        rows = await self._fetch_rows(table, order_by="")
        return rows[0] if rows else None

    async def _latest_panel_uuid_by_telegram(self) -> dict[int, str]:
        if "subscriptions" not in self.tables:
            return {}
        result = await self.source.execute(
            text(
                f"""
                SELECT DISTINCT ON (user_telegram_id)
                    user_telegram_id,
                    user_remna_id
                FROM {_qtable(self.source_schema, "subscriptions")}
                WHERE user_remna_id IS NOT NULL
                ORDER BY user_telegram_id, updated_at DESC NULLS LAST, id DESC
                """
            )
        )
        panel_by_tg: dict[int, str] = {}
        for row in result.mappings().all():
            telegram_id = _to_int(row.get("user_telegram_id"))
            panel_uuid = str(row.get("user_remna_id") or "").strip()
            if telegram_id and panel_uuid:
                panel_by_tg[telegram_id] = panel_uuid
        return panel_by_tg

    async def _target_user_for_telegram(self, telegram_id: Any) -> Optional[User]:
        normalized = _to_int(telegram_id)
        if normalized is None:
            return None
        user = await user_dal.get_user_by_telegram_id(self.target, normalized)
        if not user:
            user = await user_dal.get_user_by_id(self.target, normalized)
        if user:
            self.user_map[normalized] = int(user.user_id)
        return user

    def _can_overwrite(self) -> bool:
        return self.on_conflict == "overwrite"

    def _can_merge_existing(self) -> bool:
        return self.on_conflict in {"merge", "overwrite"}

    def _assign_if_allowed(self, model: Any, attr: str, value: Any) -> bool:
        if value is None:
            return False
        current = getattr(model, attr, None)
        if self._can_overwrite() or current in (None, ""):
            setattr(model, attr, value)
            return True
        return False

    async def _upsert_mapping(
        self,
        *,
        entity_type: str,
        source_id: Any,
        target_table: str,
        target_id: Any,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        source_id_value = str(source_id)
        target_id_value = str(target_id)
        stmt = (
            pg_insert(LegacyImportMapping)
            .values(
                source=SOURCE,
                entity_type=entity_type,
                source_id=source_id_value,
                target_table=target_table,
                target_id=target_id_value,
                metadata_json=_json_dumps(metadata or {}),
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[
                    LegacyImportMapping.source,
                    LegacyImportMapping.entity_type,
                    LegacyImportMapping.source_id,
                ],
                set_={
                    "target_table": target_table,
                    "target_id": target_id_value,
                    "metadata_json": _json_dumps(metadata or {}),
                    "updated_at": now,
                },
            )
        )
        await self.target.execute(stmt)

    async def _get_mapping(self, entity_type: str, source_id: Any) -> Optional[LegacyImportMapping]:
        stmt = select(LegacyImportMapping).where(
            LegacyImportMapping.source == SOURCE,
            LegacyImportMapping.entity_type == entity_type,
            LegacyImportMapping.source_id == str(source_id),
        )
        result = await self.target.execute(stmt)
        return result.scalar_one_or_none()

    async def _upsert_setting_override(self, key: str, value: Any) -> bool:
        from bot.app.web.admin_settings_manifest import coerce_value, get_field_by_key

        field = get_field_by_key(key)
        if field is None:
            self.summary["warnings"].append(f"Skipped unknown admin setting override: {key}")
            return False
        try:
            value = coerce_value(field, value)
        except ValueError as exc:
            self.summary["warnings"].append(f"Skipped invalid admin setting override {key}: {exc}")
            return False

        now = datetime.now(timezone.utc)
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        stmt = (
            pg_insert(AppSettingOverride)
            .values(
                key=key,
                value=encoded,
                updated_at=now,
                updated_by=self.created_by_admin_id or None,
            )
            .on_conflict_do_update(
                index_elements=[AppSettingOverride.key],
                set_={
                    "value": encoded,
                    "updated_at": now,
                    "updated_by": self.created_by_admin_id or None,
                },
            )
        )
        await self.target.execute(stmt)
        return True

    async def _write_setting_overrides(
        self,
        overrides: dict[str, Any],
        *,
        summary_key: str,
    ) -> list[str]:
        written: list[str] = []
        for key, value in overrides.items():
            if await self._upsert_setting_override(key, value):
                written.append(key)
                self.summary[summary_key]["overrides_written"] += 1
            else:
                self.summary[summary_key]["overrides_skipped"] += 1
        return written

    async def import_env_settings(self) -> list[str]:
        if not self.source_env:
            self.summary["settings"]["source_env_missing"] += 1
            return []

        overrides = remnashop_env_overrides(self.source_env)
        if not overrides:
            self.summary["settings"]["source_env_no_supported_values"] += 1
            return []

        written = await self._write_setting_overrides(overrides, summary_key="settings")
        if written:
            self.summary["settings"]["source_env_overrides_written"] += 1
        await self._upsert_mapping(
            entity_type="settings_env",
            source_id="remnashop.env",
            target_table="app_setting_overrides",
            target_id=",".join(written) if written else "none",
            metadata={
                "override_keys": written,
                "source_keys_used": sorted(
                    key
                    for key in (
                        "REMNAWAVE_HOST",
                        "REMNAWAVE_TOKEN",
                        "REMNAWAVE_WEBHOOK_SECRET",
                        "BOT_SUPPORT_USERNAME",
                        "APP_DEFAULT_LOCALE",
                    )
                    if self.source_env.get(key)
                    and not _is_placeholder_setting_value(self.source_env.get(key))
                ),
                "has_app_crypt_key": bool(self.source_env.get("APP_CRYPT_KEY")),
                "source_urls": remnashop_source_urls_from_env(self.source_env),
                "ignored_keys_present": sorted(
                    key for key in ("BOT_MINI_APP",) if self.source_env.get(key)
                ),
            },
        )
        return written

    async def import_payment_provider_settings(self) -> None:
        if "payment_gateways" not in self.tables:
            self.summary["payment_provider_settings"]["missing_source_table"] += 1
            return

        rows = await self._fetch_rows("payment_gateways", order_by="order_index, id")
        if not rows:
            self.summary["payment_provider_settings"]["empty_source_table"] += 1
            return

        active_provider_ids: list[str] = []
        for index, row in enumerate(rows):
            source_id = row.get("id") or row.get("type") or f"row:{index}"
            mapping = remnashop_payment_gateway_overrides(
                row,
                crypt_key=self.source_crypt_key,
            )
            gateway_type = mapping["source_type"]
            self.summary["payment_provider_settings"]["seen"] += 1

            for warning in mapping["warnings"]:
                self.summary["warnings"].append(warning)

            if not mapping["supported"]:
                self.summary["payment_provider_settings"]["unsupported"] += 1
                display_type = gateway_type or str(row.get("type") or "unknown")
                self.summary["warnings"].append(
                    f"Remnashop payment provider {display_type} is not supported by "
                    "Minishop; configure it manually if it is still needed."
                )
                await self._upsert_mapping(
                    entity_type="payment_provider_settings",
                    source_id=source_id,
                    target_table="manual_configuration_required",
                    target_id=display_type,
                    metadata={
                        "source_type": display_type,
                        "active": _truthy(row.get("is_active")),
                        "currency": _normalize_currency(row.get("currency")),
                        "supported": False,
                    },
                )
                continue

            written = await self._write_setting_overrides(
                mapping["overrides"],
                summary_key="payment_provider_settings",
            )
            if written:
                self.summary["payment_provider_settings"]["providers_mapped"] += 1
            else:
                self.summary["payment_provider_settings"]["providers_without_overrides"] += 1

            if _truthy(row.get("is_active")):
                for provider_id in mapping["provider_ids"]:
                    if provider_id and provider_id not in active_provider_ids:
                        active_provider_ids.append(provider_id)
                    if provider_id and provider_id not in self.imported_payment_provider_ids:
                        self.imported_payment_provider_ids.append(provider_id)

            await self._upsert_mapping(
                entity_type="payment_provider_settings",
                source_id=source_id,
                target_table="app_setting_overrides",
                target_id=",".join(written) if written else "none",
                metadata={
                    "source_type": gateway_type,
                    "provider_ids": mapping["provider_ids"],
                    "active": _truthy(row.get("is_active")),
                    "currency": _normalize_currency(row.get("currency")),
                    "override_keys": written,
                    "source_settings_keys": sorted(_jsonish(row.get("settings")).keys()),
                    "warnings_count": len(mapping["warnings"]),
                    "supported": True,
                },
            )

        if active_provider_ids:
            order_value = ",".join(active_provider_ids)
            if await self._upsert_setting_override("PAYMENT_METHODS_ORDER", order_value):
                self.summary["payment_provider_settings"]["payment_order_written"] += 1

    async def _upsert_legacy_referral_code(self, *, code: str, user_id: int) -> None:
        if len(code) > 128:
            self.summary["warnings"].append(
                f"Skipped overlong legacy referral code for user {user_id}: {len(code)} chars"
            )
            return
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(LegacyReferralCode)
            .values(
                source=SOURCE,
                code=code,
                user_id=user_id,
                is_active=True,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[LegacyReferralCode.source, LegacyReferralCode.code],
                set_={"user_id": user_id, "is_active": True, "updated_at": now},
            )
        )
        await self.target.execute(stmt)

    async def _record_user_state_note(
        self,
        *,
        telegram_id: int,
        user_id: int,
        metadata: dict[str, Any],
    ) -> None:
        if not metadata:
            return
        if await self._get_mapping("user_state", telegram_id):
            return
        log = MessageLog(
            user_id=None,
            target_user_id=user_id,
            event_type="legacy_remnashop_user_state",
            content=_json_dumps(metadata),
            is_admin_event=True,
        )
        self.target.add(log)
        await self.target.flush()
        await self._upsert_mapping(
            entity_type="user_state",
            source_id=telegram_id,
            target_table="message_logs",
            target_id=log.log_id,
            metadata=metadata,
        )

    async def _source_referral_code_conflicts(self, code: str, user_id: int) -> bool:
        existing = await user_dal.get_user_by_referral_code(
            self.target,
            code,
            include_legacy=False,
        )
        return bool(existing and int(existing.user_id) != int(user_id))

    async def import_users(self) -> None:
        rows = await self._fetch_rows("users", order_by="telegram_id")
        panel_by_tg = await self._latest_panel_uuid_by_telegram()
        for row in rows:
            telegram_id = _to_int(row.get("telegram_id"))
            if telegram_id is None:
                self.summary["users"]["skipped"] += 1
                continue

            first_name, last_name = _split_name(row.get("name"))
            panel_uuid = panel_by_tg.get(telegram_id)
            referral_code = str(row.get("referral_code") or "").strip() or None
            created_at = _as_utc(row.get("created_at")) or datetime.now(timezone.utc)
            language = str(row.get("language") or "ru").strip().lower()[:8] or "ru"

            existing = await self._target_user_for_telegram(telegram_id)
            if existing and self.on_conflict == "skip":
                target = existing
                self.summary["users"]["skipped"] += 1
            elif existing:
                target = existing
                if self._can_merge_existing():
                    self._assign_if_allowed(target, "username", row.get("username"))
                    self._assign_if_allowed(target, "first_name", first_name)
                    self._assign_if_allowed(target, "last_name", last_name)
                    self._assign_if_allowed(target, "language_code", language)
                    self._assign_if_allowed(target, "panel_user_uuid", panel_uuid)
                    if bool(row.get("is_blocked")):
                        target.is_banned = True
                    elif self._can_overwrite():
                        target.is_banned = False
                    if bool(row.get("is_bot_blocked")):
                        target.telegram_notifications_status = "blocked"
                        target.telegram_notifications_checked_at = datetime.now(timezone.utc)
                        target.telegram_notifications_blocked_at = datetime.now(timezone.utc)
                    if referral_code and len(referral_code) <= 64 and not target.referral_code:
                        if not await self._source_referral_code_conflicts(
                            referral_code,
                            int(target.user_id),
                        ):
                            target.referral_code = referral_code
                    self.summary["users"]["updated"] += 1
            else:
                new_referral_code = None
                if referral_code and len(referral_code) <= 64:
                    conflict = await self._source_referral_code_conflicts(
                        referral_code,
                        telegram_id,
                    )
                    if not conflict:
                        new_referral_code = referral_code

                target, created = await user_dal.create_user(
                    self.target,
                    {
                        "user_id": telegram_id,
                        "telegram_id": telegram_id,
                        "username": row.get("username"),
                        "first_name": first_name,
                        "last_name": last_name,
                        "language_code": language,
                        "registration_date": created_at,
                        "is_banned": bool(row.get("is_blocked")),
                        "panel_user_uuid": panel_uuid,
                        "referral_code": new_referral_code,
                        "telegram_notifications_status": "blocked"
                        if bool(row.get("is_bot_blocked"))
                        else "unknown",
                        "telegram_notifications_checked_at": datetime.now(timezone.utc)
                        if bool(row.get("is_bot_blocked"))
                        else None,
                        "telegram_notifications_blocked_at": datetime.now(timezone.utc)
                        if bool(row.get("is_bot_blocked"))
                        else None,
                    },
                )
                self.summary["users"]["created" if created else "updated"] += 1

            if not target:
                self.summary["users"]["skipped"] += 1
                continue

            self.user_map[telegram_id] = int(target.user_id)
            if referral_code:
                await self._upsert_legacy_referral_code(code=referral_code, user_id=target.user_id)

            metadata = _legacy_user_metadata(row)
            if panel_uuid:
                metadata["panel_user_uuid"] = panel_uuid
            await self._upsert_mapping(
                entity_type="user",
                source_id=telegram_id,
                target_table="users",
                target_id=target.user_id,
                metadata=metadata,
            )
            await self._record_user_state_note(
                telegram_id=telegram_id,
                user_id=int(target.user_id),
                metadata=metadata,
            )

        await self.target.flush()

    async def import_referrals(self) -> None:
        rows = await self._fetch_rows("referrals", order_by="id")
        for row in rows:
            referrer = await self._target_user_for_telegram(row.get("referrer_telegram_id"))
            referred = await self._target_user_for_telegram(row.get("referred_telegram_id"))
            if not referrer or not referred or referrer.user_id == referred.user_id:
                self.summary["referrals"]["skipped"] += 1
                continue
            if referred.referred_by_id and not self._can_overwrite():
                self.summary["referrals"]["skipped"] += 1
                continue
            referred.referred_by_id = int(referrer.user_id)
            self.summary["referrals"]["updated"] += 1
            await self._upsert_mapping(
                entity_type="referral",
                source_id=row.get("id") or f"{referrer.user_id}:{referred.user_id}",
                target_table="users",
                target_id=referred.user_id,
                metadata={
                    "referrer_user_id": referrer.user_id,
                    "referred_user_id": referred.user_id,
                },
            )
        await self.target.flush()

    async def import_subscriptions(self) -> None:
        rows = await self._fetch_rows("subscriptions", order_by="id")
        now = datetime.now(timezone.utc)
        for row in rows:
            user = await self._target_user_for_telegram(row.get("user_telegram_id"))
            if not user:
                self.summary["subscriptions"]["skipped"] += 1
                continue

            panel_user_uuid = str(row.get("user_remna_id") or user.panel_user_uuid or "").strip()
            if not panel_user_uuid:
                self.summary["subscriptions"]["skipped"] += 1
                continue
            if not user.panel_user_uuid or self._can_overwrite():
                user.panel_user_uuid = panel_user_uuid

            source_id = row.get("id")
            mapping = await self._get_mapping("subscription", source_id)
            existing: Optional[Subscription] = None
            if mapping and str(mapping.target_id).isdigit():
                existing = await self.target.get(Subscription, int(mapping.target_id))

            panel_sub_uuid = _extract_panel_subscription_uuid(row.get("url"), panel_user_uuid)
            if not existing and panel_sub_uuid:
                existing = (
                    await self.target.execute(
                        select(Subscription).where(
                            Subscription.panel_subscription_uuid == panel_sub_uuid
                        )
                    )
                ).scalar_one_or_none()

            status = str(row.get("status") or "UNKNOWN").strip().upper()
            expire_at = _as_utc(row.get("expire_at")) or now
            created_at = _as_utc(row.get("created_at")) or now
            plan_snapshot = _jsonish(row.get("plan_snapshot"))
            traffic_limit_bytes = remnashop_traffic_gb_to_bytes(row.get("traffic_limit"))
            payload = {
                "user_id": int(user.user_id),
                "panel_user_uuid": panel_user_uuid,
                "panel_subscription_uuid": panel_sub_uuid,
                "start_date": created_at,
                "end_date": expire_at,
                "duration_months": remnashop_months_from_plan_snapshot(
                    plan_snapshot,
                    created_at=created_at,
                    expire_at=expire_at,
                ),
                "is_active": status in {"ACTIVE", "LIMITED"} and expire_at > now,
                "status_from_panel": status,
                "traffic_limit_bytes": traffic_limit_bytes,
                "provider": "trial" if bool(row.get("is_trial")) else SOURCE,
                "skip_notifications": True,
                "auto_renew_enabled": False,
                "tariff_key": remnashop_tariff_key(plan_snapshot, self.tariff_map),
                "tier_baseline_bytes": traffic_limit_bytes,
                "period_start_at": created_at,
                "hwid_device_limit": _to_int(row.get("device_limit")),
            }
            metadata = {
                "source": SOURCE,
                "source_subscription_id": source_id,
                "traffic_limit_strategy": str(row.get("traffic_limit_strategy") or ""),
                "tag": row.get("tag"),
                "internal_squads": [str(item) for item in _listish(row.get("internal_squads"))],
                "external_squad": str(row.get("external_squad") or "") or None,
                "url": row.get("url"),
                "plan_snapshot": plan_snapshot,
            }

            if existing:
                if self.on_conflict == "skip":
                    self.summary["subscriptions"]["skipped"] += 1
                else:
                    for key, value in payload.items():
                        self._assign_if_allowed(existing, key, value)
                    self.summary["subscriptions"]["updated"] += 1
                target_subscription_id = existing.subscription_id
            else:
                subscription = Subscription(**payload)
                self.target.add(subscription)
                await self.target.flush()
                target_subscription_id = subscription.subscription_id
                self.summary["subscriptions"]["created"] += 1

            await self._upsert_mapping(
                entity_type="subscription",
                source_id=source_id,
                target_table="subscriptions",
                target_id=target_subscription_id,
                metadata=metadata,
            )

        await self.target.flush()

    async def import_payments(self) -> None:
        rows = await self._fetch_rows("transactions", order_by="id")
        for row in rows:
            user = await self._target_user_for_telegram(row.get("user_telegram_id"))
            if not user:
                self.summary["payments"]["skipped"] += 1
                continue

            provider_payment_id = f"{SOURCE}:{row.get('payment_id') or row.get('id')}"
            existing = (
                await self.target.execute(
                    select(Payment).where(Payment.provider_payment_id == provider_payment_id)
                )
            ).scalar_one_or_none()

            provider = _provider_value(row.get("gateway_type"))
            plan_snapshot = _jsonish(row.get("plan_snapshot"))
            created_at = _as_utc(row.get("created_at"))
            payload = {
                "user_id": int(user.user_id),
                "provider_payment_id": provider_payment_id,
                "provider": provider,
                "amount": remnashop_pricing_amount(row.get("pricing")),
                "currency": remnashop_pricing_currency(row.get("pricing"), row.get("currency")),
                "status": remnashop_transaction_status(row.get("status"), provider),
                "description": self._payment_description(row),
                "subscription_duration_months": remnashop_months_from_plan_snapshot(
                    plan_snapshot,
                    created_at=row.get("created_at"),
                    expire_at=None,
                ),
                "sale_mode": remnashop_sale_mode(row.get("purchase_type")),
                "tariff_key": remnashop_tariff_key(plan_snapshot, self.tariff_map),
                "created_at": created_at,
            }
            payload = {key: value for key, value in payload.items() if value is not None}

            if existing:
                if self.on_conflict == "skip":
                    self.summary["payments"]["skipped"] += 1
                else:
                    for key, value in payload.items():
                        self._assign_if_allowed(existing, key, value)
                    self.summary["payments"]["updated"] += 1
                target_payment_id = existing.payment_id
            else:
                payment = Payment(**payload)
                self.target.add(payment)
                await self.target.flush()
                target_payment_id = payment.payment_id
                self.summary["payments"]["created"] += 1

            await self._upsert_mapping(
                entity_type="payment",
                source_id=row.get("payment_id") or row.get("id"),
                target_table="payments",
                target_id=target_payment_id,
                metadata={
                    "source_transaction_id": row.get("id"),
                    "is_test": row.get("is_test"),
                    "purchase_type": str(row.get("purchase_type") or ""),
                    "gateway_type": str(row.get("gateway_type") or ""),
                    "plan_snapshot": plan_snapshot,
                },
            )

        await self.target.flush()

    def _payment_description(self, row: dict[str, Any]) -> str:
        snapshot = _jsonish(row.get("plan_snapshot"))
        plan_name = str(snapshot.get("name") or snapshot.get("tag") or "").strip()
        purchase_type = str(row.get("purchase_type") or "").strip().upper()
        if plan_name:
            return f"Remnashop import: {purchase_type} {plan_name}".strip()
        return f"Remnashop import: {purchase_type}".strip()

    async def import_promocodes(self) -> None:
        if "promocodes" not in self.tables:
            self.summary["promocodes"]["missing_source_table"] += 1
            return

        activation_rows_by_code = await self._source_promocode_activation_rows()
        rows = await self._fetch_rows("promocodes", order_by="id")
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code:
                self.summary["promocodes"]["skipped"] += 1
                continue

            bonus_days = self._promo_bonus_days(row)
            if bonus_days is None or bonus_days <= 0:
                self.summary["promocodes"]["unsupported_reward"] += 1
                continue

            existing = (
                await self.target.execute(select(PromoCode).where(PromoCode.code == code))
            ).scalar_one_or_none()
            activations = activation_rows_by_code.get(code, [])
            valid_until = None
            lifetime_days = _to_int(row.get("lifetime"))
            if lifetime_days and _as_utc(row.get("created_at")):
                valid_until = _as_utc(row.get("created_at"))
                if valid_until:
                    valid_until = valid_until + timedelta(days=lifetime_days)

            payload = {
                "code": code,
                "bonus_days": int(bonus_days),
                "max_activations": _to_int(row.get("max_activations")) or 1_000_000,
                "current_activations": len(activations),
                "is_active": bool(row.get("is_active")),
                "created_by_admin_id": self.created_by_admin_id,
                "created_at": _as_utc(row.get("created_at")),
                "valid_until": valid_until,
            }
            payload = {key: value for key, value in payload.items() if value is not None}

            if existing:
                if self.on_conflict == "skip":
                    self.summary["promocodes"]["skipped"] += 1
                else:
                    for key, value in payload.items():
                        self._assign_if_allowed(existing, key, value)
                    self.summary["promocodes"]["updated"] += 1
                promo = existing
            else:
                promo = PromoCode(**payload)
                self.target.add(promo)
                await self.target.flush()
                self.summary["promocodes"]["created"] += 1

            await self._upsert_mapping(
                entity_type="promocode",
                source_id=row.get("id") or code,
                target_table="promo_codes",
                target_id=promo.promo_code_id,
                metadata={
                    "reward_type": str(row.get("reward_type") or ""),
                    "reward": row.get("reward"),
                    "plan": _jsonish(row.get("plan")),
                    "lifetime": row.get("lifetime"),
                },
            )
            await self._import_promocode_activations(promo, activations)

        await self.target.flush()

    async def _source_promocode_activation_rows(self) -> dict[str, list[dict[str, Any]]]:
        if "promocode_activations" not in self.tables:
            return {}
        result = await self.source.execute(
            text(
                f"""
                SELECT a.*, p.code
                FROM {_qtable(self.source_schema, "promocode_activations")} a
                JOIN {_qtable(self.source_schema, "promocodes")} p
                  ON p.id = a.promocode_id
                ORDER BY a.id
                """
            )
        )
        by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in result.mappings().all():
            mapping = _as_mapping(row)
            code = str(mapping.get("code") or "").strip()
            if code:
                by_code[code].append(mapping)
        return by_code

    def _promo_bonus_days(self, row: dict[str, Any]) -> Optional[int]:
        reward_type = str(row.get("reward_type") or "").strip().upper()
        if reward_type == "DURATION":
            return _to_int(row.get("reward"))
        if reward_type == "SUBSCRIPTION":
            plan = _jsonish(row.get("plan"))
            return (
                _to_int(plan.get("duration_days"))
                or _to_int(plan.get("days"))
                or _to_int(row.get("reward"))
            )
        return None

    async def _import_promocode_activations(
        self,
        promo: PromoCode,
        activations: Iterable[dict[str, Any]],
    ) -> None:
        for activation in activations:
            user = await self._target_user_for_telegram(activation.get("user_telegram_id"))
            if not user:
                self.summary["promocodes"]["activation_skipped"] += 1
                continue
            stmt = (
                pg_insert(PromoCodeActivation)
                .values(
                    promo_code_id=promo.promo_code_id,
                    user_id=user.user_id,
                    activated_at=_as_utc(activation.get("activated_at"))
                    or datetime.now(timezone.utc),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        PromoCodeActivation.promo_code_id,
                        PromoCodeActivation.user_id,
                    ]
                )
            )
            await self.target.execute(stmt)
            self.summary["promocodes"]["activation_imported"] += 1

    async def import_settings(self) -> None:
        source_settings = await self._fetch_one("settings")
        plans = (
            await self._fetch_rows("plans", order_by="order_index")
            if "plans" in self.tables
            else []
        )
        notes = {
            "default_currency": (
                source_settings.get("default_currency") if source_settings else None
            ),
            "settings": {
                key: source_settings.get(key)
                for key in ("access", "requirements", "notifications", "referral", "menu")
                if source_settings and source_settings.get(key) is not None
            },
            "plans_count": len(plans),
            "plans": [
                {
                    "id": plan.get("id"),
                    "name": plan.get("name"),
                    "type": str(plan.get("type") or ""),
                    "traffic_limit": plan.get("traffic_limit"),
                    "device_limit": plan.get("device_limit"),
                    "tag": plan.get("tag"),
                }
                for plan in plans[:100]
            ],
            "source_env": {
                "provided": bool(self.source_env),
                "supported_keys_present": sorted(
                    key
                    for key in (
                        "REMNAWAVE_HOST",
                        "REMNAWAVE_TOKEN",
                        "REMNAWAVE_WEBHOOK_SECRET",
                        "BOT_SUPPORT_USERNAME",
                        "APP_DEFAULT_LOCALE",
                        "APP_DOMAIN",
                        "APP_CRYPT_KEY",
                    )
                    if self.source_env.get(key)
                    and not _is_placeholder_setting_value(self.source_env.get(key))
                ),
                "source_urls": remnashop_source_urls_from_env(self.source_env),
                "ignored_keys_present": sorted(
                    key for key in ("BOT_MINI_APP",) if self.source_env.get(key)
                ),
            },
        }
        env_override_keys = await self.import_env_settings()
        await self.import_payment_provider_settings()
        notes["env_override_keys"] = env_override_keys
        notes["payment_provider_ids"] = list(dict.fromkeys(self.imported_payment_provider_ids))
        await self._upsert_mapping(
            entity_type="settings",
            source_id="singleton",
            target_table="app_setting_overrides",
            target_id="MIGRATION_REMNASHOP_NOTES",
            metadata=notes,
        )
        self.summary["settings"]["captured"] += 1

    async def _write_admin_overrides(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        plain_summary = self._plain_summary()
        await self._upsert_setting_override(
            "MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED",
            True,
        )
        await self._upsert_setting_override(
            "MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED",
            "promocodes" in self.tables,
        )
        await self._upsert_setting_override("MIGRATION_REMNASHOP_IMPORTED_AT", now)
        await self._upsert_setting_override(
            "MIGRATION_REMNASHOP_NOTES",
            _json_dumps(plain_summary),
        )
        self.summary["settings"]["admin_overrides_written"] += 1


def parse_only(value: str) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def parse_tariff_map(value: Optional[str]) -> dict[str, str]:
    if not value:
        return {}
    path = Path(value)
    raw = path.read_text(encoding="utf-8") if path.exists() else value
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("--tariff-map-json must be a JSON object or a path to one")
    return {str(key): str(mapped) for key, mapped in decoded.items()}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import legacy bot data into this shop.")
    parser.add_argument("--source-type", choices=[SOURCE], default=SOURCE)
    parser.add_argument("--source-dsn", required=True)
    parser.add_argument("--source-schema", default="public")
    parser.add_argument(
        "--source-env-file",
        help=(
            "Path to the source Remnashop .env. Used for APP_CRYPT_KEY, Remnawave "
            "API settings and selected safe compatibility values."
        ),
    )
    parser.add_argument(
        "--source-crypt-key",
        help="Explicit Remnashop APP_CRYPT_KEY. Overrides the value from --source-env-file.",
    )
    parser.add_argument("--target-dsn")
    parser.add_argument(
        "--only",
        default="all",
        help=(
            "Comma-separated sections: "
            "all,users,referrals,subscriptions,payments,promocodes,settings"
        ),
    )
    parser.add_argument(
        "--on-conflict",
        choices=["merge", "skip", "overwrite"],
        default="merge",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--created-by-admin-id", type=int, default=0)
    parser.add_argument(
        "--tariff-map-json",
        help="JSON object or path mapping remnashop plan id/name/tag to local tariff_key.",
    )
    parser.add_argument(
        "--no-admin-compat-overrides",
        action="store_true",
        help="Do not enable migration compatibility toggles in admin settings.",
    )
    return parser


async def _prepare_target_schema(engine: Any) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(run_database_migrations)


async def run_import(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings()
    source_env = read_remnashop_env_file(args.source_env_file)
    source_crypt_key = args.source_crypt_key or source_env.get("APP_CRYPT_KEY")
    source_engine = create_async_engine(normalize_async_postgres_dsn(args.source_dsn))
    target_engine = create_async_engine(
        normalize_async_postgres_dsn(args.target_dsn or settings.DATABASE_URL)
    )
    await _prepare_target_schema(target_engine)

    session_factory = async_sessionmaker(
        bind=target_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with source_engine.connect() as source, session_factory() as target:
        importer = RemnashopImporter(
            source=source,
            target=target,
            source_schema=args.source_schema,
            only=parse_only(args.only),
            on_conflict=args.on_conflict,
            dry_run=bool(args.dry_run),
            created_by_admin_id=args.created_by_admin_id,
            tariff_map=parse_tariff_map(args.tariff_map_json),
            write_admin_compat_overrides=not args.no_admin_compat_overrides,
            source_env=source_env,
            source_crypt_key=source_crypt_key,
            target_webhook_base_url=settings.WEBHOOK_BASE_URL,
        )
        summary = await importer.run()
        if args.dry_run:
            await target.rollback()
        else:
            await target.commit()

    await source_engine.dispose()
    await target_engine.dispose()
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_arg_parser().parse_args()
    summary = asyncio.run(run_import(args))
    print(_json_dumps(summary))


if __name__ == "__main__":
    main()
