"""Apply Minishop's native user filters and sorting within the blacklist."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_api_impl.users_listing import _admin_tariff_keys
from bot.app.web.admin_api_impl.users_queries import _filter_and_sort_users
from config.settings import Settings
from db.models import User

from .storage_models import Entry


async def query_matched_users(
    session: AsyncSession,
    settings: Settings,
    *,
    limit: int,
    offset: int,
    query: str,
    filter_value: str,
    panel_status: str,
    premium_traffic: str,
    sort: str,
    tariff_filter: str,
    now: datetime,
) -> tuple[list[User], int]:
    criterion = User.telegram_id.in_(select(Entry.telegram_id))
    return await _filter_and_sort_users(
        session,
        page=0,
        page_size=limit,
        offset=offset,
        extension_predicates=(criterion,),
        query=query,
        filter_value=filter_value,
        panel_status=panel_status,
        premium_traffic=premium_traffic,
        sort_value=sort,
        tariff_filter=tariff_filter,
        valid_tariff_keys=_admin_tariff_keys(settings),
        now=now,
    )
