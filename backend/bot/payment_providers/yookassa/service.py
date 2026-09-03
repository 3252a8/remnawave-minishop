import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, TypeVar

from yookassa import Configuration
from yookassa import Payment as YooKassaPayment
from yookassa.domain.common.confirmation_type import ConfirmationType
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder

from config.settings import Settings
from db.dal import auto_renew_dal, payment_dal

from ..base import (
    normalize_payment_currency_code,
    provider_runtime_enabled,
)
from ..shared import (
    RecurringChargeContext,
    RecurringChargeResult,
    build_payment_record_payload,
    format_decimal_amount,
)
from .auto_renew import (
    TRANSPORT_RETRY_DEADLINE,
    YOOKASSA_IDEMPOTENCE_WINDOW,
    YooKassaProviderRequestSnapshot,
    YooKassaRecurringSnapshot,
    attempt_idempotence_key,
    classify_request_exception,
    configuration_failure,
    existing_auto_renew_result,
    receipt_customer,
    transport_retry_delay,
)
from .config import YooKassaConfig
from .sdk_queries import YooKassaSdkQueryMixin

if TYPE_CHECKING:
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    SubscriptionService = object

logger = logging.getLogger(__name__)
SdkResultT = TypeVar("SdkResultT")


class YooKassaService(YooKassaSdkQueryMixin):
    def __init__(
        self,
        shop_id: str | None,
        secret_key: str | None,
        configured_return_url: str | None,
        bot_username_for_default_return: str | None = None,
        settings_obj: Settings | None = None,
        config: YooKassaConfig | None = None,
        subscription_service: SubscriptionService | None = None,
    ):

        self.settings = settings_obj
        self.config = config or YooKassaConfig()
        self.subscription_service = subscription_service
        self._bot_username_for_default_return = bot_username_for_default_return
        self._configured_return_url_override = configured_return_url
        # (shop_id, secret_key) currently loaded into the global SDK.
        self._sdk_configured_for: tuple[str, str] | None = None

        if not self.configured:
            if not provider_runtime_enabled(self.config):
                logger.warning(
                    "YooKassa is disabled via YOOKASSA_ENABLED flag. Payment functionality will be DISABLED."  # noqa: E501
                )
            else:
                logger.warning(
                    "YooKassa SHOP_ID or SECRET_KEY not configured in settings. "
                    "Payment functionality will be DISABLED."
                )
        logger.info("YooKassa Service effective return_url for payments: %s", self.return_url)

    @property
    def configured(self) -> bool:
        if not (
            provider_runtime_enabled(self.config) and self.config.SHOP_ID and self.config.SECRET_KEY
        ):
            return False
        self._ensure_sdk_configured()
        return self._sdk_configured_for is not None

    def _ensure_sdk_configured(self) -> None:
        """Reconfigure the global YooKassa SDK if shop_id/secret_key changed at runtime."""
        shop_id = self.config.SHOP_ID
        secret_key = self.config.SECRET_KEY
        if not shop_id or not secret_key:
            self._sdk_configured_for = None
            return
        if self._sdk_configured_for == (shop_id, secret_key):
            return
        try:
            Configuration.configure(shop_id, secret_key)
            self._sdk_configured_for = (shop_id, secret_key)
            logger.info("YooKassa SDK (re)configured for shop_id: %s...", shop_id[:5])
        except Exception:
            logger.exception("Failed to configure YooKassa SDK.")
            self._sdk_configured_for = None

    def _sdk_timeout_seconds(self) -> float:
        raw_timeout = getattr(self.settings, "PAYMENT_REQUEST_TIMEOUT_SECONDS", 20.0)
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            return 20.0
        return max(1.0, timeout)

    async def _run_sdk_call(
        self,
        operation: str,
        func: Callable[..., SdkResultT],
        *args: object,
    ) -> SdkResultT:
        timeout = self._sdk_timeout_seconds()
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning(
                "YooKassa SDK call timed out operation=%s timeout_seconds=%.1f",
                operation,
                timeout,
            )
            raise

    @property
    def return_url(self) -> str:
        url = self._configured_return_url_override or self.config.RETURN_URL
        if url:
            return url
        if self._bot_username_for_default_return:
            return f"https://t.me/{self._bot_username_for_default_return}"
        return "https://example.com/payment_error_no_return_url_configured"

    @property
    def recurring_active(self) -> bool:
        """Auto-renew is available only when YooKassa autopayments are switched on."""
        return bool(self.configured and self.config.autopayments_active)

    async def charge_saved_payment_method(
        self, context: RecurringChargeContext
    ) -> RecurringChargeResult:
        """Charge a saved method with durable, bounded recovery when attributable."""
        if not self.recurring_active:
            return RecurringChargeResult.failed("recurring_inactive")
        saved_method_id = getattr(context.saved_method, "provider_payment_method_id", None)
        if not saved_method_id:
            return RecurringChargeResult.failed("missing_saved_method")
        if isinstance(context.renewal_cycle_end, datetime):
            return await self._charge_attributed_auto_renew(context, str(saved_method_id))
        return await self._charge_legacy_auto_renew(context, str(saved_method_id))

    async def _charge_legacy_auto_renew(
        self,
        context: RecurringChargeContext,
        saved_method_id: str,
    ) -> RecurringChargeResult:
        currency = normalize_payment_currency_code(context.currency)
        idempotence_key = str(context.idempotence_key or uuid.uuid4()).strip()
        if not idempotence_key:
            idempotence_key = str(uuid.uuid4())
        payment_payload = build_payment_record_payload(
            user_id=context.user_id,
            amount=float(context.amount),
            currency=currency,
            status="pending_yookassa",
            description=context.description,
            months=context.months,
            duration_days=context.duration_days,
            subscription_terms_snapshot=context.subscription_terms_snapshot,
            provider="yookassa",
            sale_mode=context.sale_mode,
            hwid_quote=dict(context.hwid_quote or {}) or None,
            is_auto_renew=True,
            renewal_subscription_id=context.subscription_id,
            renewal_cycle_end=context.renewal_cycle_end,
            entitlement_context_snapshot=context.entitlement_context_snapshot,
            checkout_bundle_snapshot=context.checkout_bundle_snapshot,
        )
        payment_payload["idempotence_key"] = idempotence_key
        payment: Any | None = None
        try:
            payment, created = await payment_dal.create_or_get_payment_record_by_idempotence_key(
                context.session,
                payment_payload,
            )
            if created:
                await context.session.commit()
        except Exception as exc:
            await context.session.rollback()
            logger.exception("YooKassa auto-renew failed to create local payment record")
            return RecurringChargeResult.failed(
                str(exc),
                payment_db_id=getattr(payment, "payment_id", None),
            )

        if not created:
            existing_result = existing_auto_renew_result(payment, logger=logger)
            if existing_result is not None:
                return existing_result

        metadata = dict(context.metadata)
        metadata["payment_db_id"] = str(payment.payment_id)
        try:
            resp = await self.create_payment(
                amount=float(context.amount),
                currency=currency,
                description=context.description,
                metadata=metadata,
                payment_method_id=saved_method_id,
                save_payment_method=False,
                capture=True,
                idempotence_key=idempotence_key,
            )
        except Exception as exc:
            logger.exception("YooKassa auto-renew charge failed before API response")
            await self._mark_auto_renew_payment_failed(context.session, payment.payment_id)
            return RecurringChargeResult.failed(str(exc))

        status = (resp or {}).get("status")
        if not resp or status not in {"pending", "waiting_for_capture", "succeeded"}:
            provider_payment_id = str((resp or {}).get("id") or "").strip() or None
            await self._mark_auto_renew_payment_failed(
                context.session,
                payment.payment_id,
                yookassa_payment_id=provider_payment_id,
            )
            return RecurringChargeResult.failed(
                f"unexpected_status:{status}",
                provider_payment_id=provider_payment_id,
                payment_db_id=payment.payment_id,
            )

        provider_payment_id = str(resp.get("id") or "").strip() or None
        if provider_payment_id:
            try:
                await payment_dal.update_payment_status_by_db_id(
                    context.session,
                    payment.payment_id,
                    "pending_yookassa",
                    provider_payment_id,
                )
                await context.session.commit()
            except Exception:
                await context.session.rollback()
                logger.exception(
                    "YooKassa auto-renew failed to store provider payment id %s",
                    provider_payment_id,
                )
        return RecurringChargeResult.ok(
            provider_payment_id=provider_payment_id,
            payment_db_id=payment.payment_id,
            status=status,
        )

    async def _charge_attributed_auto_renew(
        self,
        context: RecurringChargeContext,
        saved_method_id: str,
    ) -> RecurringChargeResult:
        cycle_end = context.renewal_cycle_end
        if not isinstance(cycle_end, datetime):
            return RecurringChargeResult.failed("missing_renewal_cycle")
        if cycle_end.tzinfo is None:
            cycle_end = cycle_end.replace(tzinfo=UTC)
        else:
            cycle_end = cycle_end.astimezone(UTC)

        currency = normalize_payment_currency_code(context.currency)
        base_key = str(context.idempotence_key or "").strip()
        if not base_key:
            return RecurringChargeResult.failed("missing_idempotence_key")
        consent_version = max(0, int(context.consent_version or 0))
        attempt_number = max(1, int(context.attempt_number or 1))
        payment_method_db_id = (
            int(context.payment_method_db_id) if context.payment_method_db_id is not None else None
        )
        quote_snapshot = YooKassaRecurringSnapshot(
            amount=float(context.amount),
            currency=currency,
            months=int(context.months),
            sale_mode=str(context.sale_mode),
            description=str(context.description),
            metadata={str(key): str(value) for key, value in context.metadata.items()},
            hwid_quote=dict(context.hwid_quote or {}) or None,
            entitlement_context_snapshot=context.entitlement_context_snapshot,
            checkout_bundle_snapshot=context.checkout_bundle_snapshot,
        )
        quote_snapshot_json = quote_snapshot.to_json()

        try:
            if context.auto_renew_cycle_id is not None:
                cycle = await auto_renew_dal.get_cycle(
                    context.session,
                    int(context.auto_renew_cycle_id),
                    fresh=True,
                )
                created_cycle = False
            else:
                cycle, created_cycle = await auto_renew_dal.create_or_get_cycle(
                    context.session,
                    {
                        "subscription_id": int(context.subscription_id),
                        "user_id": int(context.user_id),
                        "provider": "yookassa",
                        "cycle_anchor": auto_renew_dal.cycle_anchor_utc(cycle_end),
                        "renewal_cycle_end": cycle_end,
                        "state": "scheduled",
                        "base_idempotence_key": base_key,
                        "consent_version": consent_version,
                        "payment_method_id": payment_method_db_id,
                        "payment_method_provider_id": saved_method_id,
                        "request_snapshot": quote_snapshot_json,
                    },
                )
            if cycle is None:
                return RecurringChargeResult.failed("auto_renew_cycle_missing")
            if created_cycle:
                await context.session.commit()
        except Exception as exc:
            await context.session.rollback()
            logger.exception("Failed to claim durable auto-renew cycle")
            return RecurringChargeResult.failed(
                str(exc),
                failure_kind="local_cycle_error",
            )

        cycle_id = int(cycle.cycle_id)
        immutable_cycle_values = {
            "subscription_id": (int(cycle.subscription_id), int(context.subscription_id)),
            "user_id": (int(cycle.user_id), int(context.user_id)),
            "provider": (str(cycle.provider), "yookassa"),
            "base_idempotence_key": (str(cycle.base_idempotence_key), base_key),
            "consent_version": (int(cycle.consent_version or 0), consent_version),
            "payment_method_id": (
                (int(cycle.payment_method_id) if cycle.payment_method_id is not None else None),
                payment_method_db_id,
            ),
            "payment_method_provider_id": (
                str(cycle.payment_method_provider_id),
                saved_method_id,
            ),
            "request_snapshot": (str(cycle.request_snapshot), quote_snapshot_json),
        }
        mismatches = [
            field
            for field, (stored, expected) in immutable_cycle_values.items()
            if stored != expected
        ]
        if mismatches:
            await auto_renew_dal.stop_cycle(
                context.session,
                cycle_id,
                "immutable_context_changed",
            )
            await context.session.commit()
            logger.error(
                "Auto-renew cycle %s immutable fields changed: %s",
                cycle_id,
                ", ".join(mismatches),
            )
            return RecurringChargeResult.failed("immutable_context_changed")

        cycle_state = str(cycle.state or "").strip().lower()
        if cycle_state == "succeeded":
            return RecurringChargeResult.ok(status="succeeded")
        if cycle_state == "stopped":
            return RecurringChargeResult.failed(
                f"cycle_stopped:{cycle.stopped_reason or 'unknown'}"
            )
        current_payment_id = getattr(cycle, "current_payment_id", None)
        if current_payment_id:
            if context.retry_kind != "financial":
                current_payment = await payment_dal.get_payment_by_db_id(
                    context.session,
                    int(current_payment_id),
                    fresh=True,
                )
                if current_payment is not None:
                    existing_result = existing_auto_renew_result(
                        current_payment,
                        logger=logger,
                    )
                    if existing_result is not None:
                        return RecurringChargeResult(
                            initiated=existing_result.initiated,
                            provider_payment_id=existing_result.provider_payment_id,
                            payment_db_id=int(current_payment.payment_id),
                            status=existing_result.status,
                            message=existing_result.message,
                        )
            if context.retry_kind not in {"transport", "financial"}:
                return RecurringChargeResult.failed(
                    "retry_owned_by_worker",
                    payment_db_id=int(current_payment_id),
                    retryable=cycle_state in auto_renew_dal.RETRYABLE_CYCLE_STATES,
                )
        if context.retry_kind == "financial":
            attempt_number = int(cycle.financial_attempts or 0) + 1
        elif context.retry_kind == "transport":
            attempt_number = max(1, int(cycle.financial_attempts or attempt_number))

        max_financial_attempts = min(
            2,
            max(
                1,
                int(getattr(self.settings, "AUTO_RENEW_MAX_FINANCIAL_ATTEMPTS", 2)),
            ),
        )
        if attempt_number > max_financial_attempts:
            await auto_renew_dal.stop_cycle(context.session, cycle_id, "financial_attempt_cap")
            await context.session.commit()
            return RecurringChargeResult.failed("financial_attempt_cap")

        transport_replays = int(cycle.transport_replays or 0)
        max_transport_replays = max(
            0,
            int(getattr(self.settings, "AUTO_RENEW_MAX_TRANSPORT_REPLAYS", 4)),
        )
        if context.retry_kind == "transport":
            if transport_replays >= max_transport_replays:
                await auto_renew_dal.stop_cycle(
                    context.session,
                    cycle_id,
                    "transport_replay_cap",
                )
                await context.session.commit()
                return RecurringChargeResult.failed("transport_replay_cap")
            transport_replays += 1

        idempotence_key = attempt_idempotence_key(base_key, attempt_number)
        payment_payload = build_payment_record_payload(
            user_id=context.user_id,
            amount=float(context.amount),
            currency=currency,
            status="pending_yookassa",
            description=context.description,
            months=context.months,
            duration_days=context.duration_days,
            subscription_terms_snapshot=context.subscription_terms_snapshot,
            provider="yookassa",
            sale_mode=context.sale_mode,
            hwid_quote=dict(context.hwid_quote or {}) or None,
            is_auto_renew=True,
            renewal_subscription_id=context.subscription_id,
            renewal_cycle_end=cycle_end,
            entitlement_context_snapshot=context.entitlement_context_snapshot,
            checkout_bundle_snapshot=context.checkout_bundle_snapshot,
        )
        payment_payload.update(
            {
                "idempotence_key": idempotence_key,
                "auto_renew_cycle_id": cycle_id,
                "renewal_attempt_number": attempt_number,
                "renewal_consent_version": consent_version,
                "renewal_payment_method_id": payment_method_db_id,
            }
        )
        payment: Any | None = None
        try:
            (
                payment,
                created_payment,
            ) = await payment_dal.create_or_get_payment_record_by_idempotence_key(
                context.session,
                payment_payload,
            )
            if created_payment:
                await context.session.commit()
        except Exception as exc:
            await context.session.rollback()
            logger.exception("Failed to claim local auto-renew payment")
            return RecurringChargeResult.failed(
                str(exc),
                payment_db_id=getattr(payment, "payment_id", None),
                failure_kind="local_payment_error",
            )

        if not created_payment:
            existing_result = existing_auto_renew_result(payment, logger=logger)
            if existing_result is not None:
                return RecurringChargeResult(
                    initiated=existing_result.initiated,
                    provider_payment_id=existing_result.provider_payment_id,
                    payment_db_id=int(payment.payment_id),
                    status=existing_result.status,
                    message=existing_result.message,
                )

        metadata = {str(key): str(value) for key, value in context.metadata.items()}
        metadata["payment_db_id"] = str(payment.payment_id)
        receipt_contact = receipt_customer(self.config.DEFAULT_RECEIPT_EMAIL)
        if receipt_contact is None:
            await auto_renew_dal.mark_request_failure(
                context.session,
                payment_id=int(payment.payment_id),
                status="failed_creation",
                failure_kind="receipt_contact_missing",
                http_status=None,
                provider_code=None,
            )
            await auto_renew_dal.stop_cycle(
                context.session,
                cycle_id,
                "receipt_contact_missing",
            )
            await context.session.commit()
            return RecurringChargeResult.failed(
                "receipt_contact_missing",
                payment_db_id=int(payment.payment_id),
                failure_kind="receipt_contact_missing",
            )
        expected_provider_snapshot = YooKassaProviderRequestSnapshot(
            merchant_id=str(self.config.SHOP_ID),
            amount=float(context.amount),
            currency=currency,
            description=context.description,
            metadata=metadata,
            receipt_customer=receipt_contact,
            receipt_vat_code=str(self.config.VAT_CODE),
            receipt_payment_mode=self.config.yk_receipt_payment_mode,
            receipt_payment_subject=self.config.yk_receipt_payment_subject,
            payment_method_id=saved_method_id,
        )
        expected_provider_snapshot = YooKassaProviderRequestSnapshot.from_json(
            expected_provider_snapshot.to_json()
        )
        stored_provider_snapshot = getattr(payment, "provider_request_snapshot", None)
        if stored_provider_snapshot:
            try:
                provider_snapshot = YooKassaProviderRequestSnapshot.from_json(
                    str(stored_provider_snapshot)
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                await auto_renew_dal.stop_cycle(
                    context.session,
                    cycle_id,
                    "provider_snapshot_invalid",
                )
                await context.session.commit()
                return RecurringChargeResult.failed("provider_snapshot_invalid")
            if provider_snapshot != expected_provider_snapshot:
                await auto_renew_dal.stop_cycle(
                    context.session,
                    cycle_id,
                    "provider_snapshot_changed",
                )
                await context.session.commit()
                return RecurringChargeResult.failed("provider_snapshot_changed")
        else:
            provider_snapshot = expected_provider_snapshot

        now = datetime.now(UTC)
        created_at = getattr(payment, "created_at", None)
        if not isinstance(created_at, datetime):
            created_at = now
        elif created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        else:
            created_at = created_at.astimezone(UTC)
        deadline = min(
            created_at + TRANSPORT_RETRY_DEADLINE,
            created_at + YOOKASSA_IDEMPOTENCE_WINDOW,
        )
        delay = transport_retry_delay(transport_replays)
        fallback_retry_at = min(now + (delay or TRANSPORT_RETRY_DEADLINE), deadline)
        if now >= deadline:
            await auto_renew_dal.stop_cycle(
                context.session,
                cycle_id,
                "transport_retry_deadline",
            )
            await context.session.commit()
            return RecurringChargeResult.failed("transport_retry_deadline")

        sdk_timeout = self._sdk_timeout_seconds()
        try:
            prepared = await auto_renew_dal.prepare_payment_dispatch(
                context.session,
                payment_id=int(payment.payment_id),
                request_snapshot=provider_snapshot.to_json(),
                cycle_id=cycle_id,
                attempt_number=attempt_number,
                consent_version=consent_version,
                payment_method_id=payment_method_db_id,
            )
            if prepared is None or str(prepared.provider_request_snapshot) != (
                provider_snapshot.to_json()
            ):
                raise ValueError("Immutable provider request snapshot conflict")
            await auto_renew_dal.record_payment_dispatch(
                context.session,
                cycle_id=cycle_id,
                payment_id=int(payment.payment_id),
                attempt_number=attempt_number,
                transport_replays=transport_replays,
                fallback_retry_at=fallback_retry_at,
                lease_expires_at=now + timedelta(seconds=max(30.0, sdk_timeout + 10.0)),
            )
            await context.session.commit()
        except Exception as exc:
            await context.session.rollback()
            logger.exception("Failed to persist auto-renew dispatch intent")
            return RecurringChargeResult.failed(
                str(exc),
                payment_db_id=int(payment.payment_id),
                failure_kind="local_dispatch_error",
            )

        if not await auto_renew_dal.validate_dispatch_context_for_update(
            context.session,
            cycle_id,
        ):
            await auto_renew_dal.mark_request_failure(
                context.session,
                payment_id=int(payment.payment_id),
                status="failed_creation",
                failure_kind="consent_or_method_changed",
                http_status=None,
                provider_code=None,
            )
            await auto_renew_dal.stop_cycle(
                context.session,
                cycle_id,
                "consent_or_method_changed",
            )
            await context.session.commit()
            return RecurringChargeResult.failed(
                "consent_or_method_changed",
                payment_db_id=int(payment.payment_id),
                failure_kind="consent_or_method_changed",
            )

        resp = await self.create_payment(
            amount=provider_snapshot.amount,
            currency=provider_snapshot.currency,
            description=provider_snapshot.description,
            metadata=provider_snapshot.metadata,
            payment_method_id=provider_snapshot.payment_method_id,
            save_payment_method=False,
            capture=provider_snapshot.capture,
            idempotence_key=idempotence_key,
            receipt_customer_override=provider_snapshot.receipt_customer,
            receipt_vat_code=provider_snapshot.receipt_vat_code,
            receipt_payment_mode=provider_snapshot.receipt_payment_mode,
            receipt_payment_subject=provider_snapshot.receipt_payment_subject,
        )
        provider_payment_id = str((resp or {}).get("id") or "").strip() or None
        status = str((resp or {}).get("status") or "").strip().lower() or None
        if provider_payment_id:
            try:
                await payment_dal.update_payment_status_by_db_id(
                    context.session,
                    int(payment.payment_id),
                    "pending_yookassa",
                    provider_payment_id,
                )
                await auto_renew_dal.mark_waiting_provider(context.session, cycle_id)
                await context.session.commit()
            except Exception:
                await context.session.rollback()
                logger.exception(
                    "Failed to persist YooKassa auto-renew provider id %s",
                    provider_payment_id,
                )
            return RecurringChargeResult.ok(
                provider_payment_id=provider_payment_id,
                payment_db_id=int(payment.payment_id),
                status=status,
            )

        failure_kind = str((resp or {}).get("failure_kind") or "missing_provider_id")
        retryable = bool((resp or {}).get("retryable", True))
        http_status = (resp or {}).get("http_status")
        provider_code = str((resp or {}).get("provider_code") or "").strip() or None
        retry_enabled = bool(getattr(self.settings, "AUTO_RENEW_RETRY_ENABLED", False))
        can_retry = (
            retry_enabled
            and retryable
            and delay is not None
            and transport_replays < max_transport_replays
        )
        await auto_renew_dal.mark_request_failure(
            context.session,
            payment_id=int(payment.payment_id),
            status="creation_unknown" if retryable else "failed_creation",
            failure_kind=failure_kind,
            http_status=int(http_status) if http_status is not None else None,
            provider_code=provider_code,
        )
        if can_retry:
            await auto_renew_dal.schedule_transport_retry(
                context.session,
                cycle_id=cycle_id,
                next_attempt_at=fallback_retry_at,
                failure_kind=failure_kind,
                http_status=int(http_status) if http_status is not None else None,
                provider_code=provider_code,
                transport_replays=transport_replays,
            )
        else:
            await auto_renew_dal.stop_cycle(
                context.session,
                cycle_id,
                "transport_retry_disabled" if retryable else failure_kind,
            )
        await context.session.commit()
        return RecurringChargeResult.failed(
            failure_kind,
            payment_db_id=int(payment.payment_id),
            retryable=can_retry,
            failure_kind=failure_kind,
            http_status=int(http_status) if http_status is not None else None,
            provider_code=provider_code,
        )

    async def _mark_auto_renew_payment_failed(
        self,
        session: Any,
        payment_db_id: int,
        *,
        yookassa_payment_id: str | None = None,
    ) -> None:
        try:
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id,
                "failed_creation",
                yookassa_payment_id,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "YooKassa auto-renew failed to mark payment %s as failed_creation",
                payment_db_id,
            )

    async def create_payment(
        self,
        amount: float,
        currency: str,
        description: str,
        metadata: dict[str, Any],
        receipt_email: str | None = None,
        receipt_phone: str | None = None,
        save_payment_method: bool = False,
        payment_method_id: str | None = None,
        capture: bool = True,
        bind_only: bool = False,
        idempotence_key: str | None = None,
        receipt_customer_override: dict[str, str] | None = None,
        receipt_vat_code: str | None = None,
        receipt_payment_mode: str | None = None,
        receipt_payment_subject: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.configured:
            logger.error("YooKassa is not configured. Cannot create payment.")
            return configuration_failure("provider_not_configured")

        if not self.settings:
            logger.error(
                "YooKassaService: Settings object not available. Cannot create payment with receipt details."  # noqa: E501
            )
            return configuration_failure("settings_unavailable")

        currency = normalize_payment_currency_code(currency)
        if currency != "RUB":
            logger.error("YooKassa currency %s is not supported by this integration", currency)
            return configuration_failure("unsupported_currency")

        customer_contact_for_receipt = (
            dict(receipt_customer_override)
            if receipt_customer_override is not None
            else receipt_customer(
                self.config.DEFAULT_RECEIPT_EMAIL,
                receipt_email=receipt_email,
                receipt_phone=receipt_phone,
            )
        )
        if not customer_contact_for_receipt:
            logger.error(
                "CRITICAL: No email/phone for YooKassa receipt provided and YOOKASSA_DEFAULT_RECEIPT_EMAIL is not set."  # noqa: E501
            )
            return configuration_failure("receipt_contact_missing")

        try:
            # For binding cards only, do not capture and set the documented
            # minimum amount before rendering both the payment and receipt.
            if bind_only:
                capture = False
                amount = max(amount, 1.00)
            invoice_amount = str(format_decimal_amount(amount))
            builder = PaymentRequestBuilder()
            builder.set_amount({"value": invoice_amount, "currency": currency.upper()})
            builder.set_capture(capture)
            if not payment_method_id:
                builder.set_confirmation(
                    {"type": ConfirmationType.REDIRECT, "return_url": self.return_url}
                )
            builder.set_description(description)
            builder.set_metadata(metadata)
            if save_payment_method:
                builder.set_save_payment_method(True)
            elif not payment_method_id:
                builder.set_save_payment_method(False)
            if payment_method_id:
                builder.set_payment_method_id(payment_method_id)

            receipt_items_list: list[dict[str, Any]] = [
                {
                    "description": description[:128],
                    "quantity": "1.00",
                    "amount": {"value": invoice_amount, "currency": currency.upper()},
                    "vat_code": receipt_vat_code or str(self.config.VAT_CODE),
                    "payment_mode": (receipt_payment_mode or self.config.yk_receipt_payment_mode),
                    "payment_subject": (
                        receipt_payment_subject or self.config.yk_receipt_payment_subject
                    ),
                }
            ]

            receipt_data_dict: dict[str, Any] = {
                "customer": customer_contact_for_receipt,
                "items": receipt_items_list,
            }

            builder.set_receipt(receipt_data_dict)

            idempotence_key = str(idempotence_key or uuid.uuid4()).strip()
            if not idempotence_key:
                idempotence_key = str(uuid.uuid4())
            payment_request = builder.build()

            logger.info(
                "Creating YooKassa payment (Idempotence-Key: %s). Amount: %s %s. Metadata: %s. "
                "Receipt: %s",
                idempotence_key,
                amount,
                currency,
                metadata,
                receipt_data_dict,
            )

            response = await self._run_sdk_call(
                "payment.create",
                YooKassaPayment.create,
                payment_request,
                idempotence_key,
            )

            logger.info(
                "YooKassa Payment.create response: ID=%s, Status=%s, Paid=%s",
                response.id,
                response.status,
                response.paid,
            )

            return {
                "id": response.id,
                "confirmation_url": response.confirmation.confirmation_url
                if response.confirmation
                else None,
                "status": response.status,
                "metadata": response.metadata,
                "amount_value": float(response.amount.value),
                "amount_currency": response.amount.currency,
                "idempotence_key_used": idempotence_key,
                "paid": response.paid,
                "refundable": response.refundable,
                "created_at": response.created_at.isoformat()
                if hasattr(response.created_at, "isoformat")
                else str(response.created_at),
                "description_from_yk": response.description,
                "test_mode": response.test if hasattr(response, "test") else None,
                "payment_method": getattr(response, "payment_method", None),
            }
        except Exception as exc:
            logger.exception("YooKassa payment creation failed.")
            return classify_request_exception(exc).response_payload()
