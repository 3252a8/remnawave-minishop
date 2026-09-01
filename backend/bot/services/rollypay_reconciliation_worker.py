"""Poll RollyPay subscription state because the API has no mandate-state webhook."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy.orm import sessionmaker

from bot.infra.redis import redis_lock
from bot.payment_providers.rollypay.service import RollyPayService
from db.dal import rollypay_dal

logger = logging.getLogger(__name__)

ROLLYPAY_RECONCILIATION_LOCK = "rollypay-subscription-reconciliation"


class RollyPayReconciliationWorker:
    def __init__(self, session_factory: sessionmaker, service: RollyPayService) -> None:
        self.session_factory = session_factory
        self.service = service
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        if not self.service.manages_recurrence:
            logger.info("RollyPay subscription reconciliation disabled")
            return
        while not self._stopped.is_set():
            try:
                async with redis_lock(
                    self.service.settings,
                    ROLLYPAY_RECONCILIATION_LOCK,
                    ttl_seconds=max(60, self.interval_seconds),
                ) as acquired:
                    if acquired:
                        await self.tick()
            except Exception:
                logger.exception("RollyPay subscription reconciliation tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)

    @property
    def interval_seconds(self) -> int:
        return int(self.service.config.RECONCILE_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._stopped.set()

    async def tick(self) -> None:
        async with self.session_factory() as session:
            records = await rollypay_dal.list_reconcilable(
                session,
                limit=int(self.service.config.RECONCILE_BATCH_SIZE),
            )
            remote_ids = [str(record.rollypay_subscription_id) for record in records]
        for remote_id in remote_ids:
            success, remote = await self.service.get_remote_subscription(remote_id)
            if not success:
                continue
            async with self.session_factory() as session:
                record = await rollypay_dal.get_subscription(
                    session,
                    remote_id,
                    for_update=True,
                )
                if record is None:
                    continue
                await self.service.sync_subscription_state(session, record, remote)
                await session.commit()


__all__ = ["RollyPayReconciliationWorker"]
