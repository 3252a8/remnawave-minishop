from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.checkout_addons import checkout_addon_grants, parse_checkout_bundle_snapshot
from db.dal import subscription_dal

_SNAPSHOT_VERSION = 1
_STRICT_ACTIVE_ADDON_BASES = {
    "topup",
    "premium_topup",
    "hwid_device",
    "hwid_devices",
    "hwid_devices_renewal",
}
_CONTEXT_BOUND_BASES = {*_STRICT_ACTIVE_ADDON_BASES, "traffic_package"}


class EntitlementContextError(ValueError):
    """The requested one-time purchase is not valid for the active entitlement."""


class EntitlementPreflightStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    OK = "ok"
    DETERMINISTIC_STALE = "deterministic_stale"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class EntitlementContextSnapshot:
    target_tariff_key: str | None
    active_subscription_id: int | None
    active_tariff_key: str | None


@dataclass(frozen=True, slots=True)
class EntitlementPreflightResult:
    status: EntitlementPreflightStatus
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.status in {
            EntitlementPreflightStatus.NOT_APPLICABLE,
            EntitlementPreflightStatus.OK,
        }


def _sale_mode_base(value: Any) -> str:
    return str(value or "").split("@", 1)[0].split("|", 1)[0]


def _sale_mode_tariff_key(value: Any) -> str | None:
    text = str(value or "")
    if "@" not in text:
        return None
    return text.split("@", 1)[1].split("|", 1)[0].strip() or None


def _is_combined_hwid_renewal(value: Any) -> bool:
    text = str(value or "")
    return _sale_mode_base(text) == "subscription" and "hwid_renewal" in {
        token.strip().lower() for token in text.split("|")[1:] if token.strip()
    }


def payment_uses_entitlement_context(payment_or_sale_mode: Any) -> bool:
    sale_mode = (
        getattr(payment_or_sale_mode, "sale_mode", None)
        if not isinstance(payment_or_sale_mode, str)
        else payment_or_sale_mode
    )
    if _sale_mode_base(sale_mode) in _CONTEXT_BOUND_BASES or _is_combined_hwid_renewal(sale_mode):
        return True
    if not isinstance(payment_or_sale_mode, str):
        return (
            bool(
                str(getattr(payment_or_sale_mode, "entitlement_context_snapshot", "") or "").strip()
            )
            or _subscription_checkout_snapshot(payment_or_sale_mode) is not None
        )
    return False


def _subscription_checkout_snapshot(payment: Any) -> dict[str, Any] | None:
    if _sale_mode_base(getattr(payment, "sale_mode", None)) != "subscription":
        return None
    snapshot = parse_checkout_bundle_snapshot(getattr(payment, "checkout_bundle_snapshot", None))
    if snapshot is None or snapshot.get("version") == 1 or "active_context" not in snapshot:
        return None
    return snapshot


def _preflight_checkout_context(
    payment: Any, active_subscription: Any | None
) -> EntitlementPreflightResult | None:
    snapshot = _subscription_checkout_snapshot(payment)
    if snapshot is None:
        return None
    try:
        grants = checkout_addon_grants(getattr(payment, "checkout_bundle_snapshot", None))
        context = snapshot.get("active_context")
        if context is not None and (
            not isinstance(context, dict)
            or grants.active_subscription_id is None
            or grants.active_subscription_id <= 0
            or grants.active_end_at is None
        ):
            return EntitlementPreflightResult(
                EntitlementPreflightStatus.INVALID, "checkout_context_invalid"
            )
        current_id = int(active_subscription.subscription_id) if active_subscription else None
        current_end = (
            getattr(active_subscription, "end_date", None) if active_subscription else None
        )
        if current_end is not None:
            if not isinstance(current_end, datetime):
                return EntitlementPreflightResult(
                    EntitlementPreflightStatus.INVALID, "current_subscription_invalid"
                )
            current_end = (
                current_end.replace(tzinfo=UTC)
                if current_end.tzinfo is None
                else current_end.astimezone(UTC)
            )
    except (AttributeError, TypeError, ValueError):
        return EntitlementPreflightResult(
            EntitlementPreflightStatus.INVALID, "checkout_context_invalid"
        )
    if current_id != grants.active_subscription_id:
        return EntitlementPreflightResult(
            EntitlementPreflightStatus.DETERMINISTIC_STALE, "active_subscription_changed"
        )
    if current_end != grants.active_end_at:
        return EntitlementPreflightResult(
            EntitlementPreflightStatus.DETERMINISTIC_STALE, "active_subscription_end_changed"
        )
    return EntitlementPreflightResult(EntitlementPreflightStatus.OK)


def build_entitlement_context_snapshot(
    *,
    sale_mode: str,
    active_subscription: Any | None,
    bind_to_active_subscription: bool = False,
) -> str | None:
    """Freeze the subscription a one-time entitlement checkout was quoted for."""

    active_subscription_id: int | None = None
    active_tariff_key: str | None = None
    if active_subscription is not None:
        active_subscription_id = getattr(active_subscription, "subscription_id", None)
        active_tariff_key = getattr(active_subscription, "tariff_key", None)
    return build_entitlement_context_snapshot_from_values(
        sale_mode=sale_mode,
        active_subscription_id=active_subscription_id,
        active_tariff_key=active_tariff_key,
        bind_to_active_subscription=bind_to_active_subscription,
    )


def build_entitlement_context_snapshot_from_values(
    *,
    sale_mode: str,
    active_subscription_id: Any | None,
    active_tariff_key: Any | None,
    bind_to_active_subscription: bool = False,
) -> str | None:
    """Freeze a quote-owned subscription identity without re-reading current state."""

    base = _sale_mode_base(sale_mode)
    combined_hwid_renewal = _is_combined_hwid_renewal(sale_mode)
    if (
        base not in _CONTEXT_BOUND_BASES
        and not combined_hwid_renewal
        and not bind_to_active_subscription
    ):
        return None
    target_tariff_key = _sale_mode_tariff_key(sale_mode)
    if not target_tariff_key and not bind_to_active_subscription:
        # Legacy non-tariff traffic mode has no cross-tariff identity to bind.
        return None

    normalized_subscription_id: int | None = None
    normalized_tariff_key: str | None = None
    if active_subscription_id is not None:
        try:
            normalized_subscription_id = int(active_subscription_id)
        except (TypeError, ValueError) as exc:
            raise EntitlementContextError("invalid_active_subscription") from exc
        if normalized_subscription_id <= 0:
            raise EntitlementContextError("invalid_active_subscription")
        normalized_tariff_key = str(active_tariff_key or "").strip() or None
    elif active_tariff_key is not None:
        raise EntitlementContextError("invalid_active_subscription")

    strict_active_subscription = (
        base in _STRICT_ACTIVE_ADDON_BASES or combined_hwid_renewal or bind_to_active_subscription
    )
    if strict_active_subscription and normalized_subscription_id is None:
        raise EntitlementContextError("active_subscription_required")
    if normalized_subscription_id is not None and normalized_tariff_key != target_tariff_key:
        raise EntitlementContextError("active_tariff_mismatch")

    return json.dumps(
        {
            "active_subscription_id": normalized_subscription_id,
            "active_tariff_key": normalized_tariff_key,
            "target_tariff_key": target_tariff_key,
            "version": _SNAPSHOT_VERSION,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


async def snapshot_current_entitlement_context(
    session: AsyncSession,
    *,
    user_id: int,
    sale_mode: str,
) -> str | None:
    if not payment_uses_entitlement_context(sale_mode):
        return None
    active_subscription = await subscription_dal.get_active_subscription_by_user_id(
        session,
        int(user_id),
    )
    return build_entitlement_context_snapshot(
        sale_mode=sale_mode,
        active_subscription=active_subscription,
    )


def parse_entitlement_context_snapshot(value: Any) -> EntitlementContextSnapshot | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError("snapshot_not_text")
    try:
        payload = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("snapshot_not_json") from exc
    if not isinstance(payload, dict):
        raise ValueError("snapshot_not_object")
    expected_fields = {
        "active_subscription_id",
        "active_tariff_key",
        "target_tariff_key",
        "version",
    }
    if set(payload) != expected_fields or payload.get("version") != _SNAPSHOT_VERSION:
        raise ValueError("snapshot_schema_mismatch")

    raw_target_tariff = payload.get("target_tariff_key")
    target_tariff_key = str(raw_target_tariff).strip() if raw_target_tariff is not None else None
    if target_tariff_key == "":
        raise ValueError("snapshot_target_invalid")

    raw_subscription_id = payload.get("active_subscription_id")
    if raw_subscription_id is None:
        active_subscription_id = None
    elif not isinstance(raw_subscription_id, int) or isinstance(raw_subscription_id, bool):
        raise ValueError("snapshot_subscription_invalid")
    else:
        active_subscription_id = raw_subscription_id
        if active_subscription_id <= 0:
            raise ValueError("snapshot_subscription_invalid")

    raw_active_tariff = payload.get("active_tariff_key")
    active_tariff_key = str(raw_active_tariff).strip() if raw_active_tariff is not None else None
    if active_tariff_key == "":
        raise ValueError("snapshot_active_tariff_invalid")
    if active_subscription_id is None and active_tariff_key is not None:
        raise ValueError("snapshot_active_state_invalid")

    return EntitlementContextSnapshot(
        target_tariff_key=target_tariff_key,
        active_subscription_id=active_subscription_id,
        active_tariff_key=active_tariff_key,
    )


def preflight_payment_entitlement(
    payment: Any,
    active_subscription: Any | None,
) -> EntitlementPreflightResult:
    """Pure deterministic guard run before a one-time entitlement is mutated."""

    sale_mode = str(getattr(payment, "sale_mode", "") or "")
    base = _sale_mode_base(sale_mode)
    if not payment_uses_entitlement_context(payment):
        return EntitlementPreflightResult(EntitlementPreflightStatus.NOT_APPLICABLE)

    checkout_preflight = _preflight_checkout_context(payment, active_subscription)
    if checkout_preflight is not None:
        if not checkout_preflight.allowed:
            return checkout_preflight
        if not _is_combined_hwid_renewal(sale_mode) and not getattr(
            payment, "entitlement_context_snapshot", None
        ):
            return checkout_preflight

    payment_tariff_key = str(
        getattr(payment, "tariff_key", "") or ""
    ).strip() or _sale_mode_tariff_key(sale_mode)
    raw_snapshot = getattr(payment, "entitlement_context_snapshot", None)
    try:
        snapshot = parse_entitlement_context_snapshot(raw_snapshot)
    except ValueError as exc:
        return EntitlementPreflightResult(
            EntitlementPreflightStatus.INVALID,
            str(exc),
        )

    current_subscription_id: int | None = None
    current_tariff_key: str | None = None
    if active_subscription is not None:
        try:
            current_subscription_id = int(active_subscription.subscription_id)
        except (AttributeError, TypeError, ValueError):
            return EntitlementPreflightResult(
                EntitlementPreflightStatus.INVALID,
                "current_subscription_invalid",
            )
        if current_subscription_id <= 0:
            return EntitlementPreflightResult(
                EntitlementPreflightStatus.INVALID,
                "current_subscription_invalid",
            )
        current_tariff_key = (
            str(getattr(active_subscription, "tariff_key", "") or "").strip() or None
        )

    if snapshot is not None:
        if payment_tariff_key != snapshot.target_tariff_key:
            return EntitlementPreflightResult(
                EntitlementPreflightStatus.INVALID,
                "payment_target_mismatch",
            )
        if current_subscription_id != snapshot.active_subscription_id:
            return EntitlementPreflightResult(
                EntitlementPreflightStatus.DETERMINISTIC_STALE,
                "active_subscription_changed",
            )
        if current_tariff_key != snapshot.active_tariff_key:
            return EntitlementPreflightResult(
                EntitlementPreflightStatus.DETERMINISTIC_STALE,
                "active_tariff_changed",
            )

    if (
        base in _STRICT_ACTIVE_ADDON_BASES or _is_combined_hwid_renewal(sale_mode)
    ) and current_subscription_id is None:
        return EntitlementPreflightResult(
            EntitlementPreflightStatus.DETERMINISTIC_STALE,
            "active_subscription_required",
        )
    if (
        payment_tariff_key
        and current_subscription_id is not None
        and current_tariff_key != payment_tariff_key
    ):
        return EntitlementPreflightResult(
            EntitlementPreflightStatus.DETERMINISTIC_STALE,
            "active_tariff_mismatch",
        )

    return EntitlementPreflightResult(EntitlementPreflightStatus.OK)
