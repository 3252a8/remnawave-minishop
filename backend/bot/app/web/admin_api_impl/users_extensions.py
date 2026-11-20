"""Build the table contributions from active, trusted plugin declarations."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from bot.plugins.extensions import AdminUserColumn, AdminUserFilter, ExtensionError
from bot.plugins.extensions.registry import get_registry
from bot.plugins.packages import generation_is_current

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsersTableExtensions:
    columns: tuple[tuple[str, AdminUserColumn], ...] = ()
    filters: tuple[tuple[str, AdminUserFilter], ...] = ()

    def predicates(self, selections: list[str]) -> tuple[ColumnElement[bool], ...]:
        selected = {
            key: value
            for key, separator, value in (item.partition("=") for item in selections)
            if separator
        }
        predicates = []
        for key, user_filter in self.filters:
            value = selected.get(key)
            if value is None or not any(option.id == value for option in user_filter.options):
                continue
            try:
                predicate = user_filter.predicate(value)
                if not isinstance(predicate, ColumnElement):
                    raise TypeError("Expected a SQL predicate")
                predicates.append(predicate)
            except Exception as exc:
                logger.warning("Admin user table filter %s is unavailable", key)
                raise ExtensionError("admin_user_extension_filter_unavailable", 503) from exc
        return tuple(predicates)

    async def column_values(
        self, session: AsyncSession, user_ids: tuple[int, ...]
    ) -> dict[int, dict[str, str | None]]:
        result: dict[int, dict[str, str | None]] = {user_id: {} for user_id in user_ids}
        if not result:
            return result
        for key, column in self.columns:
            try:
                async with session.begin_nested(), asyncio.timeout(5):
                    values = await column.resolve(session, user_ids)
                    for user_id, row in result.items():
                        value = values.get(user_id)
                        row[key] = value[:500] if isinstance(value, str) else None
            except Exception:
                logger.warning("Admin user table column %s is unavailable", key)
        return result

    def metadata(self) -> dict[str, Any]:
        return {
            "extension_columns": [{"id": key, "label": item.label} for key, item in self.columns],
            "extension_filters": [
                {
                    "id": key,
                    "label": item.label,
                    "options": [
                        {"value": option.id, "label": option.label} for option in item.options
                    ],
                }
                for key, item in self.filters
            ],
        }


def users_table_extensions() -> UsersTableExtensions:
    if not generation_is_current():
        return UsersTableExtensions()
    columns: list[tuple[str, AdminUserColumn]] = []
    filters: list[tuple[str, AdminUserFilter]] = []
    for owner, entry in get_registry().owners().items():
        columns.extend(
            (f"{owner}:{item.id}", item) for item in entry.contributions.admin_user_columns
        )
        filters.extend(
            (f"{owner}:{item.id}", item) for item in entry.contributions.admin_user_filters
        )
    return UsersTableExtensions(
        tuple(sorted(columns, key=lambda pair: (pair[1].order, pair[0]))),
        tuple(sorted(filters, key=lambda pair: (pair[1].order, pair[0]))),
    )
