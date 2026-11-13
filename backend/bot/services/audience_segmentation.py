from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from bot.services.account_roles import active_admin_user_ids
from bot.services.panel_activity import _panel_user_connection_activity
from bot.services.panel_user_snapshot import load_panel_users_by_reference
from bot.utils.channel_subscription import normalize_required_channel_id
from config.settings import Settings
from db.dal import broadcast_audience_dal, user_dal
from db.models import Subscription, User

logger = logging.getLogger(__name__)

AUDIENCE_ACTIVE_NEVER_CONNECTED = "active_never_connected"
AUDIENCE_ADMINS = "admins"
AUDIENCE_WITHOUT_REQUIRED_CHANNEL = "without_required_channel"
AUDIENCE_TARGETS = {
    "all",
    "active",
    "inactive",
    "expired",
    "never",
    AUDIENCE_ACTIVE_NEVER_CONNECTED,
    AUDIENCE_ADMINS,
    AUDIENCE_WITHOUT_REQUIRED_CHANNEL,
}
PANEL_ACTIVITY_LOOKUP_CONCURRENCY = 10
_AUDIENCE_TARGET_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
# Addresses exactly one existing user, so the message composer can reuse the
# broadcast delivery path (channels, buttons, personalization) for one person.
AUDIENCE_USER_PREFIX = "user:"
_AUDIENCE_USER_PATTERN = re.compile(r"^user:(-?\d{1,19})$")
# Addresses everyone holding an active subscription on one configured tariff.
AUDIENCE_TARIFF_PREFIX = "tariff:"
_AUDIENCE_TARIFF_PATTERN = re.compile(r"^tariff:([a-z0-9_.:-]{1,56})$")


def audience_target_for_tariff(tariff_key: str) -> str:
    return f"{AUDIENCE_TARIFF_PREFIX}{str(tariff_key).strip().lower()}"


def audience_target_tariff_key(target: str) -> str | None:
    """The addressed tariff key, or ``None`` when the target is not a tariff."""

    match = _AUDIENCE_TARIFF_PATTERN.fullmatch(str(target or "").strip().lower())
    return match.group(1) if match else None


def audience_target_for_user(user_id: int) -> str:
    return f"{AUDIENCE_USER_PREFIX}{int(user_id)}"


def audience_target_user_id(target: str) -> int | None:
    """The addressed user id, or ``None`` when the target is not a single user."""

    match = _AUDIENCE_USER_PATTERN.fullmatch(str(target or "").strip().lower())
    return int(match.group(1)) if match else None


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
    # Neutral icon name the admin UI maps to a glyph; unknown names render none.
    icon: str | None = None


@dataclass(frozen=True, slots=True)
class AudienceDefinition:
    target: str
    label_key: str
    fallback_label: str
    order: int
    available: bool = True
    group_label_key: str | None = None
    group_fallback_label: str | None = None
    icon: str | None = None


class AudienceSegmentationService:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        panel_service: Any = None,
        settings: Settings | None = None,
        tariffs: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.panel_service = panel_service
        self.settings = settings
        # ``(key, display name)`` of the tariffs offered as audiences.
        self.tariffs = [
            (str(key).strip().lower(), str(name).strip())
            for key, name in (tariffs or [])
            if str(key).strip()
        ]
        self._providers: dict[str, AudienceProvider] = {}

    def register_provider(self, provider: AudienceProvider) -> None:
        """Register one additional audience for this application process."""

        target = self._normalize_target(provider.target)
        if not _AUDIENCE_TARGET_PATTERN.fullmatch(target):
            raise ValueError(f"Invalid audience target: {provider.target!r}")
        if target in AUDIENCE_TARGETS or target.startswith(
            (AUDIENCE_USER_PREFIX, AUDIENCE_TARIFF_PREFIX)
        ):
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
            icon=str(provider.icon or "").strip() or None,
        )

    def unregister_provider(self, target: str) -> bool:
        """Remove an additional audience registered by the current process."""

        return self._providers.pop(self._normalize_target(target), None) is not None

    def has_target(self, target: str) -> bool:
        normalized = self._normalize_target(target)
        if audience_target_user_id(normalized) is not None:
            return True
        if self._tariff_key(normalized) is not None:
            return True
        return normalized in AUDIENCE_TARGETS or normalized in self._providers

    def is_target_available(self, target: str) -> bool:
        normalized = self._normalize_target(target)
        if audience_target_user_id(normalized) is not None:
            return True
        if self._tariff_key(normalized) is not None:
            return True
        if normalized == AUDIENCE_WITHOUT_REQUIRED_CHANNEL:
            return self.required_channel_id is not None
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
                    icon=provider.icon,
                )
            )
        if self.required_channel_id is not None:
            definitions.append(
                AudienceDefinition(
                    target=AUDIENCE_WITHOUT_REQUIRED_CHANNEL,
                    label_key="broadcast_target_without_required_channel",
                    fallback_label="Not subscribed to the required group or channel",
                    order=70,
                    group_label_key="broadcast_audience_group_telegram",
                    group_fallback_label="Telegram",
                )
            )
        definitions.extend(self._tariff_audiences())
        return definitions

    @property
    def required_channel_id(self) -> int | None:
        return normalize_required_channel_id(
            self.settings.REQUIRED_CHANNEL_ID if self.settings is not None else None
        )

    def _tariff_key(self, target: str) -> str | None:
        """The tariff a target addresses, when that tariff is actually offered."""

        key = audience_target_tariff_key(target)
        if key is None:
            return None
        return key if any(key == offered for offered, _ in self.tariffs) else None

    def _tariff_audiences(self) -> list[AudienceDefinition]:
        return [
            AudienceDefinition(
                target=audience_target_for_tariff(key),
                label_key=f"broadcast_target_tariff_{key.replace('-', '_')}",
                fallback_label=name or key,
                order=700 + index,
                available=True,
                group_label_key="broadcast_audience_group_tariffs",
                group_fallback_label="Specific tariff",
                icon="tag",
            )
            for index, (key, name) in enumerate(self.tariffs)
        ]

    async def resolve_user_ids(self, target: str) -> list[int]:
        normalized = self._normalize_target(target)
        ids = await self._matching_user_ids(normalized)
        if not ids or audience_target_user_id(normalized) is not None:
            return ids
        async with self.session_factory() as session:
            exclusions = await broadcast_audience_dal.excluded_ids_by_target(session, normalized)
        excluded = exclusions.get(normalized, set())
        return [user_id for user_id in ids if user_id not in excluded]

    async def resolve_targets(self, targets: Sequence[str]) -> list[int]:
        normalized = list(dict.fromkeys(target.strip().lower() for target in targets))
        for target in normalized:
            if (
                not target
                or audience_target_user_id(target) is not None
                or not self.has_target(target)
            ):
                raise AudienceNotFoundError(target)
            if not self.is_target_available(target):
                raise AudienceUnavailableError(target)
        users: dict[int, None] = {}
        for target in normalized:
            users.update(dict.fromkeys(await self.resolve_user_ids(target)))
        return list(users)

    async def user_audiences(self, user_id: int) -> list[str]:
        candidates = sorted(AUDIENCE_TARGETS | {audience.target for audience in self.audiences()})
        return [
            target
            for target in candidates
            if self.is_target_available(target)
            and user_id in await self._matching_user_ids(target, user_id=user_id)
        ]

    async def _matching_user_ids(self, normalized: str, *, user_id: int | None = None) -> list[int]:
        single_user_id = audience_target_user_id(normalized)
        if single_user_id is not None:
            async with self.session_factory() as session:
                if await user_dal.get_user_by_id(session, single_user_id) is None:
                    raise AudienceNotFoundError(normalized)
            return [single_user_id]

        filters = {} if user_id is None else {"user_id": user_id}
        tariff_key = self._tariff_key(normalized)
        if tariff_key is not None:
            async with self.session_factory() as session:
                return await user_dal.get_user_ids_with_active_subscription_on_tariff(
                    session, tariff_key, **filters
                )
        provider = self._providers.get(normalized)
        if provider is not None:
            if not self._provider_is_available(provider):
                raise AudienceUnavailableError(normalized)
            user_ids = await provider.resolve_user_ids()
            return [int(uid) for uid in dict.fromkeys(user_ids)]
        if normalized not in AUDIENCE_TARGETS:
            raise AudienceNotFoundError(normalized)
        async with self.session_factory() as session:
            if normalized == AUDIENCE_ADMINS:
                return await active_admin_user_ids(session)
            if normalized == AUDIENCE_WITHOUT_REQUIRED_CHANNEL:
                channel_id = self.required_channel_id
                if channel_id is None:
                    raise AudienceUnavailableError(normalized)
                stmt = broadcast_audience_dal.users_without_required_channel(channel_id)
                if user_id is not None:
                    stmt = stmt.where(User.user_id == user_id)
                return [int(uid) for uid in await session.scalars(stmt)]
            if normalized == AUDIENCE_ACTIVE_NEVER_CONNECTED:
                if self.panel_service is None:
                    return []
                return await self._user_ids_with_active_subscription_never_connected(
                    session, **filters
                )
            loaders = {
                "all": user_dal.get_all_active_user_ids_for_broadcast,
                "active": user_dal.get_user_ids_with_active_subscription,
                "inactive": user_dal.get_user_ids_without_active_subscription,
                "expired": user_dal.get_user_ids_with_expired_subscription,
                "never": user_dal.get_user_ids_without_any_subscription,
            }
            return [int(uid) for uid in await loaders[normalized](session, **filters)]

    async def counts(self) -> dict[str, int | None]:
        async with self.session_factory() as session:
            excluded = await broadcast_audience_dal.excluded_ids_by_target(session)
            admin_ids = await active_admin_user_ids(session)
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
                AUDIENCE_ADMINS: len(set(admin_ids) - excluded.pop(AUDIENCE_ADMINS, set())),
            }
            if self.tariffs:
                per_tariff = await user_dal.count_active_subscriptions_per_tariff(session)
                for key, _name in self.tariffs:
                    counts[audience_target_for_tariff(key)] = int(per_tariff.get(key, 0))
            channel_id = self.required_channel_id
            if channel_id is not None:
                channel_users = broadcast_audience_dal.users_without_required_channel(
                    channel_id, exclude_target=AUDIENCE_WITHOUT_REQUIRED_CHANNEL
                )
                excluded.pop(AUDIENCE_WITHOUT_REQUIRED_CHANNEL, None)
                counts[AUDIENCE_WITHOUT_REQUIRED_CHANNEL] = int(
                    await session.scalar(select(func.count()).select_from(channel_users.subquery()))
                    or 0
                )
            if self.panel_service is not None:
                ids = await self._user_ids_with_active_subscription_never_connected(session)
                counts[AUDIENCE_ACTIVE_NEVER_CONNECTED] = len(
                    set(ids) - excluded.pop(AUDIENCE_ACTIVE_NEVER_CONNECTED, set())
                )
        for target, ids in excluded.items():
            if counts.get(target) is not None:
                matching = await self._matching_user_ids(target)
                counts[target] = len(set(matching) - ids)
        for provider in self._providers.values():
            if not self._provider_is_available(provider):
                continue
            try:
                value = (
                    await provider.count()
                    if provider.count is not None and provider.target not in excluded
                    else len(
                        set(await provider.resolve_user_ids())
                        - excluded.get(provider.target, set())
                    )
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
        *,
        user_id: int | None = None,
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
        if user_id is not None:
            stmt = stmt.where(User.user_id == user_id)
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

    async def _user_ids_with_active_subscription_never_connected(
        self,
        session: Any,
        *,
        user_id: int | None = None,
    ) -> list[int]:
        filters = {} if user_id is None else {"user_id": user_id}
        panel_uuids_by_user = await self._active_subscription_panel_uuids_by_user(
            session, **filters
        )
        panel_uuids = list(
            dict.fromkeys(
                panel_uuid
                for entries in panel_uuids_by_user.values()
                for panel_uuid, last_connected_at in entries
                if last_connected_at is None
            )
        )
        snapshot = await load_panel_users_by_reference(
            self.panel_service,
            panel_uuids,
            threshold=50,
            concurrency=PANEL_ACTIVITY_LOOKUP_CONCURRENCY,
        )
        statuses_by_uuid = {
            panel_uuid: str(_panel_user_connection_activity(panel_user).get("status") or "unknown")
            for panel_uuid, panel_user in snapshot.users_by_reference.items()
        }
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
