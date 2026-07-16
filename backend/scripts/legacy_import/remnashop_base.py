"""Importer plumbing: source introspection, target lookups, mapping upserts."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from db.dal import user_dal
from db.models import (
    AppSettingOverride,
    LegacyImportMapping,
    User,
)

from .common import (
    SOURCE,
    _as_mapping,
    _counter,
    _json_dumps,
    _qtable,
    _safe_schema_name,
    _to_int,
)
from .remnashop_data import (
    remnashop_row_telegram_id,
)

logger = logging.getLogger(__name__)


class _RemnashopImporterBase:
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
        source_env: dict[str, str] | None = None,
        source_crypt_key: str | None = None,
        target_webhook_base_url: str | None = None,
        tariffs_config_path: str | None = None,
    ) -> None:
        self.source = source
        self.target = target
        self.source_schema = _safe_schema_name(source_schema)
        self.only = only
        self.on_conflict = on_conflict
        self.dry_run = dry_run
        self.created_by_admin_id = created_by_admin_id
        self.tariff_map = dict(tariff_map)
        self.explicit_tariff_map = dict(tariff_map)
        self.write_admin_compat_overrides = write_admin_compat_overrides
        self.source_env = source_env or {}
        self.source_crypt_key = source_crypt_key or self.source_env.get("APP_CRYPT_KEY")
        self.target_webhook_base_url = target_webhook_base_url
        self.tariffs_config_path = tariffs_config_path or "data/tariffs.json"
        self.tables: set[str] = set()
        self.source_columns: dict[str, set[str]] = {}
        self.source_user_telegram_by_id: dict[int, int] | None = None
        self.user_map: dict[int, int] = {}
        self.source_plans: list[dict[str, Any]] = []
        self.source_plan_durations: list[dict[str, Any]] = []
        self.source_plan_prices: list[dict[str, Any]] = []
        self.generated_tariff_catalog: dict[str, Any] | None = None
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
            "tariffs": _counter(),
            "payment_provider_settings": _counter(),
            "settings": _counter(),
            "warnings": [],
        }

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

    async def _source_columns(self, table: str) -> set[str]:
        if table in self.source_columns:
            return self.source_columns[table]
        if table not in self.tables:
            self.source_columns[table] = set()
            return set()

        def load_columns(sync_connection: Any) -> set[str]:
            return {
                str(column.get("name") or "")
                for column in inspect(sync_connection).get_columns(
                    table,
                    schema=self.source_schema,
                )
                if column.get("name")
            }

        columns = await self.source.run_sync(load_columns)
        self.source_columns[table] = columns
        return columns

    async def _warn_missing_tables(self) -> None:
        required = {"users", "subscriptions", "transactions", "referrals", "settings"}
        missing = sorted(required - self.tables)
        if missing:
            self.summary["warnings"].append(f"The source is missing tables: {', '.join(missing)}")

    async def _fetch_rows(self, table: str, *, order_by: str = "id") -> list[dict[str, Any]]:
        if table not in self.tables:
            return []
        order_sql = f" ORDER BY {order_by}" if order_by else ""
        result = await self.source.execute(
            text(f"SELECT * FROM {_qtable(self.source_schema, table)}{order_sql}")
        )
        return [_as_mapping(row) for row in result.mappings().all()]

    async def _fetch_one(self, table: str) -> dict[str, Any] | None:
        rows = await self._fetch_rows(table, order_by="")
        return rows[0] if rows else None

    def _remember_source_user(self, row: dict[str, Any]) -> None:
        source_user_id = _to_int(row.get("id"))
        telegram_id = _to_int(row.get("telegram_id"))
        if source_user_id is None or telegram_id is None:
            return
        if self.source_user_telegram_by_id is None:
            self.source_user_telegram_by_id = {}
        self.source_user_telegram_by_id[source_user_id] = telegram_id

    async def _source_user_telegram_map(self) -> dict[int, int]:
        if self.source_user_telegram_by_id is not None:
            return self.source_user_telegram_by_id
        self.source_user_telegram_by_id = {}
        for row in await self._fetch_rows("users", order_by="id"):
            self._remember_source_user(row)
        return self.source_user_telegram_by_id

    async def _source_row_telegram_id(
        self,
        row: dict[str, Any],
        *,
        user_id_key: str = "user_id",
        telegram_id_key: str = "user_telegram_id",
    ) -> int | None:
        telegram_id = remnashop_row_telegram_id(
            row,
            user_id_key=user_id_key,
            telegram_id_key=telegram_id_key,
        )
        if telegram_id is not None:
            return telegram_id
        return remnashop_row_telegram_id(
            row,
            await self._source_user_telegram_map(),
            user_id_key=user_id_key,
            telegram_id_key=telegram_id_key,
        )

    async def _latest_panel_uuid_by_telegram(self) -> dict[int, str]:
        if "subscriptions" not in self.tables:
            return {}
        subscription_columns = await self._source_columns("subscriptions")
        if "user_telegram_id" in subscription_columns:
            user_join = ""
            telegram_expr = "s.user_telegram_id"
        elif "user_id" in subscription_columns and "users" in self.tables:
            user_columns = await self._source_columns("users")
            if not {"id", "telegram_id"}.issubset(user_columns):
                return {}
            user_join = f"JOIN {_qtable(self.source_schema, 'users')} u ON u.id = s.user_id"
            telegram_expr = "u.telegram_id"
        else:
            return {}

        result = await self.source.execute(
            text(
                f"""
                SELECT DISTINCT ON ({telegram_expr})
                    {telegram_expr} AS user_telegram_id,
                    s.user_remna_id
                FROM {_qtable(self.source_schema, "subscriptions")} s
                {user_join}
                WHERE s.user_remna_id IS NOT NULL
                  AND {telegram_expr} IS NOT NULL
                ORDER BY {telegram_expr}, s.updated_at DESC NULLS LAST, s.id DESC
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

    async def _target_user_for_telegram(self, telegram_id: Any) -> User | None:
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

    def _merge_existing_user_profile(
        self,
        model: Any,
        *,
        username: Any,
        first_name: str | None,
        last_name: str | None,
        language: str | None,
    ) -> None:
        if self._can_overwrite():
            self._assign_if_allowed(model, "username", username)
            self._assign_if_allowed(model, "first_name", first_name)
            self._assign_if_allowed(model, "last_name", last_name)
            self._assign_if_allowed(model, "language_code", language)
            return
        if any((username, first_name, last_name, language)):
            self.summary["users"]["profile_preserved"] += 1

    async def _upsert_mapping(
        self,
        *,
        entity_type: str,
        source_id: Any,
        target_table: str,
        target_id: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
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

    async def _get_mapping(self, entity_type: str, source_id: Any) -> LegacyImportMapping | None:
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
            self.summary["warnings"].append(f"Skipped unknown admin setting: {key}")
            return False
        try:
            value = coerce_value(field, value)
        except ValueError as exc:
            self.summary["warnings"].append(f"Skipped invalid admin setting value {key}: {exc}")
            return False

        now = datetime.now(UTC)
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
