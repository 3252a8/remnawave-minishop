"""Premium traffic accounting against versioned Remnawave bandwidth stats."""

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from bot.services.panel_api_contracts import PanelApiCapability
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_user_snapshot import panel_user_count_hint
from db.models import Subscription

logger = logging.getLogger(__name__)

type UsageLookup = dict[str, dict[Any, int]]
type UsageBatchKey = tuple[tuple[str, ...], str, str]
type VersionedUsageBatchKey = tuple[str, tuple[str, ...], str, str]

PREMIUM_USAGE_CACHE_TTL_SECONDS = 115.0
PREMIUM_USAGE_CROSS_TICK_CACHE_SIZE = 32
PREMIUM_USAGE_TICK_CACHE_SIZE = 128
PREMIUM_USAGE_TOP_USERS_FLOOR = 10_001
PREMIUM_USAGE_TOP_USERS_CEILING = 250_001


@dataclass(frozen=True, slots=True)
class PremiumUsageSnapshot:
    totals: UsageLookup
    by_node: dict[str, UsageLookup] | None
    complete: bool
    source: str


class _PremiumNodesTariff(Protocol):
    premium_squad_uuids: list[str]


class TariffWorkerPremiumUsageMixin:
    panel_service: PanelApiService
    _premium_nodes_cache: dict[tuple[str, ...], dict[str, Any]]
    _premium_node_names: dict[str, str]
    _premium_node_usage_tick_cache: dict[tuple[str, str, str], UsageLookup | None]
    _premium_usage_batch_tick_cache: dict[Any, Any]
    _premium_usage_snapshot_cache: dict[Any, Any]
    _premium_usage_completion_tick: dict[UsageBatchKey, bool]
    _premium_usage_user_limit_hint: int

    def _premium_node_label(self, node_uuid: str) -> str:
        return self._premium_node_names.get(str(node_uuid)) or str(node_uuid)

    async def _premium_node_uuids_for_tariff(self, tariff: _PremiumNodesTariff) -> list[str]:
        cache_key = tuple(sorted(tariff.premium_squad_uuids or []))
        cached = self._premium_nodes_cache.get(cache_key)
        now_ts = datetime.now(UTC).timestamp()
        cached_nodes = cached.get("nodes") if cached else None
        cached_ts = cached.get("ts") if cached else None
        if cached and cached_nodes is not None and now_ts - float(cached_ts or 0) < 600:
            return [str(node) for node in cached_nodes] if isinstance(cached_nodes, list) else []

        nodes: list[str] = []
        for squad_uuid in tariff.premium_squad_uuids or []:
            accessible = (
                await self.panel_service.get_internal_squad_accessible_nodes(squad_uuid) or []
            )
            for node in accessible:
                if not isinstance(node, dict):
                    continue
                node_uuid = node.get("uuid") or node.get("nodeUuid") or node.get("node_uuid")
                if node_uuid:
                    nodes.append(str(node_uuid))
                    node_name = node.get("name") or node.get("nodeName")
                    if node_name:
                        self._premium_node_names[str(node_uuid)] = str(node_name)
        deduped = list(dict.fromkeys(nodes))
        self._premium_nodes_cache[cache_key] = {"ts": now_ts, "nodes": deduped}
        return deduped

    async def _premium_usage_for_user(
        self,
        user_uuid: str,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
        *,
        panel_username: str | None = None,
    ) -> int | None:
        snapshot = await self._premium_usage_snapshot_for_nodes(
            node_uuids,
            start_date,
            end_date,
        )
        if snapshot is None:
            return None
        return self._usage_from_lookup(snapshot.totals, user_uuid, panel_username)

    async def _premium_usage_by_node(
        self,
        user_uuid: str,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
        *,
        panel_username: str | None = None,
    ) -> dict[str, int]:
        """Premium bytes per node; 2.8 falls back here only for leak localization."""
        snapshot = await self._premium_usage_snapshot_for_nodes(
            node_uuids,
            start_date,
            end_date,
        )
        if snapshot is not None and snapshot.by_node is not None:
            return {
                str(node_uuid): self._usage_from_lookup(
                    snapshot.by_node.get(str(node_uuid), self._empty_usage_lookup()),
                    user_uuid,
                    panel_username,
                )
                for node_uuid in node_uuids
            }

        usage: dict[str, int] = {}
        for node_uuid in node_uuids:
            lookup = await self._premium_usage_lookup_for_node(node_uuid, start_date, end_date)
            if lookup is not None:
                usage[str(node_uuid)] = self._usage_from_lookup(
                    lookup,
                    user_uuid,
                    panel_username,
                )
        return usage

    def _premium_usage_with_partial_stats_floor(
        self,
        sub: Subscription,
        premium_used: int,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
        *,
        same_period: bool,
    ) -> int:
        """Never let an incomplete response lower usage in the current period."""
        if not same_period:
            return premium_used
        batch_key = self._usage_batch_key(node_uuids, start_date, end_date)
        complete = self._premium_usage_completion_tick.get(batch_key)
        if complete is not False:
            return premium_used
        stored_used = max(0, int(getattr(sub, "premium_used_bytes", 0) or 0))
        if stored_used <= premium_used:
            return premium_used
        logger.warning(
            "Premium usage for subscription %s kept at %s bytes: panel stats are incomplete "
            "(fresh sum was %s bytes)",
            getattr(sub, "subscription_id", None),
            stored_used,
            premium_used,
        )
        return stored_used

    async def _premium_usage_snapshot_for_nodes(
        self,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
    ) -> PremiumUsageSnapshot | None:
        nodes = tuple(sorted(dict.fromkeys(str(value) for value in node_uuids if str(value))))
        if not nodes:
            return PremiumUsageSnapshot(self._empty_usage_lookup(), {}, True, "empty")
        batch_key = self._usage_batch_key(list(nodes), start_date, end_date)

        # Old test doubles and third-party PanelApiService-compatible adapters
        # continue through the established per-node contract.
        if not hasattr(self.panel_service, "get_multi_node_user_usage"):
            legacy_snapshot = await self._premium_usage_snapshot_from_per_node(
                nodes,
                start_date,
                end_date,
            )
            self._premium_usage_completion_tick[batch_key] = legacy_snapshot.complete
            return legacy_snapshot

        compatibility = await self.panel_service.get_panel_api_compatibility()
        version_key = compatibility.version or compatibility.generation.value
        cache_key = (version_key, nodes, start_date, end_date)
        tick_cached = self._premium_usage_batch_tick_cache.get(cache_key)
        if tick_cached is not None:
            self._premium_usage_completion_tick[batch_key] = tick_cached.complete
            return tick_cached

        now = time.monotonic()
        cross_tick = self._premium_usage_snapshot_cache.get(cache_key)
        if cross_tick is not None and now - cross_tick[0] < PREMIUM_USAGE_CACHE_TTL_SECONDS:
            cached_snapshot = cross_tick[1]
            self._remember_usage_tick_snapshot(cache_key, cached_snapshot)
            self._premium_usage_completion_tick[batch_key] = cached_snapshot.complete
            logger.info(
                "metric premium_usage_snapshot source=cross_tick_cache nodes=%s complete=%s",
                len(nodes),
                cached_snapshot.complete,
            )
            return cached_snapshot

        snapshot: PremiumUsageSnapshot | None = None
        v3_capability = self.panel_service.panel_capability_state(
            PanelApiCapability.MULTI_NODE_USAGE,
            compatibility,
        )
        if v3_capability is not False:
            payload = await self.panel_service.get_multi_node_user_usage(
                list(nodes),
                start=start_date,
                end=end_date,
                min_total_bytes=0,
            )
            snapshot = self._snapshot_from_v3_usage(payload, nodes)

        aggregate_capability = self.panel_service.panel_capability_state(
            PanelApiCapability.MULTI_NODE_TOP_USERS,
            compatibility,
        )
        if snapshot is None and aggregate_capability is not False:
            snapshot = await self._premium_usage_snapshot_from_aggregate(
                nodes,
                start_date,
                end_date,
            )

        if snapshot is None:
            snapshot = await self._premium_usage_snapshot_from_per_node(
                nodes,
                start_date,
                end_date,
            )

        self._remember_usage_tick_snapshot(cache_key, snapshot)
        self._premium_usage_completion_tick[batch_key] = snapshot.complete
        if snapshot.complete and snapshot.source != "per_node":
            self._remember_cross_tick_snapshot(cache_key, now, snapshot)
        logger.info(
            "metric premium_usage_snapshot source=%s nodes=%s complete=%s users=%s",
            snapshot.source,
            len(nodes),
            snapshot.complete,
            max(
                len(snapshot.totals["by_uuid"]),
                len(snapshot.totals["by_username"]),
            ),
        )
        return snapshot

    async def _premium_usage_snapshot_from_aggregate(
        self,
        nodes: tuple[str, ...],
        start_date: str,
        end_date: str,
    ) -> PremiumUsageSnapshot | None:
        panel_hint = await panel_user_count_hint(self.panel_service)
        known_panel_users = max(panel_hint, max(0, int(self._premium_usage_user_limit_hint)))
        limit = max(PREMIUM_USAGE_TOP_USERS_FLOOR, known_panel_users + 1)
        maximum = (
            min(
                PREMIUM_USAGE_TOP_USERS_CEILING,
                max(limit, panel_hint * 2 + 1),
            )
            if panel_hint > 0
            else PREMIUM_USAGE_TOP_USERS_CEILING
        )
        while True:
            payload = await self.panel_service.get_multi_node_users_bandwidth_stats(
                list(nodes),
                start=start_date,
                end=end_date,
                top_users_limit=limit,
            )
            if not isinstance(payload, dict):
                return None
            entries = payload.get("topUsers")
            if not isinstance(entries, list):
                return None
            saturated = len(entries) >= limit
            if not saturated or limit >= maximum:
                return PremiumUsageSnapshot(
                    totals=self._build_premium_usage_lookup(payload) or self._empty_usage_lookup(),
                    by_node=None,
                    complete=not saturated,
                    source="multi_node_top_users",
                )
            limit = min(maximum, max(limit + 1, limit * 2))

    async def _premium_usage_snapshot_from_per_node(
        self,
        nodes: tuple[str, ...],
        start_date: str,
        end_date: str,
    ) -> PremiumUsageSnapshot:
        by_node: dict[str, UsageLookup] = {}
        complete = True
        for node_uuid in nodes:
            lookup = await self._premium_usage_lookup_for_node(
                node_uuid,
                start_date,
                end_date,
            )
            if lookup is None:
                complete = False
                continue
            by_node[node_uuid] = lookup
        return PremiumUsageSnapshot(
            totals=self._merge_usage_lookups(by_node.values()),
            by_node=by_node,
            complete=complete,
            source="per_node",
        )

    async def _premium_usage_lookup_for_node(
        self,
        node_uuid: str,
        start_date: str,
        end_date: str,
    ) -> UsageLookup | None:
        stats_cache_key = (node_uuid, start_date, end_date)
        if stats_cache_key not in self._premium_node_usage_tick_cache:
            stats = await self.panel_service.get_node_users_bandwidth_stats(
                node_uuid,
                start=start_date,
                end=end_date,
            )
            self._premium_node_usage_tick_cache[stats_cache_key] = self._build_premium_usage_lookup(
                stats
            )
        return self._premium_node_usage_tick_cache.get(stats_cache_key)

    @classmethod
    def _snapshot_from_v3_usage(
        cls,
        payload: dict[str, Any] | None,
        requested_nodes: tuple[str, ...],
    ) -> PremiumUsageSnapshot | None:
        if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
            return None
        by_node = {node_uuid: cls._empty_usage_lookup() for node_uuid in requested_nodes}
        for node in payload["nodes"]:
            if not isinstance(node, dict):
                return None
            node_uuid = str(node.get("uuid") or node.get("nodeUuid") or "").strip()
            users = node.get("users")
            if not node_uuid or not isinstance(users, list):
                return None
            lookup = cls._empty_usage_lookup()
            for entry in users:
                if not isinstance(entry, dict):
                    continue
                user_id = entry.get("id") if entry.get("id") is not None else entry.get("userId")
                if user_id is None:
                    continue
                raw_total = (
                    entry.get("totalBytes")
                    if entry.get("totalBytes") is not None
                    else entry.get("total")
                )
                try:
                    total = max(0, int(raw_total or 0))
                except (TypeError, ValueError):
                    continue
                key = str(user_id)
                lookup["by_uuid"][key] = lookup["by_uuid"].get(key, 0) + total
            by_node[node_uuid] = lookup
        return PremiumUsageSnapshot(
            totals=cls._merge_usage_lookups(by_node.values()),
            by_node=by_node,
            complete=True,
            source="multi_node_usage",
        )

    @staticmethod
    def _usage_from_lookup(
        lookup: UsageLookup,
        user_uuid: str,
        panel_username: str | None,
    ) -> int:
        user_key = str(user_uuid or "").strip()
        username = str(panel_username or "").strip()
        uuid_total = int(lookup["by_uuid"].get(user_key, 0) or 0) if user_key else 0
        username_total = int(lookup["by_username"].get(username, 0) or 0) if username else 0
        overlap = (
            int(lookup["by_uuid_username"].get((user_key, username), 0) or 0)
            if user_key and username
            else 0
        )
        return uuid_total + username_total - overlap

    @staticmethod
    def _empty_usage_lookup() -> UsageLookup:
        return {"by_uuid": {}, "by_username": {}, "by_uuid_username": {}}

    @classmethod
    def _merge_usage_lookups(cls, lookups: Any) -> UsageLookup:
        merged = cls._empty_usage_lookup()
        for lookup in lookups:
            for bucket in ("by_uuid", "by_username", "by_uuid_username"):
                for key, value in lookup[bucket].items():
                    merged[bucket][key] = merged[bucket].get(key, 0) + int(value or 0)
        return merged

    @staticmethod
    def _usage_batch_key(
        node_uuids: list[str],
        start_date: str,
        end_date: str,
    ) -> UsageBatchKey:
        return tuple(sorted(dict.fromkeys(node_uuids))), start_date, end_date

    def _remember_usage_tick_snapshot(
        self,
        key: VersionedUsageBatchKey,
        snapshot: PremiumUsageSnapshot,
    ) -> None:
        self._premium_usage_batch_tick_cache[key] = snapshot
        if (
            isinstance(self._premium_usage_batch_tick_cache, OrderedDict)
            and len(self._premium_usage_batch_tick_cache) > PREMIUM_USAGE_TICK_CACHE_SIZE
        ):
            self._premium_usage_batch_tick_cache.popitem(last=False)

    def _remember_cross_tick_snapshot(
        self,
        key: VersionedUsageBatchKey,
        observed_at: float,
        snapshot: PremiumUsageSnapshot,
    ) -> None:
        self._premium_usage_snapshot_cache[key] = (observed_at, snapshot)
        if (
            isinstance(self._premium_usage_snapshot_cache, OrderedDict)
            and len(self._premium_usage_snapshot_cache) > PREMIUM_USAGE_CROSS_TICK_CACHE_SIZE
        ):
            self._premium_usage_snapshot_cache.popitem(last=False)

    @staticmethod
    def _build_premium_usage_lookup(stats: dict[str, Any] | None) -> UsageLookup | None:
        if not isinstance(stats, dict):
            return None
        entries = stats.get("topUsers") or stats.get("usersStats") or stats.get("users") or []
        if not isinstance(entries, list):
            return None

        result = TariffWorkerPremiumUsageMixin._empty_usage_lookup()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            user_obj_raw = entry.get("user")
            user_obj: dict[str, Any] = user_obj_raw if isinstance(user_obj_raw, dict) else {}
            entry_uuid = (
                user_obj.get("uuid")
                or entry.get("userUuid")
                or entry.get("uuid")
                or entry.get("user_uuid")
            )
            entry_username = (
                user_obj.get("username") or entry.get("username") or entry.get("userUsername")
            )
            value = entry.get("total")
            if value is None:
                value = int(entry.get("download", 0) or 0) + int(entry.get("upload", 0) or 0)
            total = int(value or 0)
            uuid_key = str(entry_uuid) if entry_uuid else ""
            username_key = str(entry_username) if entry_username else ""
            if uuid_key:
                result["by_uuid"][uuid_key] = result["by_uuid"].get(uuid_key, 0) + total
            if username_key:
                result["by_username"][username_key] = (
                    result["by_username"].get(username_key, 0) + total
                )
            if uuid_key and username_key:
                pair = (uuid_key, username_key)
                result["by_uuid_username"][pair] = result["by_uuid_username"].get(pair, 0) + total
        return result
