from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from yookassa.domain.exceptions import ApiError

if TYPE_CHECKING:
    from bot.payment_providers.shared import RecurringChargeResult

TRANSPORT_RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=13),
)
TRANSPORT_RETRY_DEADLINE = timedelta(minutes=30)
YOOKASSA_IDEMPOTENCE_WINDOW = timedelta(hours=24)

FINANCIAL_RETRY_DELAYS = {
    "insufficient_funds": timedelta(hours=12),
    "issuer_unavailable": timedelta(minutes=30),
    "internal_timeout": timedelta(minutes=30),
}


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported auto-renew snapshot value: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class YooKassaRecurringSnapshot:
    amount: float
    currency: str
    months: int
    sale_mode: str
    description: str
    metadata: dict[str, str]
    hwid_quote: dict[str, Any] | None
    entitlement_context_snapshot: str | None
    checkout_bundle_snapshot: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )

    @classmethod
    def from_json(cls, raw: str) -> YooKassaRecurringSnapshot:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Auto-renew request snapshot must be an object")
        metadata = payload.get("metadata")
        hwid_quote = payload.get("hwid_quote")
        if not isinstance(metadata, dict):
            raise ValueError("Auto-renew request snapshot metadata must be an object")
        if hwid_quote is not None and not isinstance(hwid_quote, dict):
            raise ValueError("Auto-renew request snapshot HWID quote must be an object")
        return cls(
            amount=float(payload["amount"]),
            currency=str(payload["currency"]),
            months=int(payload["months"]),
            sale_mode=str(payload["sale_mode"]),
            description=str(payload["description"]),
            metadata={str(key): str(value) for key, value in metadata.items()},
            hwid_quote=hwid_quote,
            entitlement_context_snapshot=(
                str(payload["entitlement_context_snapshot"])
                if payload.get("entitlement_context_snapshot") is not None
                else None
            ),
            checkout_bundle_snapshot=(
                str(payload["checkout_bundle_snapshot"])
                if payload.get("checkout_bundle_snapshot") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class YooKassaProviderRequestSnapshot:
    """Exact provider-call inputs reused for same-key transport recovery."""

    merchant_id: str
    amount: float
    currency: str
    description: str
    metadata: dict[str, str]
    receipt_customer: dict[str, str]
    receipt_vat_code: str
    receipt_payment_mode: str
    receipt_payment_subject: str
    payment_method_id: str
    capture: bool = True

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> YooKassaProviderRequestSnapshot:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("YooKassa provider request snapshot must be an object")
        metadata = payload.get("metadata")
        receipt_customer = payload.get("receipt_customer")
        if not isinstance(metadata, dict):
            raise ValueError("YooKassa provider request metadata must be an object")
        if not isinstance(receipt_customer, dict):
            raise ValueError("YooKassa receipt customer must be an object")
        return cls(
            merchant_id=str(payload["merchant_id"]),
            amount=float(payload["amount"]),
            currency=str(payload["currency"]),
            description=str(payload["description"]),
            metadata={str(key): str(value) for key, value in metadata.items()},
            receipt_customer={str(key): str(value) for key, value in receipt_customer.items()},
            receipt_vat_code=str(payload["receipt_vat_code"]),
            receipt_payment_mode=str(payload["receipt_payment_mode"]),
            receipt_payment_subject=str(payload["receipt_payment_subject"]),
            payment_method_id=str(payload["payment_method_id"]),
            capture=bool(payload.get("capture", True)),
        )


@dataclass(frozen=True, slots=True)
class YooKassaRequestFailure:
    kind: str
    retryable: bool
    uncertain: bool
    http_status: int | None = None
    provider_code: str | None = None

    def response_payload(self) -> dict[str, Any]:
        return {
            "error": True,
            "failure_kind": self.kind,
            "retryable": self.retryable,
            "uncertain": self.uncertain,
            "http_status": self.http_status,
            "provider_code": self.provider_code,
        }


def _provider_error_code(exc: ApiError) -> str | None:
    error = getattr(exc, "error", None)
    code = str(getattr(error, "code", "") or "").strip()
    return code or None


def classify_request_exception(exc: Exception) -> YooKassaRequestFailure:
    if isinstance(exc, ApiError):
        http_status = int(getattr(exc, "HTTP_CODE", 0) or 0) or None
        provider_code = _provider_error_code(exc)
        if http_status == 429:
            return YooKassaRequestFailure(
                kind="rate_limited",
                retryable=True,
                uncertain=False,
                http_status=http_status,
                provider_code=provider_code,
            )
        if http_status in {202, 500}:
            return YooKassaRequestFailure(
                kind="provider_response_unknown",
                retryable=True,
                uncertain=True,
                http_status=http_status,
                provider_code=provider_code,
            )
        if http_status is not None and 400 <= http_status < 500:
            return YooKassaRequestFailure(
                kind="request_rejected",
                retryable=False,
                uncertain=False,
                http_status=http_status,
                provider_code=provider_code,
            )
        return YooKassaRequestFailure(
            kind="provider_response_unknown",
            retryable=True,
            uncertain=True,
            http_status=http_status,
            provider_code=provider_code,
        )
    if isinstance(exc, TimeoutError):
        return YooKassaRequestFailure(
            kind="request_timeout",
            retryable=True,
            uncertain=True,
        )
    if isinstance(exc, (ConnectionError, OSError)):
        return YooKassaRequestFailure(
            kind="transport_error",
            retryable=True,
            uncertain=True,
        )
    return YooKassaRequestFailure(
        kind="transport_error",
        retryable=True,
        uncertain=True,
    )


def configuration_failure(kind: str) -> dict[str, Any]:
    return YooKassaRequestFailure(
        kind=kind,
        retryable=False,
        uncertain=False,
    ).response_payload()


def transport_retry_delay(replay_number: int) -> timedelta | None:
    if replay_number < 0 or replay_number >= len(TRANSPORT_RETRY_DELAYS):
        return None
    return TRANSPORT_RETRY_DELAYS[replay_number]


def financial_retry_delay(cancellation_reason: str | None) -> timedelta | None:
    return FINANCIAL_RETRY_DELAYS.get(str(cancellation_reason or "").strip().lower())


def attempt_idempotence_key(base_key: str, attempt_number: int) -> str:
    if attempt_number <= 1:
        return base_key
    source = f"{base_key}|financial-attempt:{attempt_number}"
    return f"yk-auto-{uuid.uuid5(uuid.NAMESPACE_URL, source).hex}"


def existing_auto_renew_result(
    payment: Any,
    *,
    logger: logging.Logger,
) -> RecurringChargeResult | None:
    """Resolve an already-claimed order without creating a second charge."""

    from bot.payment_providers.shared import RecurringChargeResult

    status = str(getattr(payment, "status", "") or "").strip().lower()
    provider_payment_id = (
        str(
            getattr(payment, "yookassa_payment_id", None)
            or getattr(payment, "provider_payment_id", None)
            or ""
        ).strip()
        or None
    )
    if provider_payment_id:
        if status in {
            "pending",
            "pending_yookassa",
            "waiting_for_capture",
            "succeeded_pending_finalization",
            "succeeded_pending_review",
            "succeeded",
        }:
            logger.info(
                "YooKassa auto-renew reusing payment %s (provider id %s, status %s)",
                getattr(payment, "payment_id", None),
                provider_payment_id,
                status,
            )
            return RecurringChargeResult.ok(
                provider_payment_id=provider_payment_id,
                status=status,
            )
        return RecurringChargeResult.failed(f"existing_payment:{status or 'unknown'}")
    if status in {"succeeded_pending_finalization", "succeeded_pending_review", "succeeded"}:
        return RecurringChargeResult.ok(status=status)
    created_at = getattr(payment, "created_at", None)
    if not isinstance(created_at, datetime):
        logger.error(
            "YooKassa auto-renew will not replay payment %s without a creation timestamp",
            getattr(payment, "payment_id", None),
        )
        return RecurringChargeResult.failed("idempotence_window_unknown")
    created_at = (
        created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at.astimezone(UTC)
    )
    if datetime.now(UTC) - created_at >= YOOKASSA_IDEMPOTENCE_WINDOW:
        logger.warning(
            "YooKassa auto-renew will not replay payment %s after the 24h idempotence window",
            getattr(payment, "payment_id", None),
        )
        return RecurringChargeResult.failed("idempotence_window_expired")
    return None


def receipt_customer(
    default_email: str | None,
    *,
    receipt_email: str | None = None,
    receipt_phone: str | None = None,
) -> dict[str, str] | None:
    if receipt_email:
        return {"email": receipt_email}
    if receipt_phone:
        return {"phone": receipt_phone}
    if default_email:
        return {"email": default_email}
    return None
