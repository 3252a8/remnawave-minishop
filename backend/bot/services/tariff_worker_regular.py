import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.message_audit import log_user_message_delivery
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.traffic_reset import (
    panel_traffic_limit_strategy,
    previous_traffic_reset,
    traffic_accounting_period_start,
    traffic_period_starts_match,
)
from config.settings import Settings
from db.dal import tariff_dal, user_dal
from db.models import Subscription

from .tariff_worker_shared import (
    TARIFF_WORKER_BATCH_SIZE,
    TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD,
    TARIFF_WORKER_PANEL_CONCURRENCY,
    deliver_traffic_warning,
)

logger = logging.getLogger(__name__)


class _RegularTariff(Protocol):
    billing_model: str
    monthly_bytes: int

    def name(self, lang: str, fallback: str = "ru") -> str: ...


class TariffWorkerRegularMixin:
    settings: Settings
    panel_service: PanelApiService
    subscription_service: SubscriptionService
    bot: Bot | None
    i18n: JsonI18n | None
    _premium_node_usage_tick_cache: dict[
        tuple[str, str, str],
        dict[str, dict[Any, int]] | None,
    ]

    if TYPE_CHECKING:
        REGULAR_RESET_NOTICE_LEVEL: int

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
        async def _user_lang(self, session: AsyncSession, user_id: int) -> str: ...
        def _period_tariff_traffic_strategy(self) -> str: ...
        def _usage_placeholders(self, used_bytes: int, limit_bytes: int) -> dict: ...
        def _panel_next_traffic_reset_at(
            self,
            panel_user_data: dict[str, Any] | None,
            *,
            now: datetime | None = None,
        ) -> datetime | None: ...
        def _traffic_next_reset_note(
            self,
            translate: Callable[..., str],
            *,
            kind: str,
            period_start_at: datetime | None,
            reset_available_bytes: int,
            user_lang: str,
            next_reset_at: datetime | None = None,
        ) -> str: ...
        def _traffic_topup_markup(
            self, user_lang: str, kind: str
        ) -> InlineKeyboardMarkup | None: ...
        async def _send_traffic_warning_email(
            self,
            session: AsyncSession,
            *,
            user_id: int,
            subject_key: str,
            message_text: str,
            kind: str,
            warning_key: str,
            audit_content: str,
        ) -> None: ...
        def _traffic_notice_channels_available(self) -> bool: ...
        def _traffic_reset_notice_is_reassuring(
            self, used_bytes: int, limit_bytes: int
        ) -> bool: ...
        async def _send_traffic_reset_notice(
            self,
            session: AsyncSession,
            *,
            sub: Subscription,
            subject_key: str,
            message_text: str,
            kind: str,
            warning_key: str,
            audit_content: str,
        ) -> None: ...

    async def traffic_period_tick(self, session: AsyncSession) -> None:
        now = datetime.now(UTC)
        self._premium_node_usage_tick_cache = {}
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
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.end_date > now,
                tracked_subscriptions_filter,
            )
            .order_by(Subscription.subscription_id.asc())
        )
        subs = list(result.scalars().all())
        if not subs:
            return

        panel_users_by_uuid = await self._prefetch_panel_users_by_uuid(subs)
        panel_view = "list" if panel_users_by_uuid is not None else "full_fetch"
        semaphore = asyncio.Semaphore(TARIFF_WORKER_PANEL_CONCURRENCY)

        async def _fetch_panel(sub: Subscription) -> dict:
            if panel_users_by_uuid is not None:
                cached_panel_user = panel_users_by_uuid.get(str(sub.panel_user_uuid))
                if cached_panel_user is not None:
                    return cached_panel_user
                return await self._repair_missing_panel_user_for_subscription(
                    session,
                    sub,
                    panel_users_by_uuid=panel_users_by_uuid,
                    semaphore=semaphore,
                    confirmed_missing=True,
                )

            async with semaphore:
                try:
                    data = await self.panel_service.get_user_by_uuid(
                        sub.panel_user_uuid, log_response=False
                    )
                except Exception:
                    logger.exception(
                        "TariffTrafficWorker: failed to fetch panel user %s",
                        sub.panel_user_uuid,
                    )
                    return {}
            if data:
                return data if isinstance(data, dict) else {}
            return await self._repair_missing_panel_user_for_subscription(
                session,
                sub,
                panel_users_by_uuid=None,
                semaphore=semaphore,
                confirmed_missing=False,
            )

        for chunk_start in range(0, len(subs), TARIFF_WORKER_BATCH_SIZE):
            chunk = subs[chunk_start : chunk_start + TARIFF_WORKER_BATCH_SIZE]
            panel_payloads = await asyncio.gather(*(_fetch_panel(s) for s in chunk))
            for sub, panel_data in zip(chunk, panel_payloads, strict=True):
                if not panel_data:
                    continue
                trial_premium_subscription = bool(
                    not getattr(sub, "tariff_key", None) and self._is_trial_subscription(sub)
                )
                if trial_premium_subscription:
                    tariff = self._trial_premium_tariff()
                    if tariff is None:
                        continue
                else:
                    try:
                        tariff = self.settings.tariffs_config.require(sub.tariff_key)
                    except Exception:
                        continue
                (
                    used,
                    limit,
                    _panel_strategy,
                ) = self.subscription_service._extract_panel_traffic_details(panel_data)
                effective_strategy = panel_traffic_limit_strategy(
                    panel_data,
                    self._period_tariff_traffic_strategy(),
                )
                panel_status = str(panel_data.get("status") or "").upper()
                panel_username = (
                    panel_data.get("username") if isinstance(panel_data, dict) else None
                )
                if used is not None and used != sub.traffic_used_bytes:
                    sub.traffic_used_bytes = used
                if limit is not None and limit != sub.traffic_limit_bytes:
                    sub.traffic_limit_bytes = limit
                if panel_status and panel_status != (sub.status_from_panel or "").upper():
                    sub.status_from_panel = panel_status

                if not trial_premium_subscription and tariff.billing_model == "period":
                    previous_regular_period_start = getattr(sub, "period_start_at", None)
                    warning_period_start = traffic_accounting_period_start(
                        self._period_tariff_traffic_strategy(),
                        now,
                        subscription_start_at=getattr(sub, "start_date", None),
                        previous_period_start_at=previous_regular_period_start,
                        panel_user_data=panel_data,
                    )
                    await self._maybe_send_regular_reset_notice(
                        session,
                        sub,
                        tariff,
                        used,
                        limit,
                        warning_period_start,
                        previous_period_start=previous_regular_period_start,
                        traffic_strategy=effective_strategy,
                    )
                    sub.period_start_at = warning_period_start
                else:
                    warning_period_start = None
                if not trial_premium_subscription:
                    panel_next_reset_at = self._panel_next_traffic_reset_at(panel_data, now=now)
                    await self._sync_hwid_device_limit(session, sub, tariff, panel_data)
                    await self._maybe_warn_or_throttle(
                        session,
                        sub,
                        tariff,
                        used,
                        limit,
                        warning_period_start=warning_period_start,
                        next_reset_at=panel_next_reset_at,
                    )

                await self._sync_premium_squad_limit(
                    session,
                    sub,
                    tariff,
                    now,
                    panel_username=panel_username,
                    panel_user_dict=panel_data,
                    panel_view=panel_view,
                )

    async def _prefetch_panel_users_by_uuid(
        self,
        subs: list[Subscription],
    ) -> dict[str, dict] | None:
        threshold = int(
            getattr(
                self.settings,
                "TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD",
                TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD,
            )
            or 0
        )
        if threshold <= 0 or len(subs) < threshold:
            return None
        try:
            panel_users = await self.panel_service.get_all_panel_users(log_responses=False)
        except Exception:
            logger.exception("TariffTrafficWorker: failed to bulk-prefetch panel users")
            return None
        if not panel_users:
            return None

        by_uuid: dict[str, dict] = {}
        for user in panel_users:
            if not isinstance(user, dict):
                continue
            uuid = user.get("uuid")
            if uuid:
                by_uuid[str(uuid)] = user
        if not by_uuid:
            return None
        matched = sum(1 for sub in subs if str(sub.panel_user_uuid) in by_uuid)
        logger.info(
            "metric panel_bulk_user_prefetch users=%s matched=%s active_subscriptions=%s",
            len(by_uuid),
            matched,
            len(subs),
        )
        return by_uuid

    async def _repair_missing_panel_user_for_subscription(
        self,
        session: AsyncSession,
        sub: Subscription,
        *,
        panel_users_by_uuid: dict[str, dict] | None,
        semaphore: asyncio.Semaphore,
        confirmed_missing: bool,
    ) -> dict:
        current_uuid = str(getattr(sub, "panel_user_uuid", "") or "").strip()
        try:
            user_id = int(sub.user_id)
        except (TypeError, ValueError):
            user_id = 0
        db_user = await user_dal.get_user_by_id(session, user_id) if user_id else None
        canonical_uuid = str(getattr(db_user, "panel_user_uuid", "") or "").strip()

        if canonical_uuid and canonical_uuid != current_uuid:
            panel_user = None
            if panel_users_by_uuid is not None:
                panel_user = panel_users_by_uuid.get(canonical_uuid)
            else:
                async with semaphore:
                    try:
                        panel_user = await self.panel_service.get_user_by_uuid(
                            canonical_uuid,
                            log_response=False,
                        )
                    except Exception:
                        logger.exception(
                            "TariffTrafficWorker: failed to fetch canonical panel user %s",
                            canonical_uuid,
                        )
                        panel_user = None
            if panel_user:
                logger.warning(
                    "TariffTrafficWorker: repaired subscription %s panel UUID %s -> %s",
                    sub.subscription_id,
                    current_uuid,
                    canonical_uuid,
                )
                sub.panel_user_uuid = canonical_uuid
                return panel_user

        if confirmed_missing:
            sub.is_active = False
            sub.skip_notifications = True
            sub.status_from_panel = "PANEL_USER_NOT_FOUND"
            logger.warning(
                "TariffTrafficWorker: deactivated subscription %s because panel user %s is missing",
                sub.subscription_id,
                current_uuid,
            )
        else:
            logger.warning(
                "TariffTrafficWorker: skipping subscription %s because panel user %s "
                "could not be fetched",
                sub.subscription_id,
                current_uuid,
            )
        return {}

    def _same_regular_period(
        self,
        value: datetime | None,
        period_start: datetime,
        *,
        traffic_strategy: str | None = None,
    ) -> bool:
        if value is None:
            return False
        try:
            return traffic_period_starts_match(
                value,
                period_start,
                traffic_strategy or self._period_tariff_traffic_strategy(),
            )
        except Exception:
            return False

    async def _sync_hwid_device_limit(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff: _RegularTariff,
        panel_data: dict[str, Any],
    ) -> None:
        base_hwid_limit = (
            int(sub.hwid_device_limit)
            if sub.hwid_device_limit is not None
            else self.subscription_service._base_hwid_limit_for_tariff(tariff)
        )
        active_extra = await tariff_dal.sum_active_hwid_devices(
            session,
            subscription_id=sub.subscription_id,
            at=datetime.now(UTC),
        )
        update_data = {}
        if sub.hwid_device_limit != base_hwid_limit:
            update_data["hwid_device_limit"] = base_hwid_limit
        if int(sub.extra_hwid_devices or 0) != active_extra:
            update_data["extra_hwid_devices"] = active_extra
        if update_data:
            for key, value in update_data.items():
                setattr(sub, key, value)

        effective_limit = self.subscription_service._effective_hwid_limit(
            base_hwid_limit,
            active_extra,
        )
        if effective_limit is None:
            return
        try:
            panel_limit = panel_data.get("hwidDeviceLimit")
            panel_limit_int = int(panel_limit) if panel_limit is not None else None
        except (TypeError, ValueError):
            panel_limit_int = None
        if panel_limit_int == effective_limit:
            return

        payload = self.subscription_service._build_panel_update_payload(
            panel_user_uuid=sub.panel_user_uuid,
            expire_at=sub.end_date,
            hwid_device_limit=effective_limit,
            include_default_squads=False,
        )
        updated_panel = await self.panel_service.update_user_details_on_panel(
            sub.panel_user_uuid,
            payload,
            log_response=False,
        )
        if not updated_panel or updated_panel.get("error"):
            logger.warning(
                "TariffTrafficWorker: failed to sync HWID limit for subscription %s: %s",
                sub.subscription_id,
                updated_panel,
            )

    async def _maybe_send_regular_reset_notice(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff: _RegularTariff,
        used: int | None,
        limit: int | None,
        period_start_at: datetime,
        *,
        previous_period_start: datetime | None,
        traffic_strategy: str,
    ) -> None:
        if traffic_strategy == "NO_RESET":
            return
        if not self._traffic_notice_channels_available():
            return
        if bool(getattr(sub, "regular_unlimited_override", False)):
            return
        used_val = int(used if used is not None else (getattr(sub, "traffic_used_bytes", 0) or 0))
        limit_val = int(
            limit if limit is not None else (getattr(sub, "traffic_limit_bytes", 0) or 0)
        )
        if not self._traffic_reset_notice_is_reassuring(used_val, limit_val):
            return

        expected_previous_period = previous_traffic_reset(
            period_start_at,
            traffic_strategy,
        )
        if expected_previous_period is None:
            return
        if not self._same_regular_period(
            previous_period_start,
            expected_previous_period,
            traffic_strategy=traffic_strategy,
        ):
            return
        was_warned_previous_period = await tariff_dal.has_warning_level_between(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=expected_previous_period,
            min_level=0,
            max_level=100,
        )
        if not was_warned_previous_period:
            return
        warned_current_period = await tariff_dal.has_warning_level_between(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=period_start_at,
            min_level=0,
            max_level=100,
        )
        if warned_current_period:
            return
        reset_notice = await tariff_dal.get_warning(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=period_start_at,
            level=self.REGULAR_RESET_NOTICE_LEVEL,
        )
        if reset_notice:
            return
        await tariff_dal.create_warning(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=period_start_at,
            level=self.REGULAR_RESET_NOTICE_LEVEL,
            traffic_limit_bytes=None,
        )

        user_lang = await self._user_lang(session, sub.user_id)
        _ = (
            (lambda k, **kw: self.i18n.gettext(user_lang, k, **kw))
            if self.i18n
            else (lambda k, **kw: k)
        )
        usage = self._usage_placeholders(used_val, limit_val)
        tariff_name = hd.quote(str(tariff.name(user_lang)))
        text = _(
            "traffic_reset_regular_notification",
            tariff_name=tariff_name,
            **usage,
        )
        warning_key = "traffic_reset_regular"
        audit_content = (
            f"kind=regular warning_key={warning_key} used_bytes={used_val} "
            f"limit_bytes={limit_val} period_start={period_start_at.isoformat()}"
        )
        await self._send_traffic_reset_notice(
            session,
            sub=sub,
            subject_key="email_traffic_reset_regular_subject",
            message_text=text,
            kind="regular",
            warning_key=warning_key,
            audit_content=audit_content,
        )

    async def _maybe_warn_or_throttle(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff: _RegularTariff,
        used: int | None,
        limit: int | None,
        *,
        warning_period_start: datetime | None = None,
        next_reset_at: datetime | None = None,
    ) -> None:
        if bool(getattr(sub, "regular_unlimited_override", False)):
            return
        used_val = int(used or sub.traffic_used_bytes or 0)
        limit_val = int(limit or sub.traffic_limit_bytes or 0)
        if limit_val <= 0:
            return
        ratio = used_val / limit_val
        levels = list(getattr(self.settings, "tariff_traffic_warning_levels", [85, 90, 95]))
        if 100 not in levels:
            levels.append(100)
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
            user_lang = await self._user_lang(session, sub.user_id)
            _ = (
                (lambda k, _user_lang=user_lang, **kw: self.i18n.gettext(_user_lang, k, **kw))
                if self.i18n
                else (lambda k, **kw: k)
            )
            left_pct = max(0, 100 - level)
            tariff_name = hd.quote(str(tariff.name(user_lang)))
            usage = self._usage_placeholders(used_val, limit_val)
            reset_note = self._traffic_next_reset_note(
                _,
                kind="regular",
                period_start_at=warning_period_start if tariff.billing_model == "period" else None,
                reset_available_bytes=limit_val,
                user_lang=user_lang,
                next_reset_at=next_reset_at,
            )
            if level < 100:
                text = _(
                    "traffic_warning_regular_almost",
                    tariff_name=tariff_name,
                    left_pct=left_pct,
                    **usage,
                )
                subject_key = "email_traffic_warning_regular_almost_subject"
            else:
                text = _(
                    "traffic_warning_regular_depleted",
                    tariff_name=tariff_name,
                    **usage,
                )
                subject_key = "email_traffic_warning_regular_depleted_subject"
            if reset_note:
                text = f"{text}\n\n{reset_note}"
            warning_key = (
                "traffic_warning_regular_almost"
                if level < 100
                else "traffic_warning_regular_depleted"
            )
            audit_content = (
                f"kind=regular warning_key={warning_key} level={level} "
                f"used_bytes={used_val} limit_bytes={limit_val}"
            )
            markup = self._traffic_topup_markup(user_lang, "regular") if self.bot else None
            await deliver_traffic_warning(
                session,
                user_id=sub.user_id,
                bot=self.bot,
                text=text,
                markup=markup,
                audit_content=audit_content,
                audit_logger=log_user_message_delivery,
                email_sender=self._send_traffic_warning_email,
                subject_key=subject_key,
                kind="regular",
                warning_key=warning_key,
                logger=logger,
                telegram_failure_message="Failed to send traffic warning to user %s",
            )
        if ratio >= 1.0 and not sub.is_throttled:
            logger.info(
                "Tariff traffic limit reached for user %s subscription %s. "
                "Leaving access control to Remnawave status handling.",
                sub.user_id,
                sub.subscription_id,
            )
