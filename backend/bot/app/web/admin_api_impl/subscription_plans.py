"""Resolve plan metadata without losing disabled or removed tariff bindings."""

from typing import Any

from config.settings import Settings

from .subscription_plan_schemas import (
    AdminActiveTariffOut,
    AdminPlanOut,
    AdminSubscriptionPlanOut,
    AdminTariffOptionOut,
)


def _configured_tariffs(settings: Settings) -> dict[str, Any]:
    config = settings.tariffs_config
    return {str(tariff.key): tariff for tariff in getattr(config, "tariffs", []) or []}


def admin_plan_metadata(
    settings: Settings, *, tariff_key: str | None, is_trial: bool = False
) -> AdminPlanOut:
    if is_trial:
        return AdminPlanOut(
            kind="trial", tariff_key=None, tariff_names={}, is_configured=False, is_enabled=None
        )
    if not tariff_key:
        return AdminPlanOut(
            kind="unassigned",
            tariff_key=None,
            tariff_names={},
            is_configured=False,
            is_enabled=None,
        )
    config = settings.tariffs_config
    tariff = config.get(tariff_key) if config is not None else None
    return AdminPlanOut(
        kind="tariff",
        tariff_key=tariff_key,
        tariff_names=dict(getattr(tariff, "names", {}) or {}),
        is_configured=tariff is not None,
        is_enabled=bool(tariff.enabled) if tariff is not None else None,
    )


def admin_subscription_plan(
    settings: Settings, row: dict[str, Any] | None
) -> dict[str, Any] | None:
    if row is None:
        return None
    metadata = admin_plan_metadata(
        settings, tariff_key=row["tariff_key"], is_trial=bool(row["is_trial"])
    )
    return AdminSubscriptionPlanOut(
        **metadata.model_dump(), is_active=bool(row["is_active"])
    ).model_dump()


def admin_tariff_options(settings: Settings, observed_keys: list[str]) -> list[dict[str, Any]]:
    keys = list(_configured_tariffs(settings))
    keys.extend(sorted(set(observed_keys) - set(keys)))
    return [
        AdminTariffOptionOut(
            **admin_plan_metadata(settings, tariff_key=key).model_dump(exclude={"kind"})
        ).model_dump()
        for key in keys
    ]


def admin_active_tariffs(settings: Settings, counts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals = {
        (bool(row["is_trial"]), row["tariff_key"]): int(row["active_users"]) for row in counts
    }
    keys = list(_configured_tariffs(settings))
    keys.extend(sorted({key for trial, key in totals if not trial and key} - set(keys)))
    groups: list[tuple[bool, str | None]] = [(False, key) for key in keys]
    groups.extend([(True, None), (False, None)])
    return [
        AdminActiveTariffOut(
            **admin_plan_metadata(settings, tariff_key=key, is_trial=trial).model_dump(),
            active_users=totals.get((trial, key), 0),
        ).model_dump()
        for trial, key in groups
    ]
