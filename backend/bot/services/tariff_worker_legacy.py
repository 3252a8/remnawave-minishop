from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from db.dal import subscription_dal
from db.models import Subscription

PREMIUM_WARNING_LEVEL_OFFSET = 1000
# Single warning per premium billing period when usage reached or exceeded the quota.
PREMIUM_WARNING_DEPLETED_LEVEL = PREMIUM_WARNING_LEVEL_OFFSET + 100

# Process active subscriptions in chunks and prefetch panel data concurrently
# to avoid an N+1 serial chain to the Remnawave panel each tick.
TARIFF_WORKER_BATCH_SIZE = 50
TARIFF_WORKER_PANEL_CONCURRENCY = 10
TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD = 50
TARIFF_WORKER_SQUAD_CONFIRMATION_CACHE_TTL_SECONDS = 900
TARIFF_WORKER_DB_RETRY_ATTEMPTS = 3
TARIFF_WORKER_DB_RETRY_BASE_SLEEP_SECONDS = 0.5
POSTGRES_RETRYABLE_SQLSTATES = {"40001", "40P01"}
POSTGRES_RETRYABLE_ERROR_NAMES = {"DeadlockDetectedError", "SerializationError"}


class TariffWorkerLegacyMixin:
    settings: Settings
    panel_service: PanelApiService

    async def legacy_throttle_recovery_tick(self, session: AsyncSession) -> None:
        """Recover subscriptions throttled by older bot versions.

        Current Remnawave versions enforce exhausted user traffic limits by
        switching the user status to LIMITED, so new ticks must not remove users
        from Internal Squads.
        """
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.is_throttled == True,
            )
            .order_by(Subscription.subscription_id.asc())
        )
        for sub in result.scalars().all():
            try:
                tariff = self.settings.tariffs_config.require(sub.tariff_key)
            except Exception:
                continue
            if int(sub.traffic_limit_bytes or 0) <= int(sub.traffic_used_bytes or 0):
                continue
            for squad_uuid in tariff.squad_uuids:
                await self.panel_service.add_users_to_internal_squad(
                    squad_uuid, [sub.panel_user_uuid]
                )
            await subscription_dal.update_subscription(
                session,
                sub.subscription_id,
                {"is_throttled": False, "status_from_panel": "ACTIVE"},
            )
