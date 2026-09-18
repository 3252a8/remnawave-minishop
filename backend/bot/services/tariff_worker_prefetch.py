"""Read exact premium periods before acquiring subscription row locks."""

import asyncio
from datetime import datetime
from typing import Any, Protocol

from bot.infra.performance import performance_phase
from bot.services.subscription_order_terms import gift_tariff
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.models import Subscription


class PremiumPrefetchTariff(Protocol):
    @property
    def billing_model(self) -> str: ...
    @property
    def premium_squad_uuids(self) -> list[str]: ...
    def has_premium_squad_limit(self) -> bool: ...


class PremiumPrefetchWorker(Protocol):
    settings: Settings
    subscription_service: SubscriptionService

    def _trial_premium_tariff(self) -> PremiumPrefetchTariff | None: ...
    def _is_trial_subscription(self, sub: Subscription) -> bool: ...
    async def _premium_node_uuids_for_tariff(self, tariff: Any) -> list[str]: ...
    async def _premium_usage_snapshot_for_nodes(
        self, nodes: list[str], start: str, end: str
    ) -> Any: ...


async def prefetch_premium_periods(
    worker: PremiumPrefetchWorker,
    subs: list[Subscription],
    payloads: list[dict],
    now: datetime,
) -> None:
    groups: set[tuple[tuple[str, ...], str, str]] = set()
    for sub, payload in zip(subs, payloads, strict=True):
        if not payload:
            continue
        try:
            tariff = (
                worker._trial_premium_tariff()
                if not sub.tariff_key and worker._is_trial_subscription(sub)
                else gift_tariff(sub)
                or worker.settings.tariffs_config.require_configured(sub.tariff_key)
            )
        except (KeyError, ValueError):
            continue
        if tariff is None or not tariff.premium_squad_uuids or not tariff.has_premium_squad_limit():
            continue
        period = worker.subscription_service._premium_accounting_period_start(
            sub,
            now,
            panel_user_data=payload if tariff.billing_model == "period" else None,
            tariff=tariff,
        )
        nodes = await worker._premium_node_uuids_for_tariff(tariff)
        if nodes:
            groups.add((tuple(sorted(nodes)), period.date().isoformat(), now.date().isoformat()))
    semaphore = asyncio.Semaphore(4)

    async def load(group: tuple[tuple[str, ...], str, str]) -> None:
        nodes, start, end = group
        async with semaphore:
            await worker._premium_usage_snapshot_for_nodes(list(nodes), start, end)

    with performance_phase("premium_prefetch"):
        await asyncio.gather(*(load(group) for group in sorted(groups)))
