"""Remnashop .env parsing, secret decryption and settings overrides."""

from __future__ import annotations

import logging
import re
import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:  # cryptography is already used by the app for payment webhook validation.
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - defensive fallback for minimal tooling.
    Fernet = None  # type: ignore[assignment,misc]

from .common import (
    PAYMENT_WEBHOOK_PATHS,
    PLACEHOLDER_SETTING_VALUES,
    REMNASHOP_ENCRYPTED_PREFIX,
    REMNASHOP_PANEL_WEBHOOK_PATH,
    SUPPORTED_REMNASHOP_PROVIDER_TYPES,
    _jsonish,
    _truthy,
)

logger = logging.getLogger(__name__)


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


def read_remnashop_env_file(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    return parse_remnashop_env_text(Path(path).read_text(encoding="utf-8"))


def _is_placeholder_setting_value(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in PLACEHOLDER_SETTING_VALUES


def _clean_url(value: Any) -> str | None:
    if _is_placeholder_setting_value(value):
        return None
    text_value = str(value or "").strip().rstrip("/")
    return text_value or None


def _remnashop_panel_api_url(value: Any) -> str | None:
    host = _clean_url(value)
    if not host:
        return None
    if "://" not in host:
        host = f"https://{host}" if "." in host else f"http://{host}:3000"
    if not host.rstrip("/").endswith("/api"):
        host = f"{host.rstrip('/')}/api"
    return host


def _source_public_base_from_env(env: dict[str, str]) -> str | None:
    domain = _clean_url(env.get("APP_DOMAIN"))
    if not domain:
        return None
    if "://" not in domain:
        domain = f"https://{domain}"
    return domain


def _support_link_from_username(value: Any) -> str | None:
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
    _add_override(overrides, "PANEL_API_COOKIE", env.get("REMNAWAVE_COOKIE"))
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


def _normalize_currency(value: Any) -> str | None:
    text_value = str(value or "").strip().upper()
    if "." in text_value:
        text_value = text_value.rsplit(".", 1)[-1]
    aliases = {"RUR": "RUB", "STARS": "XTR", "STAR": "XTR"}
    normalized = aliases.get(text_value, text_value)
    return normalized or None


def _is_encrypted_remnashop_value(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(REMNASHOP_ENCRYPTED_PREFIX)


def remnashop_decrypt_value(value: Any, crypt_key: str | None) -> tuple[Any, bool]:
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
    crypt_key: str | None,
    *,
    skipped_paths: list[str] | None = None,
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
    warnings: list[str] | None = None,
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
    crypt_key: str | None = None,
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
            f"Skipped encrypted Remnashop setting {gateway_type} '{path}': "
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
                f"Minishop supports only RUB for YooKassa; the source currency is {currency}."
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
                f"Remnashop specifies the following currency for CryptoPay: {currency}; Minishop "
                "manages payment currency through tariffs/default currency. Configure "
                "CRYPTOPAY_ASSET manually if another default is needed."
            )
        return _provider_mapping_result(gateway_type, ["cryptopay"], overrides, warnings)

    if gateway_type == "HELEKET":
        _add_override(overrides, "HELEKET_ENABLED", active)
        _add_override(overrides, "HELEKET_MERCHANT_ID", settings.get("merchant_id"))
        _add_override(overrides, "HELEKET_API_KEY", settings.get("api_key"))
        if currency and currency != "RUB":
            warnings.append(
                f"Remnashop specifies the following currency for Heleket: {currency}; Minishop "
                "manages payment currency through tariffs/default currency. Configure "
                "HELEKET_CURRENCY manually if another default is needed."
            )
        return _provider_mapping_result(gateway_type, ["heleket"], overrides, warnings)

    if gateway_type == "PAYKILLA":
        _add_override(overrides, "PAYKILLA_ENABLED", active)
        _add_override(
            overrides,
            "PAYKILLA_API_KEY",
            settings.get("api_key") or settings.get("public_key") or settings.get("publicKey"),
        )
        _add_override(
            overrides,
            "PAYKILLA_SECRET_KEY",
            settings.get("secret_key") or settings.get("secretKey"),
        )
        if currency and currency != "RUB":
            warnings.append(
                f"Remnashop specifies the following currency for PayKilla: {currency}; Minishop "
                "manages payment currency through tariffs/default currency. Configure "
                "PAYKILLA_CURRENCY and PAYKILLA_PAYMENT_CURRENCIES manually if another "
                "default is needed."
            )
        return _provider_mapping_result(gateway_type, ["paykilla"], overrides, warnings)

    if gateway_type == "FREEKASSA":
        _add_override(overrides, "FREEKASSA_ENABLED", active)
        _add_override(overrides, "FREEKASSA_MERCHANT_ID", settings.get("shop_id"))
        _add_override(overrides, "FREEKASSA_API_KEY", settings.get("api_key"))
        _add_override(overrides, "FREEKASSA_SECOND_SECRET", settings.get("secret_word_2"))
        _add_override(overrides, "FREEKASSA_PAYMENT_METHOD_ID", settings.get("payment_system_id"))
        _add_override(overrides, "FREEKASSA_PAYMENT_IP", settings.get("customer_ip"))
        if settings.get("customer_email"):
            warnings.append(
                "Remnashop stored FreeKassa customer_email, but Minishop does not expose it "
                "as a payment-provider setting."
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
                f"Remnashop specifies the following currency for Platega: {currency}; Minishop "
                "manages payment currency through tariffs/default currency. Configure "
                "PLATEGA_SUPPORTED_CURRENCIES manually if another currency is needed."
            )
        return _provider_mapping_result(gateway_type, ["platega_sbp"], overrides, warnings)

    return _provider_mapping_result(gateway_type, [], overrides, warnings)


def _target_webhook_url(base_url: str | None, path: str) -> str | None:
    base = _clean_url(base_url)
    if not base:
        return None
    return f"{base}{path if path.startswith('/') else '/' + path}"


def remnashop_post_migration_actions(
    *,
    target_webhook_base_url: str | None,
    imported_provider_ids: Iterable[str],
    source_env: dict[str, str] | None = None,
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
                    "paykilla": "PayKilla Dashboard -> Settings -> Webhooks",
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
