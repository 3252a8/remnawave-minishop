"""Fast re-check lane for premium squad limits.

The full tariff tick walks every active subscription and therefore runs on a slow
interval. Premium squads are access control, not a report: a subscription that is
about to exhaust its premium quota has to be re-checked far more often than the
full tick allows, otherwise the client keeps burning premium traffic until the
next full pass. This lane re-checks only the subscriptions that are close to the
premium limit (or already limited) so the extra panel load stays proportional to
the users that can actually cross the limit right now.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.models import Subscription

from .tariff_worker_shared import (
    TARIFF_WORKER_PANEL_CONCURRENCY,
    canonical_subscriptions_per_panel_user,
)

logger = logging.getLogger(__name__)


class TariffWorkerPremiumFastMixin:
    settings: Settings
    panel_service: PanelApiService
    subscription_service: SubscriptionService
    _premium_node_usage_tick_cache: dict[
        tuple[str, str, str],
        dict[str, dict[Any, int]] | None,
    ]
    _premium_usage_batch_tick_cache: dict[Any, Any]
    _premium_usage_completion_tick: dict[Any, bool]
    _premium_usage_user_limit_hint: int

    if TYPE_CHECKING:

        def _is_trial_subscription(self, sub: Subscription) -> bool: ...
        def _trial_premium_tariff(self) -> Any | None: ...
        async def _sync_premium_squad_limit(
            self,
            session: AsyncSession,
            sub: Subscription,
            tariff: Any,
            now: datetime,
            *,
            panel_username: str | None = None,
            panel_user_dict: dict | None = None,
            panel_view: str = "unknown",
        ) -> None: ...
        def _begin_premium_panel_batch(self) -> None: ...
        async def _finish_premium_panel_batch(self, session: AsyncSession) -> None: ...

    def premium_fast_tick_seconds(self) -> int:
        """Interval of the premium fast lane, or 0 when it is disabled."""
        fast_seconds = int(getattr(self.settings, "TARIFF_PREMIUM_FAST_TICK_SECONDS", 0) or 0)
        if fast_seconds <= 0:
            return 0
        full_seconds = max(1, int(self.settings.TARIFF_WORKER_TICK_SECONDS or 0))
        if fast_seconds >= full_seconds:
            return 0
        return fast_seconds

    async def premium_fast_tick(self, session: AsyncSession) -> None:
        now = datetime.now(UTC)
        # Request de-duplication is per tick; completed aggregate snapshots also
        # have a short cross-tick TTL matching Remnawave's aggregation cadence.
        self._premium_node_usage_tick_cache = {}
        self._premium_usage_batch_tick_cache.clear()
        self._premium_usage_completion_tick = {}
        subs = canonical_subscriptions_per_panel_user(
            list((await session.execute(self._premium_fast_candidates_query(now))).scalars()),
            logger=logger,
        )
        if not subs:
            return

        watched: list[tuple[Subscription, Any]] = []
        for sub in subs:
            tariff = self._premium_fast_tariff_for(sub)
            if tariff is None or not getattr(tariff, "premium_squad_uuids", None):
                continue
            watched.append((sub, tariff))
        if not watched:
            return

        self._premium_usage_user_limit_hint = len(watched)

        semaphore = asyncio.Semaphore(TARIFF_WORKER_PANEL_CONCURRENCY)

        async def _fetch_panel(sub: Subscription) -> dict[str, Any]:
            async with semaphore:
                try:
                    data = await self.panel_service.get_user_by_uuid(
                        sub.panel_user_uuid,
                        log_response=False,
                    )
                except Exception:
                    logger.exception(
                        "TariffTrafficWorker: premium fast tick failed to fetch panel user %s",
                        sub.panel_user_uuid,
                    )
                    return {}
            return data if isinstance(data, dict) else {}

        panel_payloads = await asyncio.gather(*(_fetch_panel(sub) for sub, _ in watched))
        self._begin_premium_panel_batch()
        synced = 0
        for (sub, tariff), panel_data in zip(watched, panel_payloads, strict=True):
            if not panel_data:
                continue
            await self._sync_premium_squad_limit(
                session,
                sub,
                tariff,
                now,
                panel_username=panel_data.get("username"),
                panel_user_dict=panel_data,
                panel_view="full_fetch",
            )
            synced += 1
        await self._finish_premium_panel_batch(session)
        logger.info(
            "metric premium_fast_tick_subscriptions candidates=%s synced=%s",
            len(watched),
            synced,
        )

    def _premium_fast_candidates_query(self, now: datetime) -> Select[tuple[Subscription]]:
        watch_percent = self._premium_fast_watch_percent()
        premium_limit_bytes = (
            func.coalesce(Subscription.premium_baseline_bytes, 0)
            + func.coalesce(Subscription.premium_topup_balance_bytes, 0)
            + func.coalesce(Subscription.premium_topup_used_bytes, 0)
            + func.coalesce(Subscription.premium_bonus_bytes, 0)
        )
        near_premium_limit = and_(
            premium_limit_bytes > 0,
            func.coalesce(Subscription.premium_used_bytes, 0) * 100
            >= watch_percent * premium_limit_bytes,
        )
        tracked_subscriptions_filter = Subscription.tariff_key.is_not(None)
        if self._trial_premium_tariff() is not None:
            tracked_subscriptions_filter = or_(
                tracked_subscriptions_filter,
                and_(
                    Subscription.tariff_key.is_(None),
                    or_(
                        Subscription.provider == "trial",
                        Subscription.status_from_panel == "TRIAL",
                    ),
                ),
            )
        query = (
            select(Subscription)
            .where(
                Subscription.is_active.is_(True),
                Subscription.end_date > now,
                Subscription.premium_unlimited_override.is_(False),
                tracked_subscriptions_filter,
                or_(Subscription.premium_is_limited.is_(True), near_premium_limit),
            )
            # Heaviest premium users first: they are the ones that can overshoot the
            # quota before the next tick when the batch cap truncates the lane.
            .order_by(
                func.coalesce(Subscription.premium_used_bytes, 0).desc(),
                Subscription.subscription_id.asc(),
            )
        )
        batch_limit = int(getattr(self.settings, "TARIFF_PREMIUM_FAST_BATCH_LIMIT", 0) or 0)
        if batch_limit > 0:
            query = query.limit(batch_limit)
        return query

    def _premium_fast_watch_percent(self) -> int:
        percent = int(getattr(self.settings, "TARIFF_PREMIUM_FAST_WATCH_PERCENT", 80) or 0)
        return min(100, max(0, percent))

    def _premium_fast_tariff_for(self, sub: Subscription) -> Any | None:
        if not getattr(sub, "tariff_key", None):
            if not self._is_trial_subscription(sub):
                return None
            return self._trial_premium_tariff()
        try:
            return self.settings.tariffs_config.require(sub.tariff_key)
        except Exception:
            return None
