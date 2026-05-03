import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
                    await self.legacy_throttle_recovery_tick(session)
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
            panel_status = str(panel_data.get("status") or "").upper()
            if used is not None and used != sub.traffic_used_bytes:
                sub.traffic_used_bytes = used
            if limit is not None and limit != sub.traffic_limit_bytes:
                sub.traffic_limit_bytes = limit
            if panel_status and panel_status != (sub.status_from_panel or "").upper():
                sub.status_from_panel = panel_status

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
        levels = list(getattr(self.settings, "tariff_traffic_warning_levels", [85, 90, 95]))
        for level in levels:
            threshold = level / 100
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
                    markup = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="Докупить трафик",
                                    callback_data="tariff_topup:list",
                                )
                            ]
                        ]
                    )
                    await self.bot.send_message(sub.user_id, text, reply_markup=markup)
                except Exception:
                    logging.exception("Failed to send traffic warning to user %s", sub.user_id)
        if ratio >= 1.0 and not sub.is_throttled:
            logging.info(
                "Tariff traffic limit reached for user %s subscription %s. "
                "Leaving access control to Remnawave status handling.",
                sub.user_id,
                sub.subscription_id,
            )

    async def legacy_throttle_recovery_tick(self, session: AsyncSession) -> None:
        """Recover subscriptions throttled by older bot versions.

        Current Remnawave versions enforce exhausted user traffic limits by
        switching the user status to LIMITED, so new ticks must not remove users
        from Internal Squads.
        """
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
