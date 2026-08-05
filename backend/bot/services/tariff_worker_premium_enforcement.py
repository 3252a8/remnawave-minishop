"""Make a premium squad limit bite on nodes that are already serving the user.

Dropping the premium squads only stops *new* connections. Remnawave tears the
live ones down as part of the user removal, but only when the node container has
CAP_NET_ADMIN; without it a client keeps streaming through the session it
already holds. So the worker asks the panel to drop the connections explicitly,
and when premium traffic still grows after the limit it records the offending
nodes for the admin health panel.
"""

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from bot.infra.redis import cache_get_json, cache_set_json, redis_key
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from db.models import Subscription

logger = logging.getLogger(__name__)

PREMIUM_LEAK_CACHE_PARTS = ("premium-enforcement", "leaking-nodes")
PREMIUM_LEAK_CACHE_TTL_SECONDS = 24 * 60 * 60
# Ignore sub-megabyte deltas: they are accounting noise, not a live session.
PREMIUM_LEAK_MIN_BYTES = 1024 * 1024


class TariffWorkerPremiumEnforcementMixin:
    settings: Settings
    panel_service: PanelApiService
    _premium_leak_usage: dict[int, dict[str, int]]
    _premium_drop_connections_at: dict[int, float]

    if TYPE_CHECKING:

        async def _premium_usage_by_node(
            self,
            user_uuid: str,
            node_uuids: list[str],
            start_date: str,
            end_date: str,
            *,
            panel_username: str | None = None,
        ) -> dict[str, int]: ...
        def _premium_node_label(self, node_uuid: str) -> str: ...

    async def _sync_premium_connection_state(
        self,
        sub: Subscription,
        *,
        should_limit: bool,
        newly_limited: bool,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
        panel_username: str | None,
    ) -> None:
        if not should_limit:
            self.forget_premium_leak_watch(sub)
            return
        await self._enforce_premium_disconnect(
            sub,
            node_uuids=node_uuids,
            start_date=start_date,
            end_date=end_date,
            panel_username=panel_username,
            newly_limited=newly_limited,
        )

    async def _enforce_premium_disconnect(
        self,
        sub: Subscription,
        *,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
        panel_username: str | None,
        newly_limited: bool,
    ) -> None:
        subscription_id = int(getattr(sub, "subscription_id", 0) or 0)
        if not node_uuids or subscription_id <= 0:
            return
        if not bool(getattr(self.settings, "TARIFF_PREMIUM_DROP_CONNECTIONS", True)):
            self._premium_leak_usage.pop(subscription_id, None)
            return

        usage_by_node = await self._premium_usage_by_node(
            str(getattr(sub, "panel_user_uuid", "") or ""),
            node_uuids,
            start_date,
            end_date,
            panel_username=panel_username,
        )
        leaking_nodes = self._premium_leak_nodes(subscription_id, usage_by_node)
        self._premium_leak_usage[subscription_id] = dict(usage_by_node)

        if newly_limited:
            targets = list(node_uuids)
            reason = "premium_access_limited"
        elif leaking_nodes:
            targets = leaking_nodes
            reason = "premium_usage_after_limit"
            logger.warning(
                "Premium traffic keeps growing for subscription %s after the limit on node(s) %s; "
                "check that these Remnawave nodes run with CAP_NET_ADMIN",
                subscription_id,
                ", ".join(self._premium_node_label(node) for node in leaking_nodes),
            )
            await self._record_premium_leak(leaking_nodes, subscription_id)
        else:
            return

        if not self._premium_drop_cooldown_passed(subscription_id):
            return
        self._premium_drop_connections_at[subscription_id] = time.monotonic()
        logger.info(
            "Dropping premium connections for subscription %s: reason=%s nodes=%s",
            subscription_id,
            reason,
            len(targets),
        )
        await self.panel_service.drop_user_connections(
            str(getattr(sub, "panel_user_uuid", "") or ""),
            targets,
        )

    def forget_premium_leak_watch(self, sub: Subscription) -> None:
        """Drop the per-node baseline once the subscription is not limited anymore."""
        subscription_id = int(getattr(sub, "subscription_id", 0) or 0)
        if subscription_id > 0:
            self._premium_leak_usage.pop(subscription_id, None)
            self._premium_drop_connections_at.pop(subscription_id, None)

    def _premium_leak_nodes(
        self,
        subscription_id: int,
        usage_by_node: dict[str, int],
    ) -> list[str]:
        previous = self._premium_leak_usage.get(subscription_id)
        if not previous:
            # First observation while limited is only a baseline.
            return []
        leaking: list[str] = []
        for node_uuid, used in usage_by_node.items():
            before = int(previous.get(node_uuid, 0) or 0)
            if int(used) - before >= PREMIUM_LEAK_MIN_BYTES:
                leaking.append(node_uuid)
        return leaking

    def _premium_drop_cooldown_passed(self, subscription_id: int) -> bool:
        cooldown = int(
            getattr(self.settings, "TARIFF_PREMIUM_DROP_CONNECTIONS_COOLDOWN_SECONDS", 0) or 0
        )
        if cooldown <= 0:
            return True
        dropped_at = self._premium_drop_connections_at.get(subscription_id)
        if dropped_at is None:
            return True
        return (time.monotonic() - float(dropped_at)) >= cooldown

    async def _record_premium_leak(self, node_uuids: list[str], subscription_id: int) -> None:
        """Persist the offending nodes so the admin health panel can surface them."""
        if not getattr(self.settings, "REDIS_URL", None):
            # Without Redis the warning above stays the only channel.
            return
        key = redis_key(self.settings, *PREMIUM_LEAK_CACHE_PARTS)
        stored = await cache_get_json(self.settings, key)
        record: dict[str, Any] = stored if isinstance(stored, dict) else {}
        now_iso = datetime.now(UTC).isoformat()
        for node_uuid in node_uuids:
            entry = record.get(node_uuid)
            subscriptions = entry.get("subscriptions", []) if isinstance(entry, dict) else []
            if subscription_id not in subscriptions:
                subscriptions = [*subscriptions, subscription_id][-20:]
            record[node_uuid] = {
                "name": self._premium_node_label(node_uuid),
                "last_seen_at": now_iso,
                "subscriptions": subscriptions,
            }
        await cache_set_json(self.settings, key, record, PREMIUM_LEAK_CACHE_TTL_SECONDS)
