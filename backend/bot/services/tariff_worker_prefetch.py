"""Read exact premium periods before acquiring subscription row locks."""

import asyncio
from datetime import datetime
from functools import cached_property
from typing import Any, Protocol

from bot.infra.performance import performance_phase
from bot.services.subscription_order_terms import gift_tariff
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from config.tariffs_config import Tariff, TariffsConfig
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


class BatchTariffs:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def catalog(self) -> TariffsConfig | None:
        return self.settings.tariffs_config

    def for_subscription(self, sub: Subscription) -> Tariff | None:
        frozen = gift_tariff(sub)
        if frozen is not None:
            return frozen
        if self.catalog is None or not sub.tariff_key:
            return None
        return self.catalog.require_configured(sub.tariff_key)


async def prefetch_premium_periods(
    worker: PremiumPrefetchWorker,
    subs: list[Subscription],
    payloads: list[dict],
    now: datetime,
    tariffs: BatchTariffs | None = None,
) -> None:
    tariffs = tariffs or BatchTariffs(worker.settings)
    groups: set[tuple[tuple[str, ...], str, str]] = set()
    for sub, payload in zip(subs, payloads, strict=True):
        if not payload:
            continue
        try:
            if not sub.tariff_key and worker._is_trial_subscription(sub):
                tariff = worker._trial_premium_tariff()
            else:
                tariff = tariffs.for_subscription(sub)
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
