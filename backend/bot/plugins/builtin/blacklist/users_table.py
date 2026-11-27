"""Blacklist icons and filters for the native Minishop users table."""

import json
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import replace

from aiohttp import web
from sqlalchemy import and_, case, or_, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.context import get_session_factory
from bot.middlewares.i18n import JsonI18n
from bot.plugins.extensions import (
    AdminUserColumn,
    AdminUserFilter,
    AdminUserFilterOption,
    ExtensionContributions,
)
from db.models import User

from .alerts import PLUGIN_ID
from .storage_models import Configuration, Entry, Source

_ID = "status"
_EXTENSION_ID = f"{PLUGIN_ID}:{_ID}"
_ICONS = {"match": "⛔️", "clear": "❎", "unknown": "⏳", "unlinked": "❔"}
_TITLE = "admin_minishop_blacklist_status"
_TABLE_VISIBLE: ContextVar[bool] = ContextVar("blacklist_users_table_visible", default=True)
logger = logging.getLogger(__name__)


def _has_match() -> ColumnElement[bool]:
    return (
        select(Entry.telegram_id)
        .where(Entry.telegram_id == User.telegram_id)
        .correlate(User)
        .exists()
    )


def _sources_checked() -> ColumnElement[bool]:
    unchecked = select(Source.id).where(
        or_(Source.last_success_at.is_(None), Source.last_error.is_not(None))
    )
    return and_(select(Source.id).exists(), ~unchecked.exists())


def _unlinked() -> ColumnElement[bool]:
    return or_(User.telegram_id.is_(None), User.telegram_id <= 0)


def _filter_users(option: str) -> ColumnElement[bool]:
    if not _TABLE_VISIBLE.get():
        return true()
    if option == "match":
        return _has_match()
    if option == "unlinked":
        return _unlinked()
    checked = _sources_checked()
    return and_(~_unlinked(), ~_has_match(), checked if option == "clear" else ~checked)


async def _resolve_icons(session: AsyncSession, ids: tuple[int, ...]) -> dict[int, str | None]:
    if not _TABLE_VISIBLE.get():
        return {}
    icon = case(
        (_unlinked(), _ICONS["unlinked"]),
        (_has_match(), _ICONS["match"]),
        (_sources_checked(), _ICONS["clear"]),
        else_=_ICONS["unknown"],
    )
    rows = await session.execute(select(User.user_id, icon).where(User.user_id.in_(ids)))
    return dict(rows.tuples().all())


def _option_labels(i18n: JsonI18n, language: str) -> dict[str, str]:
    return {
        option: i18n.gettext(language, f"admin_minishop_blacklist_users_filter_{option}")
        for option in _ICONS
    }


def add_users_table(
    contributions: ExtensionContributions, i18n: JsonI18n, language: str
) -> ExtensionContributions:
    label = i18n.gettext(language, _TITLE)
    options = tuple(
        AdminUserFilterOption(option, title)
        for option, title in _option_labels(i18n, language).items()
    )
    return replace(
        contributions,
        admin_user_columns=(AdminUserColumn(_ID, label, _resolve_icons),),
        admin_user_filters=(AdminUserFilter(_ID, label, options, _filter_users),),
    )


def _adapt_metadata(
    payload: dict[str, object], i18n: JsonI18n, language: str, visible: bool
) -> None:
    for key in ("extension_columns", "extension_filters"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict) or item.get("id") != _EXTENSION_ID:
                continue
            if not visible:
                del items[index]
            else:
                item["label"] = i18n.gettext(language, _TITLE)
                options = item.get("options")
                if isinstance(options, list):
                    labels = _option_labels(i18n, language)
                    for option in options:
                        value = option.get("value") if isinstance(option, dict) else None
                        if isinstance(value, str) and value in labels:
                            option["label"] = labels[value]
            break


def setup_users_table(app: web.Application, i18n: JsonI18n, default_language: str) -> None:
    @web.middleware
    async def users_table_display(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        if (
            request.method not in ("GET", "HEAD")
            or request.path != "/api/admin/users"
            or not request.get("admin_authorized")
        ):
            return await handler(request)

        actor_id = _require_admin_user_id(request)
        try:
            async with get_session_factory(request)() as session:
                preference = (
                    await session.execute(
                        select(Configuration.users_table_visible, User.language_code)
                        .select_from(Configuration)
                        .outerjoin(User, User.user_id == actor_id)
                        .where(Configuration.id == 1)
                    )
                ).one_or_none()
        except SQLAlchemyError:
            logger.warning("Could not load the blacklist display setting for the users table")
            preference = None
        visible, language = preference if preference is not None else (False, None)

        # Core 3.8.6 registers static descriptors. Use one visibility decision
        # for the predicate, the cells and the metadata of this request.
        token = _TABLE_VISIBLE.set(visible)
        try:
            response = await handler(request)
        finally:
            _TABLE_VISIBLE.reset(token)
        if (
            isinstance(response, web.Response)
            and response.status == 200
            and response.content_type == "application/json"
            and response.text
        ):
            payload: object = json.loads(response.text)
            if isinstance(payload, dict) and payload.get("ok") is True:
                _adapt_metadata(payload, i18n, language or default_language, visible)
                response.text = json.dumps(payload)
        return response

    app.middlewares.append(users_table_display)
