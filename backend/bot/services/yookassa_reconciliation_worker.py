from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from aiogram import Bot
from sqlalchemy.orm import sessionmaker

from bot.app.factories.core_services import PanelService
from bot.infra import events
from bot.infra.event_payloads import PaymentCanceledPayload
from bot.infra.redis import redis_lock
from bot.middlewares.i18n import JsonI18n
from bot.payment_providers.yookassa.reconciliation import normalize_yookassa_payment_payload
from bot.payment_providers.yookassa.service import YooKassaService
from bot.payment_providers.yookassa.success import (
    emit_yookassa_success_events,
    payment_processing_lock,
    process_cancelled_payment,
    process_successful_payment,
)
from bot.services.lknpd_service import LknpdService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.dal import payment_dal
from db.dal.payment_dal import YooKassaReconciliationCandidate

logger = logging.getLogger(__name__)

YOOKASSA_RECONCILIATION_LOCK = "yookassa-payment-reconciliation"
DEFAULT_YOOKASSA_RECONCILIATION_TICK_SECONDS = 60
DEFAULT_YOOKASSA_RECONCILIATION_GRACE_SECONDS = 30
DEFAULT_YOOKASSA_RECONCILIATION_BATCH_SIZE = 100


class YooKassaReconciliationWorker:
    """Poll pending local YooKassa orders when a webhook is delayed or lost."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker,
        yookassa_service: YooKassaService,
        bot: Bot,
        i18n: JsonI18n,
        panel_service: PanelService,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        lknpd_service: LknpdService | None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.yookassa_service = yookassa_service
        self.bot = bot
        self.i18n = i18n
        self.panel_service = panel_service
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self.lknpd_service = lknpd_service
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        if not self.yookassa_service.configured:
            logger.info("YooKassa reconciliation worker disabled: provider is not configured")
            return

        while not self._stopped.is_set():
            try:
                async with redis_lock(
                    self.settings,
                    YOOKASSA_RECONCILIATION_LOCK,
                    ttl_seconds=max(60, self._tick_seconds()),
                ) as acquired:
                    if not acquired:
                        logger.info("YooKassa reconciliation tick skipped: Redis lock is held")
                    else:
                        started = time.monotonic()
                        await self.tick()
                        logger.info(
                            "metric worker_tick_duration_seconds=%.3f "
                            "worker=yookassa_reconciliation",
                            time.monotonic() - started,
                        )
            except Exception:
                logger.exception("YooKassa reconciliation worker tick failed")
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
                    "YOOKASSA_RECONCILIATION_TICK_SECONDS",
                    DEFAULT_YOOKASSA_RECONCILIATION_TICK_SECONDS,
                )
                or DEFAULT_YOOKASSA_RECONCILIATION_TICK_SECONDS
            ),
        )

    def _grace_seconds(self) -> int:
        return max(
            0,
            int(
                getattr(
                    self.settings,
                    "YOOKASSA_RECONCILIATION_GRACE_SECONDS",
                    DEFAULT_YOOKASSA_RECONCILIATION_GRACE_SECONDS,
                )
                or DEFAULT_YOOKASSA_RECONCILIATION_GRACE_SECONDS
            ),
        )

    def _batch_size(self) -> int:
        return max(
            1,
            int(
                getattr(
                    self.settings,
                    "YOOKASSA_RECONCILIATION_BATCH_SIZE",
                    DEFAULT_YOOKASSA_RECONCILIATION_BATCH_SIZE,
                )
                or DEFAULT_YOOKASSA_RECONCILIATION_BATCH_SIZE
            ),
        )

    async def tick(self) -> None:
        async with self.session_factory() as session:
            candidates = await payment_dal.list_yookassa_reconciliation_candidates(
                session,
                limit=self._batch_size(),
                grace_seconds=self._grace_seconds(),
            )

        for candidate in candidates:
            try:
                await self._reconcile_candidate(candidate)
            except Exception:
                logger.exception(
                    "Failed to reconcile YooKassa payment %s (remote %s)",
                    candidate.payment_id,
                    candidate.provider_payment_id,
                )

    async def _reconcile_candidate(
        self,
        candidate: YooKassaReconciliationCandidate,
    ) -> None:
        provider_payload = await self.yookassa_service.get_payment_info(
            candidate.provider_payment_id
        )
        if not provider_payload:
            await self._defer_candidate(candidate.payment_id)
            return

        payload = normalize_yookassa_payment_payload(provider_payload)
        remote_id = str(payload.get("id") or "").strip()
        if remote_id != candidate.provider_payment_id:
            logger.error(
                "YooKassa reconciliation response ID mismatch for local payment %s: "
                "expected %s, received %s",
                candidate.payment_id,
                candidate.provider_payment_id,
                remote_id or None,
            )
            await self._defer_candidate(candidate.payment_id)
            return

        metadata_raw = payload.get("metadata")
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        try:
            metadata_payment_id = int(str(metadata.get("payment_db_id") or ""))
        except ValueError:
            metadata_payment_id = 0
        if metadata_payment_id != candidate.payment_id:
            logger.error(
                "YooKassa reconciliation metadata mismatch for local payment %s: got %s",
                candidate.payment_id,
                metadata.get("payment_db_id"),
            )
            await self._defer_candidate(candidate.payment_id)
            return

        provider_status = str(payload.get("status") or "").strip().lower()
        if provider_status == "succeeded" and payload.get("paid") is True:
            finalized = await self._finalize_success(payload)
        elif provider_status in {"canceled", "cancelled"}:
            finalized = await self._finalize_cancellation(payload)
        else:
            finalized = False
        if not finalized:
            # Rotate candidates the finalizers could not resolve (validation
            # failures that leave the local order untouched); otherwise they
            # stay at the front of the bounded batch and starve the queue.
            await self._defer_candidate(candidate.payment_id)

    async def _finalize_success(self, payload: dict[str, Any]) -> bool:
        async with payment_processing_lock, self.session_factory() as session:
            try:
                event_payload = await process_successful_payment(
                    session,
                    self.bot,
                    payload,
                    self.i18n,
                    self.settings,
                    self.panel_service,
                    self.subscription_service,
                    self.referral_service,
                    self.lknpd_service,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        if event_payload:
            await emit_yookassa_success_events(event_payload)
        return event_payload is not None

    async def _finalize_cancellation(self, payload: dict[str, Any]) -> bool:
        async with payment_processing_lock, self.session_factory() as session:
            try:
                event_payload = await process_cancelled_payment(
                    session,
                    self.bot,
                    payload,
                    self.i18n,
                    self.settings,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        if event_payload:
            await events.emit_model(
                PaymentCanceledPayload.model_validate(event_payload),
                exclude_unset=True,
            )
        return event_payload is not None

    async def _defer_candidate(self, payment_id: int) -> None:
        async with self.session_factory() as session:
            await payment_dal.mark_yookassa_reconciliation_checked(session, payment_id)
            await session.commit()
