"""Entitlement and recurring-billing rules for account merges."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sqlalchemy import delete, func, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import Select

from db.models import (
    AutoRenewCycle,
    FlexibleTrafficLimit,
    HwidDevicePurchase,
    PlategaSubscription,
    PromoCode,
    RollyPaySubscription,
    Subscription,
    TrafficTopup,
    TributeEntitlement,
    TributeProductPurchase,
    UserBalanceLedgerEntry,
    UserBilling,
    UserPanelSquadOverride,
    UserPaymentMethod,
)

_LIVE_PLATEGA_STATUSES = ("active", "past_due")
_LIVE_ROLLYPAY_STATUSES = (
    "consent_pending",
    "pending",
    "enabled",
    "review",
    "stop_pending",
)


@dataclass(frozen=True, slots=True)
class RecurringMergeState:
    source_has_recurring: bool
    target_has_recurring: bool
    source_managed_providers: tuple[str, ...]


def _is_free_grant_subscription(subscription: Subscription) -> bool:
    status = str(getattr(subscription, "status_from_panel", "") or "").strip().upper()
    if status in {"TRIAL", "ACTIVE_BONUS", "ACTIVE_MERGED_FREE_GRANT"}:
        return True
    provider = str(getattr(subscription, "provider", "") or "").strip().lower()
    try:
        duration_months = int(getattr(subscription, "duration_months", 0) or 0)
    except (TypeError, ValueError):
        duration_months = 0
    return (
        provider in {"", "trial"}
        and duration_months <= 0
        and not getattr(subscription, "duration_days", None)
    )


def _merged_subscription_end(
    source_subscription: Subscription,
    target_subscription: Subscription,
    *,
    now: datetime,
) -> tuple[datetime, str]:
    source_end = cast(datetime, source_subscription.end_date)
    if source_end.tzinfo is None:
        source_end = source_end.replace(tzinfo=UTC)

    target_end = cast(datetime, target_subscription.end_date)
    if target_end.tzinfo is None:
        target_end = target_end.replace(tzinfo=UTC)

    if _is_free_grant_subscription(source_subscription) or _is_free_grant_subscription(
        target_subscription
    ):
        # A free trial/bonus must not stack with another grant or paid time.
        return max(source_end, target_end), "ACTIVE_MERGED_FREE_GRANT"

    source_remaining = max(timedelta(0), source_end - now)
    base_end = target_end if target_end > now else now
    return base_end + source_remaining, "ACTIVE_EXTENDED_BY_MERGE"


def _decimal_value(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _entitlement_rank(
    subscription: Subscription,
) -> tuple[bool, Decimal, bool, int, bool, int, bool, int]:
    """Prefer paid and more valuable tariff-owned state, excluding additive purchases."""
    tier_baseline = max(0, int(getattr(subscription, "tier_baseline_bytes", 0) or 0))
    traffic_limit = max(0, int(getattr(subscription, "traffic_limit_bytes", 0) or 0))
    premium_baseline = max(0, int(getattr(subscription, "premium_baseline_bytes", 0) or 0))
    hwid_limit_raw = getattr(subscription, "hwid_device_limit", None)
    hwid_limit = -1 if hwid_limit_raw is None else int(hwid_limit_raw)
    return (
        not _is_free_grant_subscription(subscription),
        _decimal_value(getattr(subscription, "effective_monthly_price_rub", None)),
        bool(getattr(subscription, "regular_unlimited_override", False))
        or (bool(getattr(subscription, "tariff_key", None)) and tier_baseline == 0),
        max(tier_baseline, traffic_limit),
        bool(getattr(subscription, "premium_unlimited_override", False)),
        premium_baseline,
        hwid_limit == 0,
        hwid_limit,
    )


def _copy_tariff_owned_state(source: Subscription, target: Subscription) -> None:
    for field in (
        "tariff_key",
        "tariff_binding_source",
        "tariff_bound_at",
        "tariff_binding_note",
        "tier_baseline_bytes",
        "premium_baseline_bytes",
        "premium_is_limited",
        "effective_monthly_price_rub",
        "hwid_device_limit",
        "hwid_device_limit_is_override",
        "tariff_managed_squad_uuids",
    ):
        setattr(target, field, getattr(source, field, None))


def _explicit_hwid_overrides(
    source: Subscription,
    target: Subscription,
) -> list[int]:
    return [
        int(value)
        for subscription in (source, target)
        if bool(getattr(subscription, "hwid_device_limit_is_override", False))
        for value in (getattr(subscription, "hwid_device_limit", None),)
        if value is not None
    ]


def _apply_explicit_hwid_override(target: Subscription, overrides: list[int]) -> None:
    if not overrides:
        return
    target.hwid_device_limit = 0 if 0 in overrides else max(overrides)
    target.hwid_device_limit_is_override = True


def merge_subscription_state(
    source: Subscription,
    target: Subscription,
    *,
    now: datetime,
    source_has_recurring: bool,
    target_has_recurring: bool,
) -> None:
    """Consolidate active entitlement state without discarding paid balances."""
    merged_end, merged_status = _merged_subscription_end(source, target, now=now)
    source_is_preferred = _entitlement_rank(source) > _entitlement_rank(target)
    explicit_hwid_overrides = _explicit_hwid_overrides(source, target)
    if source_is_preferred:
        _copy_tariff_owned_state(source, target)

    for field in (
        "topup_balance_bytes",
        "regular_bonus_bytes",
        "premium_topup_balance_bytes",
        "premium_bonus_bytes",
    ):
        setattr(
            target,
            field,
            max(0, int(getattr(target, field, 0) or 0))
            + max(0, int(getattr(source, field, 0) or 0)),
        )

    target.regular_unlimited_override = bool(
        getattr(target, "regular_unlimited_override", False)
        or getattr(source, "regular_unlimited_override", False)
    )
    target.premium_unlimited_override = bool(
        getattr(target, "premium_unlimited_override", False)
        or getattr(source, "premium_unlimited_override", False)
    )
    _apply_explicit_hwid_override(target, explicit_hwid_overrides)
    target.extra_hwid_devices = max(0, int(getattr(target, "extra_hwid_devices", 0) or 0)) + max(
        0, int(getattr(source, "extra_hwid_devices", 0) or 0)
    )

    source_started = getattr(source, "start_date", None)
    target_started = getattr(target, "start_date", None)
    if source_started is not None and (target_started is None or source_started < target_started):
        target.start_date = source_started

    if source_has_recurring and not target_has_recurring:
        for field in (
            "provider",
            "auto_renew_enabled",
            "auto_renew_consent_version",
            "duration_months",
            "duration_days",
            "period_semantics",
        ):
            setattr(target, field, getattr(source, field, None))
    elif source_is_preferred and not target_has_recurring:
        for field in (
            "provider",
            "duration_months",
            "duration_days",
            "period_semantics",
        ):
            setattr(target, field, getattr(source, field, None))

    target.end_date = merged_end
    target.last_notification_sent = None
    target.is_active = True
    target.skip_notifications = False
    target.status_from_panel = merged_status

    source.is_active = False
    source.auto_renew_enabled = False
    source.skip_notifications = True
    source.last_notification_sent = None
    source.status_from_panel = "MERGED_INTO_ACCOUNT"


async def merge_active_subscription_entitlements(
    session: AsyncSession,
    source: Subscription,
    target: Subscription,
    *,
    now: datetime,
    source_has_recurring: bool,
    target_has_recurring: bool,
) -> None:
    merge_subscription_state(
        source,
        target,
        now=now,
        source_has_recurring=source_has_recurring,
        target_has_recurring=target_has_recurring,
    )
    for model in (TrafficTopup, FlexibleTrafficLimit, HwidDevicePurchase):
        await session.execute(
            update(model)
            .where(model.subscription_id == source.subscription_id)
            .values(subscription_id=target.subscription_id)
        )


async def merge_user_billing_state(
    session: AsyncSession,
    *,
    source_user_id: int,
    target_user_id: int,
    source_subscription: Subscription | None,
    recurring_state: RecurringMergeState,
) -> None:
    """Keep payment credentials that belong to the one surviving recurrence."""

    target_method_ids = select(UserPaymentMethod.provider_payment_method_id).where(
        UserPaymentMethod.user_id == target_user_id
    )
    source_recurring_provider = (
        str(getattr(source_subscription, "provider", None) or "").strip().lower()
    )
    source_recurrence_wins = bool(
        recurring_state.source_has_recurring and not recurring_state.target_has_recurring
    )
    if source_recurrence_wins and source_recurring_provider:
        await session.execute(
            update(UserPaymentMethod)
            .where(
                UserPaymentMethod.user_id == target_user_id,
                func.lower(UserPaymentMethod.provider) == source_recurring_provider,
            )
            .values(is_default=False)
        )
    else:
        target_default_providers = select(func.lower(UserPaymentMethod.provider)).where(
            UserPaymentMethod.user_id == target_user_id,
            UserPaymentMethod.is_default == True,
        )
        await session.execute(
            update(UserPaymentMethod)
            .where(
                UserPaymentMethod.user_id == source_user_id,
                UserPaymentMethod.is_default == True,
                func.lower(UserPaymentMethod.provider).in_(target_default_providers),
            )
            .values(is_default=False)
        )
    await session.execute(
        delete(UserPaymentMethod).where(
            UserPaymentMethod.user_id == source_user_id,
            UserPaymentMethod.provider_payment_method_id.in_(target_method_ids),
        )
    )
    await session.execute(
        update(UserPaymentMethod)
        .where(UserPaymentMethod.user_id == source_user_id)
        .values(user_id=target_user_id)
    )

    target_has_billing = (
        await session.execute(
            select(UserBilling.user_id).where(UserBilling.user_id == target_user_id)
        )
    ).scalar_one_or_none()
    if target_has_billing and source_recurrence_wins:
        await session.execute(delete(UserBilling).where(UserBilling.user_id == target_user_id))
        await session.execute(
            update(UserBilling)
            .where(UserBilling.user_id == source_user_id)
            .values(user_id=target_user_id)
        )
    elif target_has_billing:
        await session.execute(delete(UserBilling).where(UserBilling.user_id == source_user_id))
    else:
        await session.execute(
            update(UserBilling)
            .where(UserBilling.user_id == source_user_id)
            .values(user_id=target_user_id)
        )


async def transfer_entitlement_ownership(
    session: AsyncSession,
    *,
    source_user_id: int,
    target_user_id: int,
    panel_user_uuid: str | None,
) -> None:
    """Move entitlement, balance, and provider records off the deleted user."""

    target_override_keys = select(
        UserPanelSquadOverride.kind,
        UserPanelSquadOverride.override_key,
    ).where(UserPanelSquadOverride.user_id == target_user_id)
    await session.execute(
        delete(UserPanelSquadOverride).where(
            UserPanelSquadOverride.user_id == source_user_id,
            tuple_(
                UserPanelSquadOverride.kind,
                UserPanelSquadOverride.override_key,
            ).in_(target_override_keys),
        )
    )
    override_values: dict[str, Any] = {"user_id": target_user_id}
    if panel_user_uuid:
        override_values["panel_user_uuid"] = panel_user_uuid
    await session.execute(
        update(UserPanelSquadOverride)
        .where(UserPanelSquadOverride.user_id == source_user_id)
        .values(**override_values)
    )

    for model in (
        AutoRenewCycle,
        PlategaSubscription,
        PromoCode,
        RollyPaySubscription,
        TributeEntitlement,
        TributeProductPurchase,
        UserBalanceLedgerEntry,
    ):
        await session.execute(
            update(model).where(model.user_id == source_user_id).values(user_id=target_user_id)
        )
    await session.execute(
        update(UserBalanceLedgerEntry)
        .where(UserBalanceLedgerEntry.actor_admin_id == source_user_id)
        .values(actor_admin_id=target_user_id)
    )


async def _has_row(session: AsyncSession, statement: Select[tuple[int]]) -> bool:
    result = await session.execute(statement)
    return result.scalar_one_or_none() is not None


async def inspect_recurring_merge(
    session: AsyncSession,
    *,
    source_user_id: int,
    target_user_id: int,
    source_subscription: Subscription | None,
    target_subscription: Subscription | None,
    now: datetime,
) -> RecurringMergeState:
    async def account_recurring_state(
        user_id: int,
        subscription: Subscription | None,
    ) -> tuple[bool, tuple[str, ...]]:
        managed_providers: list[str] = []
        provider_statements = (
            (
                "platega",
                select(PlategaSubscription.id)
                .where(
                    PlategaSubscription.user_id == user_id,
                    PlategaSubscription.status.in_(_LIVE_PLATEGA_STATUSES),
                )
                .limit(1),
            ),
            (
                "rollypay",
                select(RollyPaySubscription.id)
                .where(
                    RollyPaySubscription.user_id == user_id,
                    RollyPaySubscription.billing_status.in_(_LIVE_ROLLYPAY_STATUSES),
                )
                .limit(1),
            ),
            (
                "tribute",
                select(TributeEntitlement.entitlement_id)
                .where(
                    TributeEntitlement.user_id == user_id,
                    TributeEntitlement.status == "active",
                    TributeEntitlement.active_until > now,
                )
                .limit(1),
            ),
        )
        for provider, statement in provider_statements:
            if await _has_row(session, statement):
                managed_providers.append(provider)
        local_recurring = bool(
            subscription is not None and getattr(subscription, "auto_renew_enabled", False)
        )
        return local_recurring or bool(managed_providers), tuple(managed_providers)

    source_has_recurring, source_managed_providers = await account_recurring_state(
        source_user_id,
        source_subscription,
    )
    target_has_recurring, _ = await account_recurring_state(
        target_user_id,
        target_subscription,
    )
    return RecurringMergeState(
        source_has_recurring=source_has_recurring,
        target_has_recurring=target_has_recurring,
        source_managed_providers=source_managed_providers,
    )
