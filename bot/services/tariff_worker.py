import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.utils.date_utils import month_start
from config.settings import Settings
from db.dal import subscription_dal, tariff_dal
from db.models import Subscription


class TariffTrafficWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker,
        panel_service: PanelApiService,
        subscription_service: SubscriptionService,
        bot: Optional[Bot] = None,
        i18n: Optional[JsonI18n] = None,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.panel_service = panel_service
        self.subscription_service = subscription_service
        self.bot = bot
        self.i18n = i18n
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        if not self.settings.tariffs_config:
            return
        while not self._stopped.is_set():
            try:
                async with self.session_factory() as session:
                    await self.traffic_period_tick(session)
                    await session.commit()
                async with self.session_factory() as session:
                    await self.throttle_recovery_tick(session)
                    await session.commit()
            except Exception:
                logging.exception("TariffTrafficWorker tick failed")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=300)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()

    async def traffic_period_tick(self, session: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        warning_period_start = month_start(now)
        result = await session.execute(
            select(Subscription).where(
                Subscription.is_active == True,
                Subscription.end_date > now,
                Subscription.tariff_key.is_not(None),
            )
        )
        for sub in result.scalars().all():
            try:
                tariff = self.settings.tariffs_config.require(sub.tariff_key)
            except Exception:
                continue
            panel_data = await self.panel_service.get_user_by_uuid(sub.panel_user_uuid, log_response=False) or {}
            used, limit, panel_strategy = self.subscription_service._extract_panel_traffic_details(panel_data)
            if used is not None and used != sub.traffic_used_bytes:
                sub.traffic_used_bytes = used
            if limit is not None and limit != sub.traffic_limit_bytes:
                sub.traffic_limit_bytes = limit

            if tariff.billing_model == "period":
                await self._ensure_period_reset_strategy(sub, tariff, limit, panel_strategy)
            await self._maybe_warn_or_throttle(
                session,
                sub,
                tariff,
                used,
                limit,
                warning_period_start=warning_period_start if tariff.billing_model == "period" else None,
            )

    async def _ensure_period_reset_strategy(
        self,
        sub: Subscription,
        tariff,
        limit: Optional[int],
        panel_strategy: Optional[str],
    ) -> None:
        if str(panel_strategy or "").upper() == "MONTH":
            return
        traffic_limit_bytes = int(limit or sub.traffic_limit_bytes or (tariff.monthly_bytes + int(sub.topup_balance_bytes or 0)))
        payload = self.subscription_service._build_panel_update_payload(
            panel_user_uuid=sub.panel_user_uuid,
            expire_at=sub.end_date,
            status="ACTIVE",
            traffic_limit_bytes=traffic_limit_bytes,
            traffic_limit_strategy="MONTH",
        )
        payload["activeInternalSquads"] = tariff.squad_uuids
        await self.panel_service.update_user_details_on_panel(sub.panel_user_uuid, payload, log_response=False)

    async def _maybe_warn_or_throttle(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff,
        used: Optional[int],
        limit: Optional[int],
        *,
        warning_period_start: Optional[datetime] = None,
    ) -> None:
        used_val = int(used or sub.traffic_used_bytes or 0)
        limit_val = int(limit or sub.traffic_limit_bytes or 0)
        if limit_val <= 0:
            return
        ratio = used_val / limit_val
        for level, threshold in ((80, 0.8), (95, 0.95), (100, 1.0)):
            if ratio < threshold:
                continue
            warning = await tariff_dal.get_warning(
                session,
                subscription_id=sub.subscription_id,
                period_start_at=warning_period_start if tariff.billing_model == "period" else None,
                level=level,
                traffic_limit_bytes=limit_val if tariff.billing_model == "traffic" else None,
            )
            if warning:
                continue
            await tariff_dal.create_warning(
                session,
                subscription_id=sub.subscription_id,
                period_start_at=warning_period_start if tariff.billing_model == "period" else None,
                level=level,
                traffic_limit_bytes=limit_val if tariff.billing_model == "traffic" else None,
            )
            if self.bot:
                try:
                    left_pct = max(0, 100 - level)
                    if level < 100:
                        text = f"Трафик тарифа {tariff.name(self.settings.DEFAULT_LANGUAGE)} почти закончился. Осталось около {left_pct}%."
                    else:
                        text = "Трафик закончился. Доступ временно ограничен до сброса или докупки пакета."
                    await self.bot.send_message(sub.user_id, text)
                except Exception:
                    logging.exception("Failed to send traffic warning to user %s", sub.user_id)
            if level == 100:
                await self._throttle(session, sub, tariff)

    async def _throttle(self, session: AsyncSession, sub: Subscription, tariff) -> None:
        if sub.is_throttled:
            return
        for squad_uuid in tariff.squad_uuids:
            await self.panel_service.remove_users_from_internal_squad(squad_uuid, [sub.panel_user_uuid])
        await subscription_dal.update_subscription(
            session,
            sub.subscription_id,
            {"is_throttled": True, "status_from_panel": "THROTTLED_BY_BOT"},
        )

    async def throttle_recovery_tick(self, session: AsyncSession) -> None:
        result = await session.execute(
            select(Subscription).where(
                Subscription.is_active == True,
                Subscription.is_throttled == True,
            )
        )
        for sub in result.scalars().all():
            try:
                tariff = self.settings.tariffs_config.require(sub.tariff_key)
            except Exception:
                continue
            if int(sub.traffic_limit_bytes or 0) <= int(sub.traffic_used_bytes or 0):
                continue
            for squad_uuid in tariff.squad_uuids:
                await self.panel_service.add_users_to_internal_squad(squad_uuid, [sub.panel_user_uuid])
            await subscription_dal.update_subscription(
                session,
                sub.subscription_id,
                {"is_throttled": False, "status_from_panel": "ACTIVE"},
            )
