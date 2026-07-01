from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_api_impl.common import _panel_user_connection_activity
from db.dal import user_dal
from db.models import Subscription, User

logger = logging.getLogger(__name__)

AUDIENCE_ACTIVE_NEVER_CONNECTED = "active_never_connected"
AUDIENCE_TARGETS = {
    "all",
    "active",
    "inactive",
    "expired",
    "never",
    AUDIENCE_ACTIVE_NEVER_CONNECTED,
}
PANEL_ACTIVITY_LOOKUP_CONCURRENCY = 10


class AudienceSegmentationService:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        panel_service: Any = None,
    ) -> None:
        self.session_factory = session_factory
        self.panel_service = panel_service

    async def resolve_user_ids(self, target: str) -> list[int]:
        normalized = str(target or "all").strip().lower()
        if normalized not in AUDIENCE_TARGETS:
            normalized = "all"
        async with self.session_factory() as session:
            if normalized == AUDIENCE_ACTIVE_NEVER_CONNECTED:
                if self.panel_service is None:
                    return []
                return await self._user_ids_with_active_subscription_never_connected(session)
            if normalized == "active":
                active_ids = await user_dal.get_user_ids_with_active_subscription(session)
                return [int(uid) for uid in active_ids]
            if normalized == "inactive":
                return [
                    int(uid)
                    for uid in await user_dal.get_user_ids_without_active_subscription(session)
                ]
            if normalized == "expired":
                return [
                    int(uid)
                    for uid in await user_dal.get_user_ids_with_expired_subscription(session)
                ]
            if normalized == "never":
                return [
                    int(uid)
                    for uid in await user_dal.get_user_ids_without_any_subscription(session)
                ]
            all_ids = await user_dal.get_all_active_user_ids_for_broadcast(session)
            return [int(uid) for uid in all_ids]

    async def counts(self) -> dict[str, int | None]:
        async with self.session_factory() as session:
            counts: dict[str, int | None] = {
                "all": await user_dal.count_all_active_users_for_broadcast(session),
                "active": await user_dal.count_users_with_active_subscription_for_broadcast(
                    session
                ),
                "inactive": await user_dal.count_users_without_active_subscription_for_broadcast(
                    session
                ),
                "expired": await user_dal.count_users_with_expired_subscription_for_broadcast(
                    session
                ),
                "never": await user_dal.count_users_without_any_subscription_for_broadcast(session),
                AUDIENCE_ACTIVE_NEVER_CONNECTED: None,
            }
            if self.panel_service is not None:
                counts[AUDIENCE_ACTIVE_NEVER_CONNECTED] = len(
                    await self._user_ids_with_active_subscription_never_connected(session)
                )
            return counts

    async def _active_subscription_panel_uuids_by_user(self, session: Any) -> dict[int, list[str]]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(Subscription.user_id, Subscription.panel_user_uuid)
            .join(User, Subscription.user_id == User.user_id)
            .where(
                User.is_banned == False,
                Subscription.is_active == True,
                Subscription.end_date > now,
                Subscription.panel_user_uuid.is_not(None),
                Subscription.panel_user_uuid != "",
            )
            .order_by(Subscription.user_id.asc(), Subscription.end_date.desc())
        )
        result = await session.execute(stmt)
        grouped: dict[int, list[str]] = defaultdict(list)
        seen: dict[int, set[str]] = defaultdict(set)
        for user_id, panel_uuid in result.all():
            user_id_int = int(user_id)
            panel_uuid_str = str(panel_uuid or "").strip()
            if panel_uuid_str and panel_uuid_str not in seen[user_id_int]:
                grouped[user_id_int].append(panel_uuid_str)
                seen[user_id_int].add(panel_uuid_str)
        return dict(grouped)

    async def _panel_connection_status(self, panel_uuid: str) -> str:
        try:
            panel_user = await self.panel_service.get_user_by_uuid(panel_uuid)
        except Exception as exc:
            logger.warning("Failed to fetch panel user activity uuid=%s: %s", panel_uuid, exc)
            return "unknown"
        activity = _panel_user_connection_activity(panel_user)
        return str(activity.get("status") or "unknown")

    async def _user_ids_with_active_subscription_never_connected(
        self,
        session: Any,
    ) -> list[int]:
        panel_uuids_by_user = await self._active_subscription_panel_uuids_by_user(session)
        semaphore = asyncio.Semaphore(PANEL_ACTIVITY_LOOKUP_CONCURRENCY)

        async def lookup(panel_uuid: str) -> str:
            async with semaphore:
                return await self._panel_connection_status(panel_uuid)

        panel_uuids = list(
            dict.fromkeys(
                panel_uuid
                for user_panel_uuids in panel_uuids_by_user.values()
                for panel_uuid in user_panel_uuids
            )
        )
        statuses_by_uuid = dict(
            zip(
                panel_uuids,
                await asyncio.gather(*(lookup(uuid) for uuid in panel_uuids)),
            )
        )
        user_ids: list[int] = []
        for user_id, panel_uuids in panel_uuids_by_user.items():
            statuses = [statuses_by_uuid.get(panel_uuid, "unknown") for panel_uuid in panel_uuids]
            if statuses and all(status == "never" for status in statuses):
                user_ids.append(user_id)
        return user_ids
