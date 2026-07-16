"""Env-derived settings, payment provider settings and admin overrides."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from .common import (
    _json_dumps,
    _jsonish,
    _truthy,
)
from .remnashop_data import (
    remnashop_notification_overrides,
)
from .remnashop_env import (
    _is_placeholder_setting_value,
    _normalize_currency,
    remnashop_env_overrides,
    remnashop_payment_gateway_overrides,
    remnashop_source_urls_from_env,
)
from .remnashop_sales import _RemnashopSalesSection

logger = logging.getLogger(__name__)


class _RemnashopSettingsSection(_RemnashopSalesSection):
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
                        "REMNAWAVE_COOKIE",
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

    async def import_settings(self) -> None:
        source_settings = await self._fetch_one("settings")
        plans = self.source_plans
        if not plans and "plans" in self.tables:
            plans = await self._fetch_rows("plans", order_by="order_index, id")
        notification_import = remnashop_notification_overrides(
            source_settings.get("notifications") if source_settings else None
        )
        notes: dict[str, Any] = {
            "default_currency": (
                source_settings.get("default_currency") if source_settings else None
            ),
            "settings": {
                key: source_settings.get(key)
                for key in ("access", "requirements", "notifications", "referral", "menu")
                if source_settings and source_settings.get(key) is not None
            },
            "plans_count": len(plans),
            "plan_durations_count": len(self.source_plan_durations),
            "plan_prices_count": len(self.source_plan_prices),
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
            "tariff_catalog": {
                "path": self.tariffs_config_path,
                "generated": bool(self.generated_tariff_catalog),
                "tariffs_count": len((self.generated_tariff_catalog or {}).get("tariffs", [])),
                "auto_map_entries": len(self.tariff_map),
            },
            "notification_routes": notification_import,
            "source_env": {
                "provided": bool(self.source_env),
                "supported_keys_present": sorted(
                    key
                    for key in (
                        "REMNAWAVE_HOST",
                        "REMNAWAVE_TOKEN",
                        "REMNAWAVE_COOKIE",
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
        notification_override_keys = await self._write_setting_overrides(
            notification_import.get("overrides") or {},
            summary_key="settings",
        )
        self.summary["settings"]["notification_route"] = notification_import.get("route")
        self.summary["settings"]["notification_overrides"] = (
            notification_import.get("overrides") or {}
        )
        if notification_override_keys:
            self.summary["settings"]["notification_overrides_written"] += 1
        for warning in notification_import.get("warnings") or []:
            self.summary["warnings"].append(warning)
        tariff_catalog_path = await self.write_generated_tariff_catalog()
        await self.import_payment_provider_settings()
        notes["env_override_keys"] = env_override_keys
        notes["notification_override_keys"] = notification_override_keys
        notes["tariff_catalog"]["written_path"] = tariff_catalog_path
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
        now = datetime.now(UTC).isoformat()
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
