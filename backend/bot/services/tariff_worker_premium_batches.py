"""Two-phase premium access writes and grouped connection teardown."""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_contracts import PanelApiCapability
from bot.services.panel_api_service import PanelApiService
from db.models import Subscription

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PremiumSquadMutationPlan:
    sub: Subscription
    tariff: Any
    desired_squads: tuple[str, ...]
    effective_payload: dict[str, Any]
    squad_match_cache_key: tuple[str, tuple[str, ...]]
    should_limit: bool
    newly_limited: bool
    node_uuids: list[str]
    start_date: str
    end_date: str
    panel_username: str | None
    send_reset_notice: bool
    premium_used: int
    premium_limit: int
    premium_period_start: datetime
    previous_period_start: datetime | None
    traffic_strategy: str


@dataclass(frozen=True, slots=True)
class PremiumConnectionDropPlan:
    subscription_id: int
    panel_user_reference: str
    node_uuids: tuple[str, ...]


class TariffWorkerPremiumBatchMixin:
    panel_service: PanelApiService
    _premium_batching_active: bool
    _premium_squad_mutations: list[PremiumSquadMutationPlan]
    _premium_connection_drops: list[PremiumConnectionDropPlan]
    _premium_drop_connections_at: dict[int, float]

    if TYPE_CHECKING:

        def _remember_premium_squad_match(
            self,
            cache_key: tuple[str, tuple[str, ...]],
        ) -> None: ...
        async def _maybe_send_premium_reset_notice(
            self,
            session: AsyncSession,
            sub: Subscription,
            tariff: Any,
            *,
            used: int,
            limit: int,
            period_start_at: datetime,
            previous_period_start: datetime | None,
            traffic_strategy: str,
        ) -> None: ...
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
        ) -> None: ...

    def _begin_premium_panel_batch(self) -> None:
        self._premium_squad_mutations.clear()
        self._premium_connection_drops.clear()
        self._premium_batching_active = True

    async def _finish_premium_panel_batch(self, session: AsyncSession) -> None:
        try:
            await self._flush_premium_squad_mutations(session)
            await self._flush_premium_connection_drops()
        finally:
            self._premium_batching_active = False
            self._premium_squad_mutations.clear()
            self._premium_connection_drops.clear()

    def _queue_premium_squad_mutation(self, plan: PremiumSquadMutationPlan) -> bool:
        if not self._premium_batching_active:
            return False
        self._premium_squad_mutations.append(plan)
        return True

    def _queue_premium_connection_drop(self, plan: PremiumConnectionDropPlan) -> bool:
        if not self._premium_batching_active:
            return False
        self._premium_connection_drops = [
            existing
            for existing in self._premium_connection_drops
            if existing.subscription_id != plan.subscription_id
        ]
        self._premium_connection_drops.append(plan)
        return True

    async def _flush_premium_squad_mutations(self, session: AsyncSession) -> None:
        grouped: dict[tuple[str, ...], list[PremiumSquadMutationPlan]] = defaultdict(list)
        for plan in self._premium_squad_mutations:
            grouped[plan.desired_squads].append(plan)
        for desired_squads, plans in grouped.items():
            references = [str(plan.sub.panel_user_uuid) for plan in plans]
            # Remnawave 3.0.0 returns A088/500 when bulk/update-squads is asked
            # to clear the final squad. Avoid the ambiguous failed mutation and
            # use the exact per-user PATCH contract for this state on both
            # generations. Non-empty states keep the efficient bulk route.
            if not desired_squads:
                successful = await self._fallback_premium_squad_patches(plans)
                for plan in successful:
                    await self._complete_premium_squad_mutation(session, plan)
                continue
            bulk_ok = await self.panel_service.update_users_internal_squads_exact(
                references,
                list(desired_squads),
            )
            successful = plans
            if not bulk_ok:
                compatibility = await self.panel_service.get_panel_api_compatibility()
                capability_state = self.panel_service.panel_capability_state(
                    PanelApiCapability.BULK_SQUAD_UPDATE,
                    compatibility,
                )
                # Only replay through per-user PATCH when the panel conclusively
                # reports that the bulk route does not exist. A timeout or 5xx
                # leaves the POST outcome ambiguous; replaying it immediately can
                # race a still-running bulk mutation and reorder exact squad state.
                successful = (
                    await self._fallback_premium_squad_patches(plans)
                    if capability_state is False
                    else []
                )
            for plan in successful:
                await self._complete_premium_squad_mutation(session, plan)
        if self._premium_squad_mutations:
            logger.info(
                "metric premium_squad_write_batch users=%s desired_states=%s",
                len(self._premium_squad_mutations),
                len(grouped),
            )

    async def _fallback_premium_squad_patches(
        self,
        plans: list[PremiumSquadMutationPlan],
    ) -> list[PremiumSquadMutationPlan]:
        semaphore = asyncio.Semaphore(10)

        async def patch(plan: PremiumSquadMutationPlan) -> PremiumSquadMutationPlan | None:
            async with semaphore:
                updated = await self.panel_service.update_user_details_on_panel(
                    str(plan.sub.panel_user_uuid),
                    plan.effective_payload,
                    log_response=False,
                )
            return plan if updated and not updated.get("error") else None

        results = await asyncio.gather(*(patch(plan) for plan in plans))
        return [plan for plan in results if plan is not None]

    async def _complete_premium_squad_mutation(
        self,
        session: AsyncSession,
        plan: PremiumSquadMutationPlan,
    ) -> None:
        self._remember_premium_squad_match(plan.squad_match_cache_key)
        if plan.send_reset_notice:
            await self._maybe_send_premium_reset_notice(
                session,
                plan.sub,
                plan.tariff,
                used=plan.premium_used,
                limit=plan.premium_limit,
                period_start_at=plan.premium_period_start,
                previous_period_start=plan.previous_period_start,
                traffic_strategy=plan.traffic_strategy,
            )
        await self._sync_premium_connection_state(
            plan.sub,
            should_limit=plan.should_limit,
            newly_limited=plan.newly_limited,
            node_uuids=plan.node_uuids,
            start_date=plan.start_date,
            end_date=plan.end_date,
            panel_username=plan.panel_username,
        )
        logger.info(
            "Premium squad access %s for user %s tariff %s: %s/%s bytes",
            "limited" if plan.should_limit else "restored",
            plan.sub.user_id,
            getattr(plan.tariff, "key", "unknown"),
            plan.premium_used,
            plan.premium_limit,
        )

    async def _flush_premium_connection_drops(self) -> None:
        grouped: dict[tuple[str, ...], list[PremiumConnectionDropPlan]] = defaultdict(list)
        for plan in self._premium_connection_drops:
            grouped[plan.node_uuids].append(plan)
        for node_uuids, plans in grouped.items():
            dropped = await self.panel_service.drop_users_connections(
                [plan.panel_user_reference for plan in plans],
                list(node_uuids),
            )
            if not dropped:
                continue
            dropped_at = time.monotonic()
            for plan in plans:
                self._premium_drop_connections_at[plan.subscription_id] = dropped_at
        if self._premium_connection_drops:
            logger.info(
                "metric premium_connection_drop_batch users=%s target_sets=%s",
                len(self._premium_connection_drops),
                len(grouped),
            )
