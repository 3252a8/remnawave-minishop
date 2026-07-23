from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.services.panel_activity import _panel_user_connection_activity
from db.dal import user_dal
from db.models import Subscription, User

logger = logging.getLogger(__name__)

AUDIENCE_ACTIVE_NEVER_CONNECTED = "active_never_connected"
AUDIENCE_ADMINS = "admins"
AUDIENCE_TARGETS = {
    "all",
    "active",
    "inactive",
    "expired",
    "never",
    AUDIENCE_ACTIVE_NEVER_CONNECTED,
    AUDIENCE_ADMINS,
}
PANEL_ACTIVITY_LOOKUP_CONCURRENCY = 10
_AUDIENCE_TARGET_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


class AudienceNotFoundError(ValueError):
    """Raised when a broadcast target is not registered."""


class AudienceUnavailableError(PermissionError):
    """Raised when a registered audience is temporarily unavailable."""


@dataclass(frozen=True, slots=True)
class AudienceProvider:
    """A plugin-provided broadcast audience and its admin UI metadata."""

    target: str
    label_key: str
    fallback_label: str
    resolve_user_ids: Callable[[], Awaitable[Sequence[int]]]
    count: Callable[[], Awaitable[int | None]] | None = None
    is_available: Callable[[], bool] | None = None
    visible_when_unavailable: bool = False
    group_label_key: str | None = None
    group_fallback_label: str | None = None
    order: int = 100


@dataclass(frozen=True, slots=True)
class AudienceDefinition:
    target: str
    label_key: str
    fallback_label: str
    order: int
    available: bool = True
    group_label_key: str | None = None
    group_fallback_label: str | None = None


class AudienceSegmentationService:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        panel_service: Any = None,
        admin_ids: Sequence[int] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.panel_service = panel_service
        self.admin_ids = [int(admin_id) for admin_id in dict.fromkeys(admin_ids or [])]
        self._providers: dict[str, AudienceProvider] = {}

    def register_provider(self, provider: AudienceProvider) -> None:
        """Register one additional audience for this application process."""

        target = self._normalize_target(provider.target)
        if not _AUDIENCE_TARGET_PATTERN.fullmatch(target):
            raise ValueError(f"Invalid audience target: {provider.target!r}")
        if target in AUDIENCE_TARGETS:
            raise ValueError(f"Audience target is reserved by core: {target!r}")
        if target in self._providers:
            raise ValueError(f"Audience target is already registered: {target!r}")
        label_key = str(provider.label_key or "").strip()
        fallback_label = str(provider.fallback_label or "").strip()
        if not label_key or not fallback_label:
            raise ValueError("Audience label_key and fallback_label must not be empty")
        group_label_key = str(provider.group_label_key or "").strip() or None
        group_fallback_label = str(provider.group_fallback_label or "").strip() or None
        if bool(group_label_key) != bool(group_fallback_label):
            raise ValueError(
                "Audience group_label_key and group_fallback_label must be set together"
            )
        self._providers[target] = AudienceProvider(
            target=target,
            label_key=label_key,
            fallback_label=fallback_label,
            resolve_user_ids=provider.resolve_user_ids,
            count=provider.count,
            is_available=provider.is_available,
            visible_when_unavailable=bool(provider.visible_when_unavailable),
            group_label_key=group_label_key,
            group_fallback_label=group_fallback_label,
            order=int(provider.order),
        )

    def unregister_provider(self, target: str) -> bool:
        """Remove an additional audience registered by the current process."""

        return self._providers.pop(self._normalize_target(target), None) is not None

    def has_target(self, target: str) -> bool:
        normalized = self._normalize_target(target)
        return normalized in AUDIENCE_TARGETS or normalized in self._providers

    def is_target_available(self, target: str) -> bool:
        normalized = self._normalize_target(target)
        if normalized in AUDIENCE_TARGETS:
            return True
        provider = self._providers.get(normalized)
        return provider is not None and self._provider_is_available(provider)

    def audiences(self) -> list[AudienceDefinition]:
        """Return currently available additional audiences for admin discovery."""

        definitions: list[AudienceDefinition] = []
        for provider in sorted(
            self._providers.values(), key=lambda item: (item.order, item.target)
        ):
            available = self._provider_is_available(provider)
            if not available and not provider.visible_when_unavailable:
                continue
            definitions.append(
                AudienceDefinition(
                    target=provider.target,
                    label_key=provider.label_key,
                    fallback_label=provider.fallback_label,
                    order=provider.order,
                    available=available,
                    group_label_key=provider.group_label_key,
                    group_fallback_label=provider.group_fallback_label,
                )
            )
        return definitions

    async def resolve_user_ids(self, target: str) -> list[int]:
        normalized = self._normalize_target(target)
        provider = self._providers.get(normalized)
        if provider is not None:
            if not self._provider_is_available(provider):
                raise AudienceUnavailableError(normalized)
            user_ids = await provider.resolve_user_ids()
            return [int(user_id) for user_id in dict.fromkeys(user_ids)]
        if normalized not in AUDIENCE_TARGETS:
            raise AudienceNotFoundError(normalized)
        if normalized == AUDIENCE_ADMINS:
            return list(self.admin_ids)
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
                AUDIENCE_ADMINS: len(self.admin_ids),
            }
            if self.panel_service is not None:
                counts[AUDIENCE_ACTIVE_NEVER_CONNECTED] = len(
                    await self._user_ids_with_active_subscription_never_connected(session)
                )
        for provider in self._providers.values():
            if not self._provider_is_available(provider):
                continue
            try:
                value = (
                    await provider.count()
                    if provider.count is not None
                    else len(await provider.resolve_user_ids())
                )
                counts[provider.target] = None if value is None else max(0, int(value))
            except Exception:
                logger.exception("Failed to count registered audience target=%s", provider.target)
                counts[provider.target] = None
        return counts

    @staticmethod
    def _normalize_target(target: str) -> str:
        return str(target or "all").strip().lower()

    @staticmethod
    def _provider_is_available(provider: AudienceProvider) -> bool:
        if provider.is_available is None:
            return True
        try:
            return bool(provider.is_available())
        except Exception:
            logger.exception(
                "Failed to evaluate registered audience availability target=%s",
                provider.target,
            )
            return False

    async def _active_subscription_panel_uuids_by_user(
        self,
        session: Any,
    ) -> dict[int, list[tuple[str, datetime | None]]]:
        now = datetime.now(UTC)
        stmt = (
            select(
                Subscription.user_id,
                Subscription.panel_user_uuid,
                Subscription.last_connected_at,
            )
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
        grouped: dict[int, dict[str, datetime | None]] = defaultdict(dict)
        order: dict[int, list[str]] = defaultdict(list)
        for row in result.all():
            user_id, panel_uuid, last_connected_at = (
                (row[0], row[1], row[2]) if len(row) >= 3 else (row[0], row[1], None)
            )
            user_id_int = int(user_id)
            panel_uuid_str = str(panel_uuid or "").strip()
            if not panel_uuid_str:
                continue
            snapshot = last_connected_at if isinstance(last_connected_at, datetime) else None
            if panel_uuid_str not in grouped[user_id_int]:
                grouped[user_id_int][panel_uuid_str] = snapshot
                order[user_id_int].append(panel_uuid_str)
            elif grouped[user_id_int][panel_uuid_str] is None and snapshot is not None:
                grouped[user_id_int][panel_uuid_str] = snapshot
        return {
            user_id: [(panel_uuid, grouped[user_id][panel_uuid]) for panel_uuid in order[user_id]]
            for user_id in order
        }

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
                for entries in panel_uuids_by_user.values()
                for panel_uuid, last_connected_at in entries
                if last_connected_at is None
            )
        )
        statuses_by_uuid = (
            dict(
                zip(
                    panel_uuids,
                    await asyncio.gather(*(lookup(uuid) for uuid in panel_uuids)),
                    strict=True,
                )
            )
            if panel_uuids
            else {}
        )
        user_ids: list[int] = []
        for user_id, entries in panel_uuids_by_user.items():
            statuses = [
                "connected"
                if last_connected_at is not None
                else statuses_by_uuid.get(panel_uuid, "unknown")
                for panel_uuid, last_connected_at in entries
            ]
            if statuses and all(status == "never" for status in statuses):
                user_ids.append(user_id)
        return user_ids
