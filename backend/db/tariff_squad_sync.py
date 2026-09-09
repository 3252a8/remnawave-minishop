"""Durable snapshots used while reconciling tariff squad catalog edits."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.tariffs_config import TariffsConfig
from db.models import Subscription


def _dedupe_squad_uuids(values: list[str] | tuple[str, ...] | None) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values or [] if str(value).strip()))


def tariff_managed_squad_uuids(tariff: Any) -> list[str]:
    return _dedupe_squad_uuids(
        [
            *list(getattr(tariff, "squad_uuids", None) or []),
            *list(getattr(tariff, "premium_squad_uuids", None) or []),
        ]
    )


def subscription_tariff_managed_squad_uuids(subscription: Any) -> list[str]:
    raw = getattr(subscription, "tariff_managed_squad_uuids", None)
    if not raw:
        return []
    try:
        decoded = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return _dedupe_squad_uuids(decoded if isinstance(decoded, list) else [])


def tariff_squad_override_detection_uuids(subscription: Any, tariff: Any) -> list[str]:
    return _dedupe_squad_uuids(
        [
            *subscription_tariff_managed_squad_uuids(subscription),
            *tariff_managed_squad_uuids(tariff),
        ]
    )


def remember_subscription_tariff_managed_squad_uuids(
    subscription: Any,
    squad_uuids: list[str] | tuple[str, ...],
) -> None:
    subscription.tariff_managed_squad_uuids = json.dumps(
        _dedupe_squad_uuids(squad_uuids),
        separators=(",", ":"),
    )


def remember_subscription_tariff_managed_squads(subscription: Any, tariff: Any) -> None:
    remember_subscription_tariff_managed_squad_uuids(
        subscription,
        tariff_managed_squad_uuids(tariff),
    )


async def snapshot_previous_tariff_squads(
    session: AsyncSession,
    previous_config: TariffsConfig,
    next_config: TariffsConfig,
) -> int:
    previous_by_key: dict[str, list[str]] = {}
    next_by_key: dict[str, list[str]] = {}
    for tariff in previous_config.tariffs:
        squads = tariff_managed_squad_uuids(tariff)
        for key in (tariff.key, *tariff.legacy_keys):
            previous_by_key[str(key)] = squads
    for tariff in next_config.tariffs:
        squads = tariff_managed_squad_uuids(tariff)
        for key in (tariff.key, *tariff.legacy_keys):
            next_by_key[str(key)] = squads

    changed_keys = sorted(
        key
        for key in previous_by_key.keys() & next_by_key.keys()
        if previous_by_key[key] != next_by_key[key]
    )
    if not changed_keys:
        return 0

    result = await session.execute(
        select(Subscription).where(Subscription.tariff_key.in_(changed_keys))
    )
    subscriptions = list(result.scalars().all())
    for subscription in subscriptions:
        tariff_key = str(subscription.tariff_key)
        remembered = subscription_tariff_managed_squad_uuids(subscription)
        remember_subscription_tariff_managed_squad_uuids(
            subscription,
            [*remembered, *previous_by_key[tariff_key]],
        )
    await session.flush()
    return len(subscriptions)
