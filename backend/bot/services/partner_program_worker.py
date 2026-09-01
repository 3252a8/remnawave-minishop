# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; the recovery pass intentionally mutates loaded ORM instances.
# mypy: disable-error-code="assignment"

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from bot.infra.redis import redis_lock
from bot.services.partner_checkout_balance import (
    TERMINAL_CHECKOUT_STATUSES,
    PartnerCheckoutBalanceService,
)
from bot.services.partner_commission_service import PartnerCommissionService
from bot.services.user_balance_service import UserBalanceService
from config.settings import Settings
from db.dal import partner_checkout_dal, partner_dal, user_balance_dal

logger = logging.getLogger(__name__)

PARTNER_RECONCILIATION_LOCK = "partner-program-reconciliation"
PARTNER_RECONCILIATION_SECONDS = 60
PARTNER_RECONCILIATION_BATCH = 200
PARTNER_INTERNAL_SPEND_RECOVERY_MINUTES = 10


class PartnerProgramWorker:
    def __init__(self, settings: Settings, session_factory: sessionmaker) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                async with redis_lock(
                    self.settings,
                    PARTNER_RECONCILIATION_LOCK,
                    ttl_seconds=PARTNER_RECONCILIATION_SECONDS,
                ) as acquired:
                    if acquired:
                        started = time.monotonic()
                        counts = await self.tick()
                        logger.info(
                            "metric worker_tick_duration_seconds=%.3f worker=partner_program "
                            "decisions=%s available=%s reversals=%s recovered_spends=%s "
                            "purged_audit=%s purged_requisites=%s",
                            time.monotonic() - started,
                            counts["decisions"],
                            counts["available"],
                            counts["reversals"],
                            counts["recovered_spends"],
                            counts["purged_audit"],
                            counts["purged_requisites"],
                        )
            except Exception:
                logger.exception("Partner program reconciliation worker tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=PARTNER_RECONCILIATION_SECONDS,
                )

    def stop(self) -> None:
        self._stopped.set()

    async def tick(self) -> dict[str, int]:
        service = PartnerCommissionService(self.settings)
        async with self.session_factory() as session:
            decisions = await service.reconcile_payments(
                session,
                limit=PARTNER_RECONCILIATION_BATCH,
            )
            available = await service.post_due_commissions(
                session,
                limit=PARTNER_RECONCILIATION_BATCH,
            )
            reversals = await service.reconcile_refunds(
                session,
                limit=PARTNER_RECONCILIATION_BATCH,
            )
            recovered = await self._recover_stale_internal_spends(session, service)
            recovered += await self._recover_stale_checkout_spends(session)
            recovered += await self._release_terminal_checkout_spends(session)
            purged = await partner_dal.purge_expired_partner_data(
                session,
                audit_before=datetime.now(UTC)
                - timedelta(days=self.settings.partner_settings.audit_retention_days),
                requisites_before=datetime.now(UTC)
                - timedelta(days=self.settings.partner_settings.requisites_retention_days),
            )
            await session.commit()
        for decision in decisions:
            await service.emit_recorded(decision)
        for decision in available:
            await service.emit_available(decision)
        return {
            "decisions": len(decisions),
            "available": len(available),
            "reversals": len(reversals),
            "recovered_spends": recovered,
            "purged_audit": purged["audit"],
            "purged_requisites": purged["requisites"],
        }

    async def _recover_stale_internal_spends(
        self,
        session,
        service: PartnerCommissionService,
    ) -> int:
        payments = await partner_checkout_dal.list_stale_partner_balance_payments(
            session,
            older_than=datetime.now(UTC)
            - timedelta(minutes=PARTNER_INTERNAL_SPEND_RECOVERY_MINUTES),
            limit=PARTNER_RECONCILIATION_BATCH,
        )
        for payment in payments:
            await service.release_subscription_spend(
                session,
                payment_id=int(payment.payment_id),
            )
            payment.status = "activation_failed"
            payment.updated_at = datetime.now(UTC)
        return len(payments)

    async def _release_terminal_checkout_spends(self, session) -> int:
        partner_payments = await partner_checkout_dal.list_terminal_partner_checkout_payments(
            session,
            statuses=TERMINAL_CHECKOUT_STATUSES,
            limit=PARTNER_RECONCILIATION_BATCH,
        )
        for payment in partner_payments:
            await PartnerCheckoutBalanceService.release_if_terminal(
                session,
                payment_id=int(payment.payment_id),
                status=payment.status,
            )
        user_payments = await user_balance_dal.list_terminal_checkout_payments(
            session,
            statuses=TERMINAL_CHECKOUT_STATUSES,
            limit=PARTNER_RECONCILIATION_BATCH,
        )
        for payment in user_payments:
            await UserBalanceService.release_if_terminal(
                session,
                payment_id=int(payment.payment_id),
                status=payment.status,
            )
        return len(partner_payments) + len(user_payments)

    async def _recover_stale_checkout_spends(self, session) -> int:
        older_than = datetime.now(UTC) - timedelta(minutes=PARTNER_INTERNAL_SPEND_RECOVERY_MINUTES)
        partner_payments = await partner_checkout_dal.list_stale_partner_checkout_payments(
            session,
            older_than=older_than,
            limit=PARTNER_RECONCILIATION_BATCH,
        )
        for payment in partner_payments:
            await PartnerCheckoutBalanceService.release(
                session,
                payment_id=int(payment.payment_id),
                reason="partner-funded checkout finalization timed out",
            )
            payment.status = "activation_failed"
            payment.updated_at = datetime.now(UTC)
        user_payments = await user_balance_dal.list_stale_checkout_payments(
            session,
            older_than=older_than,
            limit=PARTNER_RECONCILIATION_BATCH,
        )
        for payment in user_payments:
            await UserBalanceService.release(
                session,
                payment_id=int(payment.payment_id),
                reason="user-balance-funded checkout finalization timed out",
            )
            payment.status = "activation_failed"
            payment.updated_at = datetime.now(UTC)
        return len(partner_payments) + len(user_payments)
