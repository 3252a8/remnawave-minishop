"""Immutable checkout snapshots for paid tariff changes."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from config.tariffs_config import TariffsConfig
from db.models import Payment, Subscription

from .sale_mode import parse_sale_mode_context

_SNAPSHOT_VERSION = 1
_TRANSITION_MODE = "period_to_period"
_TRANSITION_BILLING_MODEL = "period"
_CURRENCY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class TariffChangeQuoteSnapshot:
    source_tariff_key: str
    target_tariff_key: str
    required_amount: Decimal
    currency: str
    convertible_hwid_purchase_ids: tuple[int, ...]
    transition_mode: str = _TRANSITION_MODE
    version: int = _SNAPSHOT_VERSION

    def charged_amount_matches(self, amount: object) -> bool:
        try:
            charged = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            return False
        if not charged.is_finite():
            return False
        return charged.quantize(_CURRENCY_QUANTUM, rounding=ROUND_HALF_UP) == (
            self.required_amount.quantize(_CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)
        )

    def to_json(self) -> str:
        payload = {
            "convertible_hwid_purchase_ids": list(self.convertible_hwid_purchase_ids),
            "currency": self.currency,
            "required_amount": format(self.required_amount, "f"),
            "source_tariff_key": self.source_tariff_key,
            "target_tariff_key": self.target_tariff_key,
            "transition_mode": self.transition_mode,
            "version": self.version,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class TariffChangePreflightStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    OK = "ok"
    DETERMINISTIC_STALE = "deterministic_stale"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class TariffChangePreflightResult:
    status: TariffChangePreflightStatus
    reason: str
    snapshot: TariffChangeQuoteSnapshot | None = None

    @property
    def allowed(self) -> bool:
        return self.status in {
            TariffChangePreflightStatus.NOT_APPLICABLE,
            TariffChangePreflightStatus.OK,
        }

    @property
    def deterministic_stale(self) -> bool:
        return self.status is TariffChangePreflightStatus.DETERMINISTIC_STALE


def build_tariff_change_quote_snapshot(
    *,
    source_tariff_key: str,
    target_tariff_key: str,
    required_amount: object,
    currency: str,
    convertible_hwid_purchase_ids: Iterable[int],
) -> str:
    snapshot = TariffChangeQuoteSnapshot(
        source_tariff_key=_required_text(source_tariff_key, "source_tariff_key"),
        target_tariff_key=_required_text(target_tariff_key, "target_tariff_key"),
        required_amount=_positive_amount(required_amount),
        currency=_required_text(currency, "currency").upper(),
        convertible_hwid_purchase_ids=_purchase_ids(tuple(convertible_hwid_purchase_ids)),
    )
    return snapshot.to_json()


def parse_tariff_change_quote_snapshot(value: object) -> TariffChangeQuoteSnapshot | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError("tariff-change quote snapshot must be JSON text")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid tariff-change quote snapshot JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("tariff-change quote snapshot must be an object")
    if payload.get("version") != _SNAPSHOT_VERSION:
        raise ValueError("unsupported tariff-change quote snapshot version")
    transition_mode = _required_text(payload.get("transition_mode"), "transition_mode")
    if transition_mode != _TRANSITION_MODE:
        raise ValueError("unsupported tariff-change transition mode")
    return TariffChangeQuoteSnapshot(
        source_tariff_key=_required_text(payload.get("source_tariff_key"), "source_tariff_key"),
        target_tariff_key=_required_text(payload.get("target_tariff_key"), "target_tariff_key"),
        required_amount=_positive_amount(payload.get("required_amount")),
        currency=_required_text(payload.get("currency"), "currency").upper(),
        convertible_hwid_purchase_ids=_purchase_ids(payload.get("convertible_hwid_purchase_ids")),
        transition_mode=transition_mode,
    )


def preflight_paid_tariff_change(
    *,
    payment: Payment,
    active_subscription: Subscription | None,
    tariffs_config: TariffsConfig | None,
    expected_user_id: int,
    expected_target_tariff_key: str,
) -> TariffChangePreflightResult:
    """Validate an immutable paid-upgrade quote without changing state."""

    try:
        snapshot = parse_tariff_change_quote_snapshot(
            getattr(payment, "tariff_change_quote_snapshot", None)
        )
    except ValueError:
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.INVALID,
            "invalid_quote_snapshot",
        )
    if snapshot is None:
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.NOT_APPLICABLE,
            "legacy_payment_without_quote_snapshot",
        )

    sale_context = parse_sale_mode_context(str(getattr(payment, "sale_mode", "") or ""))
    stored_tariff_key = str(getattr(payment, "tariff_key", "") or "").strip()
    payment_tariff_key = sale_context.tariff_key or stored_tariff_key
    normalized_expected_target = str(expected_target_tariff_key or "").strip()
    payment_currency = str(getattr(payment, "currency", "") or "").strip().upper()
    if (
        int(getattr(payment, "user_id", 0) or 0) != int(expected_user_id)
        or sale_context.base != "tariff_upgrade"
        or not normalized_expected_target
        or (
            sale_context.tariff_key is not None
            and sale_context.tariff_key != normalized_expected_target
        )
        or (stored_tariff_key and stored_tariff_key != normalized_expected_target)
        or payment_tariff_key != normalized_expected_target
        or snapshot.target_tariff_key != payment_tariff_key
        or not snapshot.charged_amount_matches(getattr(payment, "amount", None))
        or snapshot.currency != payment_currency
    ):
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.INVALID,
            "payment_quote_mismatch",
            snapshot,
        )

    if tariffs_config is None:
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
            "target_tariff_unconfigured",
            snapshot,
        )
    try:
        configured_target = tariffs_config.require(normalized_expected_target)
    except KeyError:
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
            "target_tariff_unconfigured",
            snapshot,
        )
    if (
        configured_target.key != snapshot.target_tariff_key
        or str(configured_target.billing_model) != _TRANSITION_BILLING_MODEL
    ):
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
            "target_tariff_changed",
            snapshot,
        )

    if active_subscription is None:
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
            "active_subscription_missing",
            snapshot,
        )
    if int(getattr(active_subscription, "user_id", 0) or 0) != int(expected_user_id):
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.INVALID,
            "active_subscription_user_mismatch",
            snapshot,
        )
    if str(
        getattr(active_subscription, "provider", "") or ""
    ).strip().lower() == "tribute" and bool(
        getattr(active_subscription, "auto_renew_enabled", False)
    ):
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
            "active_tribute_recurrence",
            snapshot,
        )

    try:
        configured_source = tariffs_config.require_configured(
            str(getattr(active_subscription, "tariff_key", "") or "")
        )
    except KeyError:
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
            "source_tariff_unconfigured",
            snapshot,
        )
    if (
        configured_source.key != snapshot.source_tariff_key
        or str(configured_source.billing_model) != _TRANSITION_BILLING_MODEL
    ):
        return TariffChangePreflightResult(
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
            "source_tariff_changed",
            snapshot,
        )
    return TariffChangePreflightResult(
        TariffChangePreflightStatus.OK,
        "quote_matches_current_state",
        snapshot,
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _positive_amount(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("required_amount must be numeric") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("required_amount must be finite and positive")
    return amount


def _purchase_ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("convertible_hwid_purchase_ids must be a list")
    purchase_ids: list[int] = []
    seen: set[int] = set()
    for item in value:
        if type(item) is not int or item <= 0:
            raise ValueError("convertible_hwid_purchase_ids must contain positive integers")
        if item in seen:
            raise ValueError("convertible_hwid_purchase_ids must not contain duplicates")
        seen.add(item)
        purchase_ids.append(item)
    return tuple(purchase_ids)
