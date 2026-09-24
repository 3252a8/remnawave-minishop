from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Mapping

from aiogram import Bot
from sqlalchemy.orm import sessionmaker

from bot.infra.redis import redis_lock
from bot.middlewares.i18n import JsonI18n
from bot.payment_providers.registry import get_provider_spec
from bot.payment_providers.shared.common import detached_payment_snapshot
from bot.payment_providers.shared.reconciliation import (
    RECONCILABLE_PROVIDER_KEYS,
    refresh_hosted_payment_status,
)
from bot.payment_providers.shared.webhooks import notify_user_payment_failed
from config.settings import Settings
from db.dal import payment_dal, payment_reconciliation_dal

logger = logging.getLogger(__name__)

PAYMENT_RECONCILIATION_LOCK = "hosted-payment-reconciliation"
DEFAULT_PAYMENT_RECONCILIATION_TICK_SECONDS = 60
DEFAULT_PAYMENT_RECONCILIATION_BATCH_SIZE = 100


class PaymentReconciliationWorker:
    """Poll provider read APIs so expired hosted checkouts cannot reserve promos."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker,
        services: Mapping[str, object],
        bot: Bot | None,
        i18n: JsonI18n,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.services = services
        self.bot = bot
        self.i18n = i18n
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                async with redis_lock(
                    self.settings,
                    PAYMENT_RECONCILIATION_LOCK,
                    ttl_seconds=max(60, self._tick_seconds()),
                ) as acquired:
                    if acquired:
                        started = time.monotonic()
                        await self.tick()
                        logger.info(
                            "metric worker_tick_duration_seconds=%.3f "
                            "worker=payment_reconciliation",
                            time.monotonic() - started,
                        )
            except Exception:
                logger.exception("Hosted payment reconciliation worker tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._tick_seconds())

    def stop(self) -> None:
        self._stopped.set()

    def _tick_seconds(self) -> int:
        return DEFAULT_PAYMENT_RECONCILIATION_TICK_SECONDS

    def _batch_size(self) -> int:
        return DEFAULT_PAYMENT_RECONCILIATION_BATCH_SIZE

    async def tick(self) -> None:
        await self._retry_failure_notifications()
        async with self.session_factory() as session:
            payments = await payment_reconciliation_dal.list_candidates(
                session,
                providers=RECONCILABLE_PROVIDER_KEYS,
                limit=self._batch_size(),
                retry_after_seconds=self._tick_seconds(),
            )
            candidates = [detached_payment_snapshot(payment) for payment in payments]

        for candidate in candidates:
            spec = get_provider_spec(str(candidate.provider or ""))
            service = self.services.get(spec.service_key) if spec and spec.service_key else None
            if service is None or not getattr(service, "configured", False):
                continue
            try:
                async with self.session_factory() as session:
                    current = await payment_dal.get_payment_by_db_id(
                        session,
                        int(candidate.payment_id),
                        fresh=True,
                    )
                    if current is None:
                        continue
                    current_snapshot = detached_payment_snapshot(current)
                    await session.rollback()
                    await refresh_hosted_payment_status(session, current_snapshot, service)
            except Exception:
                logger.exception(
                    "Failed to reconcile %s payment %s",
                    candidate.provider,
                    candidate.payment_id,
                )

    async def _retry_failure_notifications(self) -> None:
        async with self.session_factory() as session:
            payments = await payment_reconciliation_dal.list_unsent_failure_notifications(
                session,
                limit=self._batch_size(),
                older_than_seconds=max(
                    0,
                    int(
                        getattr(
                            self.settings,
                            "PAYMENT_FAILURE_NOTIFICATION_GRACE_SECONDS",
                            300,
                        )
                        or 0
                    ),
                ),
            )
            candidates = [detached_payment_snapshot(payment) for payment in payments]

        for candidate in candidates:
            try:
                async with self.session_factory() as session:
                    await notify_user_payment_failed(
                        bot=self.bot,
                        settings=self.settings,
                        i18n=self.i18n,
                        session=session,
                        payment=candidate,
                    )
            except Exception:
                logger.exception(
                    "Failed to deliver payment failure notification for payment %s",
                    candidate.payment_id,
                )
