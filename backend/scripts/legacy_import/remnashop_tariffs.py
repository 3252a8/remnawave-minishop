"""Tariff catalog generation from Remnashop plans, durations and prices."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.tariffs_config import TariffsConfig

from .common import (
    _json_dumps,
    _path_exists,
    _path_read_text,
)
from .remnashop_base import _RemnashopImporterBase
from .remnashop_data import (
    remnashop_build_tariff_catalog,
)

logger = logging.getLogger(__name__)


class _RemnashopTariffsSection(_RemnashopImporterBase):
    async def prepare_tariffs(self) -> None:
        if "plans" not in self.tables:
            self.summary["tariffs"]["missing_source_table"] += 1
            return

        self.source_plans = await self._fetch_rows("plans", order_by="order_index, id")
        self.source_plan_durations = (
            await self._fetch_rows("plan_durations", order_by="order_index, id")
            if "plan_durations" in self.tables
            else []
        )
        self.source_plan_prices = (
            await self._fetch_rows("plan_prices", order_by="id")
            if "plan_prices" in self.tables
            else []
        )
        source_settings = await self._fetch_one("settings") if "settings" in self.tables else None
        result = remnashop_build_tariff_catalog(
            self.source_plans,
            self.source_plan_durations,
            self.source_plan_prices,
            default_currency=(
                source_settings.get("default_currency") if source_settings else "RUB"
            ),
        )
        for warning in result.get("warnings") or []:
            self.summary["warnings"].append(warning)
        generated_map = dict(result.get("tariff_map") or {})
        self.tariff_map = {**generated_map, **self.explicit_tariff_map}
        self.generated_tariff_catalog = result.get("catalog")
        if generated_map:
            self.summary["tariffs"]["auto_map_entries"] = len(generated_map)
        if self.generated_tariff_catalog:
            self.summary["tariffs"]["generated"] = len(
                self.generated_tariff_catalog.get("tariffs", [])
            )
        else:
            self.summary["tariffs"]["generation_skipped"] += 1

    def _merged_tariff_catalog(self, existing_catalog: dict[str, Any] | None) -> dict[str, Any]:
        generated: dict[str, Any] = json.loads(_json_dumps(self.generated_tariff_catalog or {}))
        if not existing_catalog or self.on_conflict == "overwrite":
            return generated
        if self.on_conflict == "skip":
            return existing_catalog

        existing_tariffs = [
            item for item in existing_catalog.get("tariffs", []) if isinstance(item, dict)
        ]
        generated_tariffs = [
            item for item in generated.get("tariffs", []) if isinstance(item, dict)
        ]
        generated_by_key = {
            str(item.get("key")): item for item in generated_tariffs if item.get("key")
        }
        merged_tariffs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tariff in existing_tariffs:
            key = str(tariff.get("key") or "")
            if key in generated_by_key:
                merged_tariffs.append(generated_by_key[key])
                seen.add(key)
            else:
                merged_tariffs.append(tariff)
        for tariff in generated_tariffs:
            key = str(tariff.get("key") or "")
            if key and key not in seen:
                merged_tariffs.append(tariff)
                seen.add(key)

        return {
            **existing_catalog,
            "default_tariff": generated.get("default_tariff")
            or existing_catalog.get("default_tariff"),
            "default_currency": generated.get("default_currency")
            or existing_catalog.get("default_currency")
            or "rub",
            "tariffs": merged_tariffs,
        }

    async def write_generated_tariff_catalog(self) -> str | None:
        if not self.generated_tariff_catalog:
            return None

        catalog_path = Path(self.tariffs_config_path)
        existing_catalog: dict[str, Any] | None = None
        if await _path_exists(catalog_path):
            try:
                decoded = json.loads(await _path_read_text(catalog_path, encoding="utf-8"))
                if isinstance(decoded, dict):
                    existing_catalog = decoded
            except (OSError, json.JSONDecodeError) as exc:
                if self.on_conflict == "skip":
                    self.summary["warnings"].append(
                        f"Skipped tariff catalog write: {catalog_path} already exists "
                        f"and is unreadable: {exc}"
                    )
                    self.summary["tariffs"]["catalog_write_skipped"] += 1
                    return None
                self.summary["warnings"].append(
                    f"Overwriting unreadable tariff catalog {catalog_path}: {exc}"
                )

        if await _path_exists(catalog_path) and self.on_conflict == "skip":
            self.summary["tariffs"]["catalog_write_skipped"] += 1
            self.summary["warnings"].append(
                f"Skipped tariff catalog write: {catalog_path} already exists."
            )
            return None

        catalog = self._merged_tariff_catalog(existing_catalog)
        try:
            TariffsConfig.model_validate(catalog)
        except Exception as exc:
            self.summary["warnings"].append(f"Skipped invalid merged tariff catalog: {exc}")
            self.summary["tariffs"]["catalog_write_skipped"] += 1
            return None

        self.summary["tariffs"]["catalog_path"] = str(catalog_path)
        if self.dry_run:
            self.summary["tariffs"]["catalog_would_write"] += 1
            return str(catalog_path)

        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = catalog_path.with_suffix(catalog_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(catalog_path)
        self.summary["tariffs"]["catalog_written"] += 1
        self.summary["tariffs"]["catalog_tariffs"] = len(catalog.get("tariffs", []))
        return str(catalog_path)
