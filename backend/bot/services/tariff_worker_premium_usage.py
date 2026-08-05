"""Premium traffic accounting against Remnawave node bandwidth stats."""

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from bot.services.panel_api_service import PanelApiService
from db.models import Subscription

logger = logging.getLogger(__name__)


class _PremiumNodesTariff(Protocol):
    premium_squad_uuids: list[str]


class TariffWorkerPremiumUsageMixin:
    panel_service: PanelApiService
    _premium_nodes_cache: dict[tuple[str, ...], dict[str, Any]]
    _premium_node_names: dict[str, str]
    _premium_node_usage_tick_cache: dict[
        tuple[str, str, str],
        dict[str, dict[Any, int]] | None,
    ]

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
        usage_by_node = await self._premium_usage_by_node(
            user_uuid,
            node_uuids,
            start_date,
            end_date,
            panel_username=panel_username,
        )
        return sum(usage_by_node.values())

    async def _premium_usage_by_node(
        self,
        user_uuid: str,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
        *,
        panel_username: str | None = None,
    ) -> dict[str, int]:
        """Premium bytes per node, skipping nodes whose stats request failed."""
        usage: dict[str, int] = {}
        username = (panel_username or "").strip() or None
        for node_uuid in node_uuids:
            lookup = await self._premium_usage_lookup_for_node(node_uuid, start_date, end_date)
            if not lookup:
                continue

            uuid_total = 0
            username_total = 0
            overlap_total = 0
            if user_uuid:
                user_uuid_str = str(user_uuid)
                uuid_total = int(lookup["by_uuid"].get(user_uuid_str, 0) or 0)
            else:
                user_uuid_str = ""
            if username:
                username_total = int(lookup["by_username"].get(username, 0) or 0)
            if user_uuid_str and username:
                overlap_total = int(
                    lookup["by_uuid_username"].get((user_uuid_str, username), 0) or 0
                )

            usage[str(node_uuid)] = uuid_total + username_total - overlap_total
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
        """Never let a failed node stats call lower the usage of the current period.

        A node whose bandwidth stats request failed contributes zero bytes, so a
        panel hiccup would look like "the user spent less" and could hand premium
        access back to a subscription that is over its quota.
        """
        if not same_period:
            return premium_used
        if not any(
            self._premium_node_usage_tick_cache.get((node_uuid, start_date, end_date)) is None
            for node_uuid in node_uuids
        ):
            return premium_used
        stored_used = max(0, int(getattr(sub, "premium_used_bytes", 0) or 0))
        if stored_used <= premium_used:
            return premium_used
        logger.warning(
            "Premium usage for subscription %s kept at %s bytes: node stats are incomplete "
            "(fresh sum was %s bytes)",
            getattr(sub, "subscription_id", None),
            stored_used,
            premium_used,
        )
        return stored_used

    async def _premium_usage_lookup_for_node(
        self,
        node_uuid: str,
        start_date: str,
        end_date: str,
    ) -> dict | None:
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

    @staticmethod
    def _build_premium_usage_lookup(stats: dict | None) -> dict | None:
        if not isinstance(stats, dict):
            return None
        entries = stats.get("topUsers") or stats.get("usersStats") or stats.get("users") or []
        if not isinstance(entries, list):
            return None

        by_uuid: dict[str, int] = {}
        by_username: dict[str, int] = {}
        by_uuid_username: dict[tuple[str, str], int] = {}
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
                by_uuid[uuid_key] = by_uuid.get(uuid_key, 0) + total
            if username_key:
                by_username[username_key] = by_username.get(username_key, 0) + total
            if uuid_key and username_key:
                pair = (uuid_key, username_key)
                by_uuid_username[pair] = by_uuid_username.get(pair, 0) + total
        return {
            "by_uuid": by_uuid,
            "by_username": by_username,
            "by_uuid_username": by_uuid_username,
        }
