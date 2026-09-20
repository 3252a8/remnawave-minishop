from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from bot.services.panel_tariff_tags import (
    configured_tariff_tags,
    normalize_panel_tag,
    panel_tariff_tag_for_key,
    plan_panel_tariff_tag,
)
from bot.services.subscription_order_terms import gift_tariff
from config.settings import Settings
from db.dal import user_dal
from db.models import Subscription, User

from .tariff_worker_regular_warnings import TariffWorkerRegularWarningMixin

logger = logging.getLogger(__name__)


class TariffWorkerRegularTagMixin(TariffWorkerRegularWarningMixin):
    settings: Settings
    panel_service: PanelApiService

    if TYPE_CHECKING:

        def _is_trial_subscription(self, sub: Subscription) -> bool: ...

    async def _sync_panel_tariff_tag(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        panel_user_uuid: str,
        panel_user: dict[str, Any],
        desired_tag: str | None,
        source: str,
        db_user: User | None = None,
        is_trial: bool = False,
    ) -> dict[str, Any]:
        if db_user is None:
            db_user = await user_dal.get_user_by_id(session, user_id)
        if db_user is None:
            return panel_user
        tariffs_config = getattr(self.settings, "tariffs_config", None)
        plan = plan_panel_tariff_tag(
            current_tag=panel_user.get("tag"),
            managed_tag=getattr(db_user, "managed_panel_tariff_tag", None),
            desired_tag=panel_tariff_tag_for_key(desired_tag, tariffs_config, is_trial=is_trial),
            known_tariff_tags=configured_tariff_tags(tariffs_config),
        )
        if not plan.allowed:
            db_user.managed_panel_tariff_tag = None
            logger.warning(
                "TariffTrafficWorker: preserving external Remnawave tag for user %s "
                "during %s: current_tag=%r desired_tariff_tag=%r",
                user_id,
                source,
                plan.current_tag,
                plan.desired_tag,
            )
            return panel_user
        if not plan.needs_patch:
            db_user.managed_panel_tariff_tag = plan.managed_tag_after
            return panel_user

        updated = await self.panel_service.update_user_details_on_panel(
            panel_user_uuid,
            {"tag": plan.desired_tag},
        )
        if not updated:
            logger.warning(
                "TariffTrafficWorker: failed to update Remnawave tariff tag for user %s during %s.",
                user_id,
                source,
            )
            return panel_user
        try:
            confirmed = await self.panel_service.get_user_by_uuid(
                panel_user_uuid,
                log_response=False,
                use_cache=False,
            )
        except TypeError:
            confirmed = await self.panel_service.get_user_by_uuid(
                panel_user_uuid,
                log_response=False,
            )
        if (
            not isinstance(confirmed, dict)
            or normalize_panel_tag(confirmed.get("tag")) != plan.desired_tag
        ):
            logger.warning(
                "TariffTrafficWorker: Remnawave did not persist tariff tag for user %s during %s.",
                user_id,
                source,
            )
            return panel_user
        db_user.managed_panel_tariff_tag = plan.managed_tag_after
        return confirmed

    async def _reconcile_panel_tariff_tags(
        self,
        session: AsyncSession,
        *,
        now: datetime,
    ) -> None:
        result = await session.execute(
            select(User, Subscription)
            .outerjoin(
                Subscription,
                and_(
                    Subscription.user_id == User.user_id,
                    Subscription.panel_user_uuid == User.panel_user_uuid,
                    Subscription.is_active == True,
                    Subscription.end_date > now,
                ),
            )
            .where(
                User.panel_user_uuid.is_not(None),
                or_(
                    User.managed_panel_tariff_tag.is_not(None),
                    Subscription.subscription_id.is_not(None),
                ),
            )
            .order_by(User.user_id.asc(), Subscription.end_date.desc())
        )
        rows_by_user: dict[int, tuple[User, Subscription | None]] = {}
        for db_user, subscription in result.all():
            rows_by_user.setdefault(int(db_user.user_id), (db_user, subscription))
        panel_users_by_uuid: dict[str, dict[str, Any]] | None = None
        get_all_panel_users = getattr(self.panel_service, "get_all_panel_users", None)
        if callable(get_all_panel_users):
            try:
                panel_users = await get_all_panel_users(log_responses=False)
            except Exception:
                logger.exception(
                    "TariffTrafficWorker: failed to prefetch users for tariff tag reconciliation"
                )
            else:
                if isinstance(panel_users, list):
                    panel_users_by_uuid = {
                        str(panel_user.get("uuid") or ""): panel_user
                        for panel_user in panel_users
                        if isinstance(panel_user, dict) and panel_user.get("uuid") is not None
                    }
        for db_user, subscription in rows_by_user.values():
            panel_user_uuid = str(db_user.panel_user_uuid or "").strip()
            if not panel_user_uuid:
                continue
            is_trial = subscription is not None and self._is_trial_subscription(subscription)
            desired_tag = None
            if subscription is not None and not is_trial:
                # A stored binding remains authoritative when its catalog entry is removed.
                desired_tag = normalize_panel_tag(subscription.tariff_key)
                try:
                    tariff = gift_tariff(
                        subscription
                    ) or self.settings.tariffs_config.require_configured(subscription.tariff_key)
                except Exception:
                    tariff = None
                if tariff is not None:
                    desired_tag = str(getattr(tariff, "key", "") or "").strip() or None
            panel_user = (
                panel_users_by_uuid.get(panel_user_uuid)
                if panel_users_by_uuid is not None
                else None
            )
            if panel_user is None:
                try:
                    panel_user = await self.panel_service.get_user_by_uuid(
                        panel_user_uuid,
                        log_response=False,
                    )
                except Exception:
                    logger.exception(
                        "TariffTrafficWorker: failed to fetch user's Remnawave tag for %s",
                        db_user.user_id,
                    )
                    continue
            if not isinstance(panel_user, dict):
                continue
            try:
                await self._sync_panel_tariff_tag(
                    session,
                    user_id=int(db_user.user_id),
                    panel_user_uuid=panel_user_uuid,
                    panel_user=panel_user,
                    desired_tag=desired_tag,
                    source="tariff_tag_reconciliation",
                    db_user=db_user,
                    is_trial=is_trial,
                )
            except Exception:
                logger.exception(
                    "TariffTrafficWorker: failed to reconcile Remnawave tag for user %s",
                    db_user.user_id,
                )

    async def panel_tariff_tag_cleanup_tick(self, session: AsyncSession) -> None:
        await self._reconcile_panel_tariff_tags(session, now=datetime.now(UTC))
