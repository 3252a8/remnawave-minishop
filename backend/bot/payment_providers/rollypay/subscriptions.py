"""Provider-managed recurring SBP subscriptions for RollyPay."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session

from bot.services.account_roles import is_admin as account_is_admin
from db.dal import payment_dal, rollypay_dal, subscription_dal, user_dal
from db.models import Payment, RollyPaySubscription

from ..shared import (
    CreatePaymentRequest,
    PaymentSuccessRequest,
    build_payment_description,
    build_payment_record_payload,
    finalize_successful_payment,
    make_translator,
    payment_amount_and_currency_match,
    sale_mode_base,
)

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService

logger = logging.getLogger(__name__)

ROLLYPAY_SUBSCRIPTION_PROVIDER = "rollypay_subscription"
ROLLYPAY_PENDING_STATUS = "pending_rollypay"
INTERVAL_BY_MONTHS = {1: "month", 3: "quarter", 12: "year"}
STOPPED_STATES = {"stop", "stopped"}


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def interval_for_months(months: Any) -> str | None:
    try:
        normalized = int(float(months))
    except (TypeError, ValueError):
        return None
    return INTERVAL_BY_MONTHS.get(normalized)


def subscription_context_supported(config: Any, months: Any, sale_mode: str) -> bool:
    from config.subscription_periods import sale_mode_duration_days

    if sale_mode_duration_days(sale_mode) is not None:
        return False

    if getattr(config, "TEST_MODE", False):
        return False
    return sale_mode_base(str(sale_mode or "")) == "subscription" and bool(
        interval_for_months(months)
    )


def subscription_promo_supported(config: Any, months: Any, sale_mode: str, promo: Any) -> bool:
    # RollyPay repeats the authorized amount, while a Core promo belongs to one checkout.
    return False


def subscription_charge_key(subscription_id: str, payment_id: str) -> str:
    return f"rollypay-sub:{subscription_id}:{payment_id}"


class RollyPaySubscriptionRuntime:
    bot: Any
    settings: Any
    config: Any
    i18n: Any
    async_session_factory: Any
    subscription_service: SubscriptionService
    referral_service: ReferralService
    _subscription_plans_cache: tuple[float, list[dict[str, Any]]] | None

    @property
    def configured(self) -> bool:
        raise NotImplementedError

    async def api_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        raise NotImplementedError


class RollyPaySubscriptionMixin(RollyPaySubscriptionRuntime):
    """Recurring API, attribution, settlement, cancellation and state mirroring."""

    @property
    def subscriptions_enabled(self) -> bool:
        return bool(
            not self.config.TEST_MODE
            and (self.config.SUBSCRIPTION_ENABLED or self.config.SUBSCRIPTION_ADMIN_ONLY_ENABLED)
            and self.config.TERMINAL_ID
        )

    @property
    def manages_recurrence(self) -> bool:
        # Keep polling and cancellation alive for existing mandates even when
        # the operator hides the checkout button or enables one-off sandbox mode.
        return bool(self.configured and self.config.TERMINAL_ID)

    async def get_subscription_plans(
        self,
    ) -> tuple[bool, list[dict[str, Any]]]:
        cached = self._subscription_plans_cache
        if cached is not None and cached[0] > time.monotonic():
            return True, list(cached[1])
        success, data = await self.api_request(
            "GET",
            "/subscription-plans",
            params={"terminal_id": str(self.config.TERMINAL_ID)},
        )
        if not success:
            return False, []
        raw = data.get("plans") or data.get("items") or data.get("data") or data
        if isinstance(raw, dict):
            raw = raw.get("plans") or raw.get("items") or []
        plans: list[dict[str, Any]] = (
            [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        )
        if plans:
            self._subscription_plans_cache = (
                time.monotonic() + int(self.config.PLAN_CACHE_SECONDS),
                list(plans),
            )
        return True, plans

    async def choose_subscription_plan(
        self,
        *,
        months: Any,
        amount: float,
    ) -> dict[str, Any] | None:
        interval = interval_for_months(months)
        if interval is None:
            return None
        success, plans = await self.get_subscription_plans()
        if not success:
            return None
        candidates: list[dict[str, Any]] = []
        for plan in plans:
            if str(plan.get("interval") or "").lower() != interval:
                continue
            cap_raw = plan.get("cap_amount_rub")
            if cap_raw is None:
                continue
            try:
                cap = float(cap_raw)
            except (TypeError, ValueError):
                continue
            if float(amount) <= cap + 1e-9 and plan.get("id"):
                candidates.append(plan)
        if not candidates:
            return None
        return max(candidates, key=lambda item: int(item.get("version") or 0))

    async def create_rollypay_subscription(
        self,
        request: CreatePaymentRequest,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.subscriptions_enabled:
            return False, {"message": "subscriptions_disabled"}
        if str(request.currency or "").upper() != "RUB":
            return False, {"message": "subscriptions_require_rub"}
        plan = await self.choose_subscription_plan(
            months=request.months, amount=float(request.amount)
        )
        if plan is None:
            return False, {"message": "subscription_plan_unavailable"}

        local_payment_id = int(request.payment.payment_id)
        payload = {
            "terminal_id": str(self.config.TERMINAL_ID),
            "plan_id": str(plan["id"]),
            "amount": f"{float(request.amount):.2f}",
            "merchant_subscription_ref": f"minishop-{local_payment_id}",
        }
        success, data = await self.api_request(
            "POST",
            "/subscriptions",
            json_body=payload,
            idempotency_key=f"minishop-rollypay-sub-{local_payment_id}",
        )
        if not success:
            return False, data
        subscription_id = str(data.get("id") or data.get("subscription_id") or "").strip()
        payment_url = str(data.get("pay_url") or "").strip()
        if not subscription_id or not payment_url:
            return False, {"message": "invalid_subscription_response", "response": data}

        max_cycles_raw = data.get("max_cycles")
        if max_cycles_raw is None:
            max_cycles_raw = plan.get("max_cycles")
        session = async_object_session(request.payment)
        if session is None:
            await self.stop_remote_subscription(subscription_id)
            return False, {"message": "local_session_unavailable"}
        try:
            await rollypay_dal.create_or_update_subscription(
                session,
                subscription_id=subscription_id,
                anchor_payment_id=local_payment_id,
                user_id=int(request.user_id),
                provider_state=str(data.get("provider_state") or "new").lower(),
                billing_status=str(data.get("billing_status") or "consent_pending").lower(),
                plan_id=str(data.get("plan_id") or plan["id"]),
                plan_code=str(data.get("plan_code") or plan.get("code") or ""),
                plan_version=int(data.get("plan_version") or plan.get("version") or 0),
                interval=str(data.get("interval") or plan.get("interval") or ""),
                max_cycles=int(max_cycles_raw) if max_cycles_raw is not None else None,
                amount=float(request.amount),
                months=int(float(request.months)),
                sale_mode=str(request.sale_mode or "subscription"),
                tariff_key=getattr(request.payment, "tariff_key", None),
                next_charge_at=parse_datetime(data.get("next_charge_at")),
            )
        except Exception:
            logger.exception("RollyPay subscription %s could not be persisted", subscription_id)
            await self.stop_remote_subscription(subscription_id)
            return False, {"message": "subscription_persistence_failed"}
        return True, data

    async def get_remote_subscription(
        self,
        subscription_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        return await self.api_request("GET", f"/subscriptions/{str(subscription_id).strip()}")

    async def stop_remote_subscription(
        self,
        subscription_id: str,
    ) -> bool:
        success, _data = await self.api_request(
            "POST",
            f"/subscriptions/{str(subscription_id).strip()}/stop",
            json_body={},
        )
        return success

    async def try_reuse_pending_subscription(
        self,
        payment: Any,
    ) -> str | None:
        remote_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not remote_id or not payment_url:
            return None
        success, data = await self.get_remote_subscription(remote_id)
        if not success:
            return None
        if str(data.get("billing_status") or "").lower() not in {"consent_pending", "pending"}:
            return None
        return payment_url

    async def cancel_provider_recurrence(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> bool:
        records = await rollypay_dal.list_live_for_user(session, int(user_id))
        all_stopped = True
        for record in records:
            if await self.stop_remote_subscription(str(record.rollypay_subscription_id)):
                await rollypay_dal.update_remote_state(
                    session,
                    record,
                    provider_state="stop",
                    billing_status="stopped",
                )
            else:
                all_stopped = False
        return all_stopped

    async def sync_subscription_state(
        self,
        session: AsyncSession,
        record: RollyPaySubscription,
        remote: dict[str, Any],
    ) -> None:
        provider_state = str(remote.get("provider_state") or record.provider_state).lower()
        billing_status = str(remote.get("billing_status") or record.billing_status).lower()
        await rollypay_dal.update_remote_state(
            session,
            record,
            provider_state=provider_state,
            billing_status=billing_status,
            next_charge_at=parse_datetime(remote.get("next_charge_at")),
        )
        if provider_state in STOPPED_STATES or billing_status == "stopped":
            await self._mirror_local_auto_renew(session, record, enabled=False)

    async def handle_subscription_payment(
        self,
        remote_payment: dict[str, Any],
    ) -> web.Response:
        payment_id = str(remote_payment.get("payment_id") or remote_payment.get("id") or "").strip()
        subscription_id = str(remote_payment.get("subscription_id") or "").strip()
        status = str(remote_payment.get("status") or "").lower()
        if not payment_id or not subscription_id:
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            record = await rollypay_dal.get_subscription(session, subscription_id, for_update=True)
            if record is None:
                await session.rollback()
                await self.stop_remote_subscription(subscription_id)
                return web.Response(status=404, text="subscription_not_found")
            if bool(remote_payment.get("test")) and not await account_is_admin(
                session, int(record.user_id)
            ):
                await session.rollback()
                await self.stop_remote_subscription(subscription_id)
                return web.Response(status=403, text="test_payment_forbidden")
            if not payment_amount_and_currency_match(
                expected_amount=record.amount,
                expected_currency="RUB",
                received_amount=remote_payment.get("amount"),
                received_currency=remote_payment.get("currency")
                or remote_payment.get("payment_currency"),
                places=2,
            ):
                return web.Response(status=400, text="amount_mismatch")

            remote_ok, remote_subscription = await self.get_remote_subscription(subscription_id)
            if remote_ok:
                await self.sync_subscription_state(session, record, remote_subscription)

            if status != "paid":
                if status in {"chargeback", "refunded"}:
                    existing = await payment_dal.get_payment_by_provider_payment_id(
                        session, ROLLYPAY_SUBSCRIPTION_PROVIDER, payment_id
                    )
                    local_status = "reversed" if status == "chargeback" else "refunded"
                    if record.first_provider_payment_id == payment_id:
                        await payment_dal.update_payment_status_by_db_id(
                            session,
                            int(record.anchor_payment_id),
                            local_status,
                        )
                    elif existing is not None:
                        await payment_dal.update_provider_payment_and_status(
                            session,
                            int(existing.payment_id),
                            payment_id,
                            local_status,
                        )
                    if status == "chargeback":
                        await self._stop_record(session, record)
                await session.commit()
                return web.Response(text="ok")

            if record.first_provider_payment_id == payment_id:
                await session.commit()
                return web.Response(text="ok")
            existing = await payment_dal.get_payment_by_provider_payment_id(
                session, ROLLYPAY_SUBSCRIPTION_PROVIDER, payment_id
            )
            if existing is not None and str(existing.status or "").lower() == "succeeded":
                await session.commit()
                return web.Response(text="ok")

            if int(record.charges_count or 0) == 0:
                response = await self._settle_initial_charge(session, record, payment_id)
            else:
                response = await self._settle_renewal_charge(session, record, payment_id)
        return response

    async def _settle_initial_charge(
        self,
        session: AsyncSession,
        record: RollyPaySubscription,
        payment_id: str,
    ) -> web.Response:
        anchor = await payment_dal.get_payment_by_db_id(session, int(record.anchor_payment_id))
        if anchor is None:
            return web.Response(status=404, text="payment_not_found")
        claimed = await payment_dal.claim_payment_finalization(
            session,
            int(anchor.payment_id),
            provider_payment_id=str(record.rollypay_subscription_id),
        )
        if claimed is None:
            return web.Response(text="ok")
        claimed.idempotence_key = subscription_charge_key(
            str(record.rollypay_subscription_id), payment_id
        )
        await rollypay_dal.record_charge(session, record, payment_id=payment_id)
        outcome = await self._finalize_subscription_payment(session, claimed, record)
        if outcome is None:
            return web.Response(status=500, text="processing_error")
        await self._mirror_local_auto_renew_after_commit(
            str(record.rollypay_subscription_id), enabled=True
        )
        return web.Response(text="ok")

    async def _settle_renewal_charge(
        self,
        session: AsyncSession,
        record: RollyPaySubscription,
        payment_id: str,
    ) -> web.Response:
        db_user = await user_dal.get_user_by_id(session, int(record.user_id))
        if db_user is None:
            await session.rollback()
            await self.stop_remote_subscription(str(record.rollypay_subscription_id))
            return web.Response(status=404, text="user_not_found")
        language = str(
            getattr(db_user, "language_code", None) or self.settings.DEFAULT_LANGUAGE or "en"
        )
        sale_mode = str(record.sale_mode or "subscription")
        active = await subscription_dal.get_active_subscription_by_user_id(
            session, int(record.user_id)
        )
        payload = build_payment_record_payload(
            user_id=int(record.user_id),
            amount=float(record.amount),
            currency="RUB",
            status=ROLLYPAY_PENDING_STATUS,
            description=build_payment_description(
                make_translator(self.i18n, language),
                months=int(record.months),
                sale_mode=sale_mode,
            ),
            months=int(record.months),
            provider=ROLLYPAY_SUBSCRIPTION_PROVIDER,
            sale_mode=sale_mode,
            is_auto_renew=True,
            renewal_subscription_id=int(active.subscription_id) if active else None,
        )
        payload.update(
            idempotence_key=subscription_charge_key(
                str(record.rollypay_subscription_id), payment_id
            ),
            provider_payment_id=payment_id,
            tariff_key=record.tariff_key,
        )
        payment, _created = await payment_dal.create_or_get_payment_record_by_idempotence_key(
            session, payload
        )
        claimed = await payment_dal.claim_payment_finalization(
            session, int(payment.payment_id), provider_payment_id=payment_id
        )
        if claimed is None:
            return web.Response(text="ok")
        await rollypay_dal.record_charge(session, record, payment_id=payment_id)
        outcome = await self._finalize_subscription_payment(session, claimed, record)
        return (
            web.Response(text="ok")
            if outcome is not None
            else web.Response(status=500, text="processing_error")
        )

    async def _finalize_subscription_payment(
        self,
        session: AsyncSession,
        payment: Payment,
        record: RollyPaySubscription,
    ) -> Any:
        return await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                subscription_service=self.subscription_service,
                referral_service=self.referral_service,
                payment=payment,
                user_id=int(payment.user_id),
                amount=float(payment.amount),
                currency="RUB",
                sale_mode=str(payment.sale_mode or record.sale_mode or "subscription"),
                months=int(record.months),
                traffic_amount=float(record.months),
                provider_subscription=ROLLYPAY_SUBSCRIPTION_PROVIDER,
                provider_notification=ROLLYPAY_SUBSCRIPTION_PROVIDER,
                log_prefix="RollyPay subscription webhook",
            )
        )

    async def _mirror_local_auto_renew(
        self,
        session: AsyncSession,
        record: RollyPaySubscription,
        *,
        enabled: bool,
    ) -> None:
        subscription = await subscription_dal.get_active_subscription_by_user_id(
            session, int(record.user_id)
        )
        if subscription is None or str(subscription.provider or "").lower() != (
            ROLLYPAY_SUBSCRIPTION_PROVIDER
        ):
            return
        if bool(subscription.auto_renew_enabled) == enabled:
            return
        await subscription_dal.set_auto_renew(
            session,
            int(subscription.subscription_id),
            enabled,
            stop_reason="provider_cancelled" if not enabled else "consent_changed",
        )

    async def _mirror_local_auto_renew_after_commit(
        self,
        subscription_id: str,
        *,
        enabled: bool,
    ) -> None:
        try:
            async with self.async_session_factory() as session:
                record = await rollypay_dal.get_subscription(
                    session, subscription_id, for_update=True
                )
                if record is None:
                    return
                await self._mirror_local_auto_renew(session, record, enabled=enabled)
                await session.commit()
        except Exception:
            logger.exception("RollyPay subscription %s local mirror failed", subscription_id)

    async def _stop_record(
        self,
        session: AsyncSession,
        record: RollyPaySubscription,
    ) -> None:
        await self.stop_remote_subscription(str(record.rollypay_subscription_id))
        await rollypay_dal.update_remote_state(
            session, record, provider_state="stop", billing_status="stopped"
        )
        await self._mirror_local_auto_renew(session, record, enabled=False)


__all__ = [
    "INTERVAL_BY_MONTHS",
    "ROLLYPAY_SUBSCRIPTION_PROVIDER",
    "RollyPaySubscriptionMixin",
    "interval_for_months",
    "subscription_context_supported",
    "subscription_promo_supported",
]
