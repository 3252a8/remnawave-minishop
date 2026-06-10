"""Detect common deployment misconfigurations for the admin panel.

Each check returns :class:`ConfigAlert` items the admin UI renders as
banners on the dashboard and inside the affected sections. Local checks
(filesystem, settings flags) run on every request; network checks
(Telegram webhook, Remnawave panel) are cached for a couple of minutes so
the dashboard stays fast and external APIs are not hammered.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bot.utils.request_security import ip_in_allowlist

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[3]

NETWORK_CHECKS_TTL_SECONDS = 120.0
NETWORK_CHECK_TIMEOUT_SECONDS = 8.0
_WEBHOOK_ERROR_RECENT_SECONDS = 3600
_WEBHOOK_PENDING_THRESHOLD = 50

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# Admin section ids the frontend routes alerts to.
SECTION_SETTINGS = "settings"
SECTION_PAYMENTS = "payments"
SECTION_BACKUPS = "backups"
SECTION_TARIFFS = "tariffs"
SECTION_APPEARANCE = "appearance"
SECTION_TRANSLATIONS = "translations"
SECTION_USERS = "users"

_DATA_DIR_SECTIONS = (
    SECTION_BACKUPS,
    SECTION_TARIFFS,
    SECTION_APPEARANCE,
    SECTION_TRANSLATIONS,
    SECTION_SETTINGS,
)

# Every message key an alert can carry. Tests assert each has
# ``admin_health_<key>`` entries in both locale files.
ALL_MESSAGE_KEYS = (
    "data_dir_missing",
    "data_dir_not_writable",
    "backups_dir_not_writable",
    "tariffs_config_invalid",
    "locale_overrides_invalid",
    "subscription_page_config_invalid",
    "provider_not_configured",
    "provider_webhook_needs_base_url",
    "no_payment_methods",
    "mini_app_url_missing",
    "mini_app_url_not_https",
    "redis_not_configured",
    "smtp_incomplete",
    "proxy_not_trusted",
    "bot_token_invalid",
    "telegram_api_error",
    "telegram_webhook_missing",
    "telegram_webhook_mismatch",
    "telegram_webhook_error",
    "telegram_webhook_pending",
    "panel_api_not_configured",
    "panel_api_unreachable",
)


@dataclass(frozen=True)
class ConfigAlert:
    id: str
    severity: str
    sections: Tuple[str, ...]
    params: Dict[str, Any] = field(default_factory=dict)
    # Locale key suffix; defaults to ``id``. Per-provider alerts carry ids
    # like ``provider_not_configured:wata`` but share one message key.
    message_key: Optional[str] = None

    def as_payload(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "sections": list(self.sections),
            "message_key": self.message_key or self.id,
            "params": dict(self.params),
        }


# ─── Filesystem checks ─────────────────────────────────────────────


def _dir_is_writable(path: Path) -> bool:
    probe = path / f".health-probe-{uuid.uuid4().hex}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        try:
            probe.unlink()
        except OSError:
            pass
        return False


def _resolve_data_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else APP_ROOT / path


def data_dir_alerts(settings: Any, app_root: Path = APP_ROOT) -> List[ConfigAlert]:
    alerts: List[ConfigAlert] = []
    data_dir = app_root / "data"
    if not data_dir.is_dir():
        return [
            ConfigAlert(
                id="data_dir_missing",
                severity=SEVERITY_ERROR,
                sections=_DATA_DIR_SECTIONS,
                params={"path": str(data_dir)},
            )
        ]
    if not _dir_is_writable(data_dir):
        alerts.append(
            ConfigAlert(
                id="data_dir_not_writable",
                severity=SEVERITY_ERROR,
                sections=_DATA_DIR_SECTIONS,
                params={"path": str(data_dir)},
            )
        )

    backup_dir = _resolve_data_path(str(getattr(settings, "BACKUP_DIR", "") or "data/backups"))
    if backup_dir.is_dir() and not _dir_is_writable(backup_dir):
        alerts.append(
            ConfigAlert(
                id="backups_dir_not_writable",
                severity=SEVERITY_WARNING,
                sections=(SECTION_BACKUPS,),
                params={"path": str(backup_dir)},
            )
        )
    return alerts


def config_file_alerts(settings: Any) -> List[ConfigAlert]:
    alerts: List[ConfigAlert] = []

    tariffs_path = _resolve_data_path(
        str(getattr(settings, "TARIFFS_CONFIG_PATH", "") or "data/tariffs.json")
    )
    if tariffs_path.is_file():
        try:
            from config.tariffs_config import load_tariffs_config

            load_tariffs_config(tariffs_path)
        except Exception as exc:
            alerts.append(
                ConfigAlert(
                    id="tariffs_config_invalid",
                    severity=SEVERITY_ERROR,
                    sections=(SECTION_TARIFFS,),
                    params={"path": str(tariffs_path), "error": str(exc)[:300]},
                )
            )

    locale_overrides_path = APP_ROOT / "data" / "locales-overrides.json"
    if locale_overrides_path.is_file():
        try:
            json.loads(locale_overrides_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            alerts.append(
                ConfigAlert(
                    id="locale_overrides_invalid",
                    severity=SEVERITY_WARNING,
                    sections=(SECTION_TRANSLATIONS,),
                    params={"path": str(locale_overrides_path), "error": str(exc)[:300]},
                )
            )

    try:
        from config.subscription_guides_config import (
            SubscriptionGuidesConfigError,
            subscription_guides_admin_config_json,
        )

        try:
            subscription_guides_admin_config_json(settings)
        except SubscriptionGuidesConfigError as exc:
            alerts.append(
                ConfigAlert(
                    id="subscription_page_config_invalid",
                    severity=SEVERITY_WARNING,
                    sections=(SECTION_SETTINGS,),
                    params={"error": str(exc)[:300]},
                )
            )
    except Exception:  # pragma: no cover - defensive import guard
        logger.exception("Subscription guides config check failed unexpectedly")

    return alerts


# ─── Settings checks ───────────────────────────────────────────────


def payment_provider_alerts(settings: Any, app: Any) -> List[ConfigAlert]:
    from bot.payment_providers import iter_provider_specs

    alerts: List[ConfigAlert] = []
    any_enabled = False
    seen_services: set = set()
    for spec in iter_provider_specs():
        try:
            enabled = spec.is_effectively_enabled(settings)
        except Exception:  # pragma: no cover - provider config errors
            logger.exception("Provider %s enabled check failed", spec.id)
            continue
        if not enabled:
            continue
        any_enabled = True
        if spec.service_key in seen_services:
            continue
        if spec.service_key:
            seen_services.add(spec.service_key)
        if not spec.is_service_configured(app):
            alerts.append(
                ConfigAlert(
                    id=f"provider_not_configured:{spec.id}",
                    severity=SEVERITY_ERROR,
                    sections=(SECTION_SETTINGS,),
                    params={"provider": spec.label},
                    message_key="provider_not_configured",
                )
            )
        if spec.webhook_requires_base_url and not getattr(settings, "WEBHOOK_BASE_URL", None):
            alerts.append(
                ConfigAlert(
                    id=f"provider_webhook_needs_base_url:{spec.id}",
                    severity=SEVERITY_ERROR,
                    sections=(SECTION_SETTINGS,),
                    params={"provider": spec.label},
                    message_key="provider_webhook_needs_base_url",
                )
            )
    if not any_enabled:
        alerts.append(
            ConfigAlert(
                id="no_payment_methods",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS, SECTION_PAYMENTS),
            )
        )
    return alerts


def settings_alerts(settings: Any) -> List[ConfigAlert]:
    alerts: List[ConfigAlert] = []

    mini_app_url = str(getattr(settings, "SUBSCRIPTION_MINI_APP_URL", "") or "").strip()
    if not mini_app_url:
        alerts.append(
            ConfigAlert(
                id="mini_app_url_missing",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS,),
            )
        )
    elif not mini_app_url.lower().startswith("https://"):
        alerts.append(
            ConfigAlert(
                id="mini_app_url_not_https",
                severity=SEVERITY_ERROR,
                sections=(SECTION_SETTINGS,),
                params={"url": mini_app_url},
            )
        )

    if not getattr(settings, "REDIS_URL", None):
        alerts.append(
            ConfigAlert(
                id="redis_not_configured",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS,),
            )
        )

    smtp_partial = any(
        getattr(settings, key, None)
        for key in ("SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL")
    )
    if smtp_partial and not getattr(settings, "email_auth_configured", False):
        alerts.append(
            ConfigAlert(
                id="smtp_incomplete",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS,),
            )
        )

    return alerts


def proxy_alerts(request: Any, settings: Any) -> List[ConfigAlert]:
    """Warn when the admin request itself came through an untrusted proxy.

    In that case provider webhooks with IP allowlists will see the proxy
    address instead of the real sender and may reject valid callbacks.
    """
    headers = getattr(request, "headers", None) or {}
    forwarded = headers.get("X-Forwarded-For")
    remote = getattr(request, "remote", None)
    if not forwarded or not remote:
        return []
    if ip_in_allowlist(remote, getattr(settings, "trusted_proxies", None)):
        return []
    return [
        ConfigAlert(
            id="proxy_not_trusted",
            severity=SEVERITY_WARNING,
            sections=(SECTION_SETTINGS,),
            params={"remote": str(remote)},
        )
    ]


# ─── Network checks (cached) ───────────────────────────────────────


async def telegram_alerts(bot: Any, settings: Any) -> List[ConfigAlert]:
    if bot is None:
        return []
    try:
        info = await asyncio.wait_for(bot.get_webhook_info(), timeout=NETWORK_CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        if exc.__class__.__name__ in {"TelegramUnauthorizedError", "TelegramNotFound"}:
            return [
                ConfigAlert(
                    id="bot_token_invalid",
                    severity=SEVERITY_ERROR,
                    sections=(SECTION_SETTINGS,),
                )
            ]
        return [
            ConfigAlert(
                id="telegram_api_error",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS,),
                params={"error": str(exc)[:300]},
            )
        ]

    alerts: List[ConfigAlert] = []
    actual_url = str(getattr(info, "url", "") or "")
    base_url = str(getattr(settings, "WEBHOOK_BASE_URL", "") or "").rstrip("/")
    expected_url = (
        f"{base_url}{getattr(settings, 'telegram_webhook_path', '/tg/webhook')}" if base_url else ""
    )
    if not actual_url:
        alerts.append(
            ConfigAlert(
                id="telegram_webhook_missing",
                severity=SEVERITY_ERROR,
                sections=(SECTION_SETTINGS,),
            )
        )
    elif expected_url and actual_url != expected_url:
        alerts.append(
            ConfigAlert(
                id="telegram_webhook_mismatch",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS,),
                params={"actual": actual_url, "expected": expected_url},
            )
        )

    pending = int(getattr(info, "pending_update_count", 0) or 0)
    last_error_date = getattr(info, "last_error_date", None)
    last_error_ts: Optional[float] = None
    if last_error_date is not None:
        last_error_ts = (
            last_error_date.timestamp()
            if hasattr(last_error_date, "timestamp")
            else float(last_error_date)
        )
    if (
        pending > 0
        and last_error_ts
        and (time.time() - last_error_ts) < _WEBHOOK_ERROR_RECENT_SECONDS
    ):
        alerts.append(
            ConfigAlert(
                id="telegram_webhook_error",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS,),
                params={"error": str(getattr(info, "last_error_message", "") or "")[:300]},
            )
        )

    if pending > _WEBHOOK_PENDING_THRESHOLD:
        alerts.append(
            ConfigAlert(
                id="telegram_webhook_pending",
                severity=SEVERITY_WARNING,
                sections=(SECTION_SETTINGS,),
                params={"count": pending},
            )
        )
    return alerts


async def panel_alerts(panel_service: Any, settings: Any) -> List[ConfigAlert]:
    if not getattr(settings, "PANEL_API_URL", None) or not getattr(settings, "PANEL_API_KEY", None):
        return [
            ConfigAlert(
                id="panel_api_not_configured",
                severity=SEVERITY_ERROR,
                sections=(SECTION_SETTINGS, SECTION_USERS, SECTION_TARIFFS),
            )
        ]
    if panel_service is None:
        return []
    try:
        stats = await asyncio.wait_for(
            panel_service.get_system_stats(), timeout=NETWORK_CHECK_TIMEOUT_SECONDS
        )
    except Exception as exc:
        logger.debug("Panel health check failed: %s", exc)
        stats = None
    if stats is None:
        return [
            ConfigAlert(
                id="panel_api_unreachable",
                severity=SEVERITY_ERROR,
                sections=(SECTION_SETTINGS, SECTION_USERS),
                params={"url": str(getattr(settings, "PANEL_API_URL", "") or "")},
            )
        ]
    return []


# ─── Aggregation ───────────────────────────────────────────────────

_network_cache: Dict[int, Tuple[float, List[ConfigAlert]]] = {}
_network_cache_lock = asyncio.Lock()


def local_alerts(request: Any, settings: Any, app: Any) -> List[ConfigAlert]:
    alerts: List[ConfigAlert] = []
    for collect in (
        lambda: data_dir_alerts(settings),
        lambda: config_file_alerts(settings),
        lambda: payment_provider_alerts(settings, app),
        lambda: settings_alerts(settings),
        lambda: proxy_alerts(request, settings),
    ):
        try:
            alerts.extend(collect())
        except Exception:  # pragma: no cover - one broken check must not hide others
            logger.exception("Config health check failed")
    return alerts


async def network_alerts(app: Any, settings: Any, *, refresh: bool = False) -> List[ConfigAlert]:
    cache_key = id(settings)
    now = time.monotonic()
    if not refresh:
        cached = _network_cache.get(cache_key)
        if cached and (now - cached[0]) < NETWORK_CHECKS_TTL_SECONDS:
            return cached[1]

    async with _network_cache_lock:
        if not refresh:
            cached = _network_cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) < NETWORK_CHECKS_TTL_SECONDS:
                return cached[1]

        results = await asyncio.gather(
            telegram_alerts(app.get("bot"), settings),
            panel_alerts(app.get("panel_service"), settings),
            return_exceptions=True,
        )
        alerts: List[ConfigAlert] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.exception("Network config health check failed", exc_info=result)
                continue
            alerts.extend(result)
        _network_cache[cache_key] = (time.monotonic(), alerts)
        return alerts


async def collect_config_alerts(request: Any, *, refresh: bool = False) -> List[Dict[str, Any]]:
    app = request.app
    settings = app["settings"]
    alerts = local_alerts(request, settings, app)
    alerts.extend(await network_alerts(app, settings, refresh=refresh))
    order = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1}
    alerts.sort(key=lambda alert: (order.get(alert.severity, 2), alert.id))
    return [alert.as_payload() for alert in alerts]
