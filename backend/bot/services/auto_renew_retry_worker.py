from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from bot.infra.auto_renew import auto_renew_user_lock_name
from bot.infra.redis import redis_lock
from bot.payment_providers.shared import RecurringChargeContext, RecurringRequestSnapshot
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.dal import auto_renew_dal, subscription_dal, user_billing_dal

logger = logging.getLogger(__name__)

AUTO_RENEW_RETRY_LOCK = "auto-renew-retry-worker"
DEFAULT_TICK_SECONDS = 60
DEFAULT_BATCH_SIZE = 50
DEFAULT_SCHEDULER_LEAD_HOURS = 24


class AutoRenewRetryWorker:
    """Recover one renewal safely without turning provider errors into charge loops."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker,
        subscription_service: SubscriptionService,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.subscription_service = subscription_service
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        if not self._active_provider_keys():
            logger.info("Auto-renew retry worker disabled: recurring providers are unavailable")
            return
        while not self._stopped.is_set():
            try:
                async with redis_lock(
                    self.settings,
                    AUTO_RENEW_RETRY_LOCK,
                    ttl_seconds=max(60, self._tick_seconds() * 2),
                ) as acquired:
                    if acquired:
                        started = time.monotonic()
                        await self.tick()
                        logger.info(
                            "metric worker_tick_duration_seconds=%.3f worker=auto_renew_retry",
                            time.monotonic() - started,
                        )
            except Exception:
                logger.exception("Auto-renew retry worker tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._tick_seconds())

    def stop(self) -> None:
        self._stopped.set()

    def _tick_seconds(self) -> int:
        return max(
            1,
            int(
                getattr(
                    self.settings,
                    "AUTO_RENEW_WORKER_TICK_SECONDS",
                    DEFAULT_TICK_SECONDS,
                )
            ),
        )

    def _batch_size(self) -> int:
        return max(
            1,
            int(
                getattr(
                    self.settings,
                    "AUTO_RENEW_WORKER_BATCH_SIZE",
                    DEFAULT_BATCH_SIZE,
                )
            ),
        )

    def _lease_seconds(self) -> int:
        request_timeout = float(getattr(self.settings, "PAYMENT_REQUEST_TIMEOUT_SECONDS", 20.0))
        return max(60, int(request_timeout) + 30)

    async def tick(self) -> None:
        if bool(getattr(self.settings, "AUTO_RENEW_RETRY_ENABLED", False)):
            await self._process_due_retries()
        if bool(getattr(self.settings, "AUTO_RENEW_SCHEDULER_ENABLED", False)):
            await self._process_due_subscriptions()

    async def _process_due_retries(self) -> None:
        async with self.session_factory() as session:
            candidates = await auto_renew_dal.list_due_cycles(
                session,
                limit=self._batch_size(),
            )
        for candidate in candidates:
            try:
                await self._claim_and_retry(candidate.cycle_id, candidate.user_id)
            except Exception:
                logger.exception("Auto-renew cycle %s retry failed", candidate.cycle_id)

    async def _claim_and_retry(self, cycle_id: int, user_id: int) -> None:
        async with self.session_factory() as session:
            cycle = await auto_renew_dal.claim_due_cycle(
                session,
                cycle_id,
                lease_seconds=self._lease_seconds(),
            )
            if cycle is None:
                await session.rollback()
                return
            await session.commit()

        async with redis_lock(
            self.settings,
            auto_renew_user_lock_name(user_id),
            ttl_seconds=self._lease_seconds(),
        ) as acquired:
            if not acquired:
                await self._defer_cycle(cycle_id, seconds=30)
                return
            await self._retry_cycle(cycle_id)

    async def _retry_cycle(self, cycle_id: int) -> None:
        async with self.session_factory() as session:
            cycle = await auto_renew_dal.get_cycle(session, cycle_id, fresh=True)
            if cycle is None or str(cycle.state) not in auto_renew_dal.RETRYABLE_CYCLE_STATES:
                return
            sub = await subscription_dal.get_subscription_by_id_for_update(
                session,
                int(cycle.subscription_id),
            )
            stop_reason = self._preflight_stop_reason(cycle, sub)
            if stop_reason:
                await auto_renew_dal.stop_cycle(session, cycle_id, stop_reason)
                await session.commit()
                return
            payment_method = await user_billing_dal.get_user_default_payment_method(
                session,
                int(cycle.user_id),
                provider=str(cycle.provider),
            )
            if (
                payment_method is None
                or str(payment_method.provider_payment_method_id)
                != str(cycle.payment_method_provider_id)
                or (
                    cycle.payment_method_id is not None
                    and int(payment_method.method_id) != int(cycle.payment_method_id)
                )
            ):
                await auto_renew_dal.stop_cycle(
                    session,
                    cycle_id,
                    "payment_method_changed",
                )
                await session.commit()
                return
            if await auto_renew_dal.cycle_has_blocking_payment(
                session,
                cycle_id,
                exclude_payment_id=(
                    int(cycle.current_payment_id) if cycle.current_payment_id is not None else None
                ),
            ):
                await auto_renew_dal.stop_cycle(
                    session,
                    cycle_id,
                    "another_payment_is_active",
                )
                await session.commit()
                return
            if bool(getattr(self.settings, "AUTO_RENEW_RETRY_DRY_RUN", True)):
                logger.warning(
                    "Auto-renew retry dry-run cycle=%s user=%s state=%s",
                    cycle_id,
                    cycle.user_id,
                    cycle.state,
                )
                await auto_renew_dal.defer_cycle(
                    session,
                    cycle_id,
                    next_attempt_at=datetime.now(UTC)
                    + timedelta(seconds=max(300, self._tick_seconds())),
                )
                await session.commit()
                return

            provider = str(cycle.provider or "").strip().lower()
            recurring_service = self.subscription_service.recurring_service_for(provider)
            if recurring_service is None or not bool(
                getattr(recurring_service, "recurring_active", False)
            ):
                await auto_renew_dal.stop_cycle(session, cycle_id, "provider_unavailable")
                await session.commit()
                return
            snapshot = RecurringRequestSnapshot.from_json(str(cycle.request_snapshot))
            retry_kind = "financial" if str(cycle.state) == "financial_retry" else "transport"
            result = await recurring_service.charge_saved_payment_method(
                RecurringChargeContext(
                    session=session,
                    user_id=int(cycle.user_id),
                    subscription_id=int(cycle.subscription_id),
                    saved_method=payment_method,
                    amount=snapshot.amount,
                    currency=snapshot.currency,
                    months=snapshot.months,
                    duration_days=snapshot.duration_days,
                    subscription_terms_snapshot=snapshot.subscription_terms_snapshot,
                    sale_mode=snapshot.sale_mode,
                    description=snapshot.description,
                    metadata=snapshot.metadata,
                    hwid_quote=snapshot.hwid_quote,
                    entitlement_context_snapshot=snapshot.entitlement_context_snapshot,
                    checkout_bundle_snapshot=snapshot.checkout_bundle_snapshot,
                    idempotence_key=str(cycle.base_idempotence_key),
                    renewal_cycle_end=cycle.renewal_cycle_end,
                    consent_version=int(cycle.consent_version or 0),
                    payment_method_db_id=(
                        int(cycle.payment_method_id)
                        if cycle.payment_method_id is not None
                        else None
                    ),
                    auto_renew_cycle_id=cycle_id,
                    attempt_number=max(1, int(cycle.financial_attempts or 1)),
                    retry_kind=retry_kind,
                )
            )
            logger.info(
                "Auto-renew retry completed cycle=%s initiated=%s kind=%s message=%s",
                cycle_id,
                result.initiated,
                retry_kind,
                result.message,
            )

    def _preflight_stop_reason(self, cycle: object, sub: object | None) -> str | None:
        if sub is None:
            return "subscription_missing"
        if not bool(getattr(sub, "is_active", False)):
            return "subscription_inactive"
        if not bool(getattr(sub, "auto_renew_enabled", False)):
            return "consent_disabled"
        if (
            str(getattr(sub, "provider", "") or "").strip().lower()
            != str(getattr(cycle, "provider", "") or "").strip().lower()
        ):
            return "provider_changed"
        if int(getattr(sub, "auto_renew_consent_version", 0) or 0) != int(
            getattr(cycle, "consent_version", 0) or 0
        ):
            return "consent_version_changed"
        end_date = getattr(sub, "end_date", None)
        if not isinstance(end_date, datetime):
            return "subscription_end_missing"
        end_date = (
            end_date.replace(tzinfo=UTC) if end_date.tzinfo is None else end_date.astimezone(UTC)
        )
        cycle_end = getattr(cycle, "renewal_cycle_end", None)
        if not isinstance(cycle_end, datetime):
            return "cycle_end_missing"
        cycle_end = (
            cycle_end.replace(tzinfo=UTC) if cycle_end.tzinfo is None else cycle_end.astimezone(UTC)
        )
        if end_date.date() != cycle_end.date():
            return "renewal_cycle_changed"
        cutoff = cycle_end + timedelta(
            hours=max(
                0,
                int(getattr(self.settings, "AUTO_RENEW_RETRY_GRACE_HOURS", 0)),
            )
        )
        if datetime.now(UTC) > cutoff:
            return "renewal_cutoff_expired"
        return None

    async def _defer_cycle(self, cycle_id: int, *, seconds: int) -> None:
        async with self.session_factory() as session:
            await auto_renew_dal.defer_cycle(
                session,
                cycle_id,
                next_attempt_at=datetime.now(UTC) + timedelta(seconds=max(1, seconds)),
            )
            await session.commit()

    async def _process_due_subscriptions(self) -> None:
        lead_hours = max(
            1,
            int(
                getattr(
                    self.settings,
                    "AUTO_RENEW_SCHEDULER_LEAD_HOURS",
                    DEFAULT_SCHEDULER_LEAD_HOURS,
                )
            ),
        )
        async with self.session_factory() as session:
            candidates = await auto_renew_dal.list_due_subscriptions(
                session,
                providers=self._active_provider_keys(),
                hours_ahead=lead_hours,
                limit=self._batch_size(),
            )
        for candidate in candidates:
            async with redis_lock(
                self.settings,
                auto_renew_user_lock_name(candidate.user_id),
                ttl_seconds=self._lease_seconds(),
            ) as acquired:
                if not acquired:
                    continue
                async with self.session_factory() as session:
                    sub = await subscription_dal.get_subscription_by_id_for_update(
                        session,
                        candidate.subscription_id,
                    )
                    if sub is None:
                        continue
                    if bool(getattr(self.settings, "AUTO_RENEW_RETRY_DRY_RUN", True)):
                        logger.warning(
                            "Auto-renew scheduler dry-run subscription=%s user=%s",
                            candidate.subscription_id,
                            candidate.user_id,
                        )
                        await session.rollback()
                        continue
                    await self.subscription_service.charge_subscription_renewal(
                        session,
                        sub,
                        renewal_cycle_end=sub.end_date,
                    )
                    await session.commit()

    def _active_provider_keys(self) -> tuple[str, ...]:
        services = getattr(self.subscription_service, "recurring_provider_services", {}) or {}
        return tuple(
            sorted(
                str(provider).strip().lower()
                for provider, service in services.items()
                if str(provider).strip() and bool(getattr(service, "recurring_active", False))
            )
        )
