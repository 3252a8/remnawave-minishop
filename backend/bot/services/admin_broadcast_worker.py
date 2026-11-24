"""Worker loop that starts durable broadcasts when their schedule is due."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import sessionmaker

from bot.services.admin_broadcast_delivery import AdminBroadcastDeliveryService
from db.dal import broadcast_dal

logger = logging.getLogger(__name__)

BROADCAST_WORKER_INTERVAL_SECONDS = 1.0


class AdminBroadcastWorker:
    def __init__(
        self,
        session_factory: sessionmaker,
        delivery_service: AdminBroadcastDeliveryService,
    ) -> None:
        self.session_factory = session_factory
        self.delivery_service = delivery_service

    async def run(self) -> None:
        async with self.session_factory() as session:
            recovered = await broadcast_dal.recover_interrupted_broadcasts(session)
        if recovered:
            logger.warning("Recovered %s interrupted broadcast delivery item(s)", recovered)

        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Admin broadcast worker tick failed")
            await asyncio.sleep(BROADCAST_WORKER_INTERVAL_SECONDS)

    async def _tick(self) -> None:
        async with self.session_factory() as session:
            due_ids, running_ids = await broadcast_dal.poll_broadcast_ids(session)
        for broadcast_id in due_ids:
            try:
                await self.delivery_service.dispatch(broadcast_id)
            except Exception:
                logger.exception("Admin broadcast %s dispatch failed", broadcast_id)

        # Delivery callbacks normally finalize a broadcast. This pass closes a
        # rare race where the last two callbacks commit at exactly the same time.
        if due_ids:
            # Dispatch can start or finish jobs since the initial poll.
            async with self.session_factory() as session:
                running_ids = await broadcast_dal.running_broadcast_ids(session)
        for broadcast_id in running_ids:
            async with self.session_factory() as session:
                await broadcast_dal.refresh_broadcast_stats(session, broadcast_id)
