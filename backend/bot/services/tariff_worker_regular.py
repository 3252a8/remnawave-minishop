import asyncio
import logging
import time
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
from bot.services.panel_api_compat import PanelUserIdMode, numeric_panel_user_id
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_user_snapshot import should_use_full_panel_user_scan
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
    PanelLimitPatchState,
    canonical_subscriptions_per_panel_user,
    deliver_traffic_warning,
    record_panel_limit_drift,
)

logger = logging.getLogger(__name__)

# How many consecutive ticks may rewrite the same panel limits before the worker
# decides the value does not stick and backs off instead of storming the panel.
PANEL_LIMIT_PATCH_MAX_ATTEMPTS = 3
PANEL_LIMIT_PATCH_BACKOFF_SECONDS = 1800


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
    _premium_usage_batch_tick_cache: dict[Any, Any]
    _premium_usage_completion_tick: dict[Any, bool]
    _premium_usage_user_limit_hint: int
    _panel_limit_patches: dict[str, PanelLimitPatchState]

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
        def _begin_premium_panel_batch(self) -> None: ...
        async def _finish_premium_panel_batch(self, session: AsyncSession) -> None: ...
        async def _user_lang(self, session: AsyncSession, user_id: int) -> str: ...
        def _period_tariff_traffic_strategy(self, tariff: Any | None = None) -> str: ...
        def _usage_placeholders(self, used_bytes: int, limit_bytes: int) -> dict: ...
        def _panel_next_traffic_reset_at(
            self,
            panel_user_data: dict[str, Any] | None,
            *,
            now: datetime | None = None,
            fallback_strategy: str | None = None,
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
            traffic_strategy: str | None = None,
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
        self._premium_usage_batch_tick_cache.clear()
        self._premium_usage_completion_tick = {}
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
        subs = canonical_subscriptions_per_panel_user(
            list(result.scalars().all()),
            logger=logger,
        )
        if not subs:
            return

        self._premium_usage_user_limit_hint = len(subs)

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

        self._begin_premium_panel_batch()
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
                    self._period_tariff_traffic_strategy(tariff),
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
                        effective_strategy,
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
                    panel_next_reset_at = self._panel_next_traffic_reset_at(
                        panel_data,
                        now=now,
                        fallback_strategy=effective_strategy,
                    )
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
        await self._finish_premium_panel_batch(session)

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
        use_full_scan, panel_total = await should_use_full_panel_user_scan(
            self.panel_service,
            len(subs),
            threshold=threshold,
            concurrency=TARIFF_WORKER_PANEL_CONCURRENCY,
        )
        if not use_full_scan:
            logger.info(
                "metric panel_bulk_user_prefetch strategy=point panel_users=%s "
                "active_subscriptions=%s",
                panel_total,
                len(subs),
            )
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
            "metric panel_bulk_user_prefetch strategy=stream users=%s matched=%s "
            "active_subscriptions=%s",
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

        # A same-database Remnawave 2.x -> 3.x upgrade preserves the user but
        # replaces its API UUID with a numeric id.  Before the first full admin
        # sync, bulk-prefetched 3.x users therefore cannot match old local UUIDs.
        # Treating that mismatch as an authoritative deletion would deactivate
        # every active subscription.  Relink through the stable local identity
        # (Telegram/email/deterministic username) and keep the subscription
        # active if the panel is temporarily unavailable.
        current_is_legacy = bool(current_uuid and numeric_panel_user_id(current_uuid) is None)
        prefetched_refs = tuple((panel_users_by_uuid or {}).keys())
        prefetch_is_numeric = bool(prefetched_refs) and all(
            numeric_panel_user_id(value) is not None for value in prefetched_refs
        )
        numeric_generation = prefetch_is_numeric
        if current_is_legacy and not numeric_generation:
            try:
                compatibility = await self.panel_service.get_panel_api_compatibility()
            except Exception:
                logger.exception(
                    "TariffTrafficWorker: failed to detect panel generation while checking "
                    "a stale user reference"
                )
            else:
                numeric_generation = compatibility.user_id_mode is PanelUserIdMode.NUMERIC_ID
        if current_is_legacy and numeric_generation:
            relink = (
                getattr(
                    self.subscription_service,
                    "_get_or_create_panel_user_link",
                    None,
                )
                if db_user is not None
                else None
            )
            if callable(relink):
                try:
                    link = await relink(session, user_id, db_user)
                except Exception:
                    logger.exception(
                        "TariffTrafficWorker: failed to relink stale Remnawave user identity "
                        "for subscription %s",
                        sub.subscription_id,
                    )
                else:
                    relinked_uuid = str(getattr(link, "panel_user_uuid", "") or "").strip()
                    relinked_user = getattr(link, "panel_user", None)
                    if numeric_panel_user_id(relinked_uuid) is not None and isinstance(
                        relinked_user, dict
                    ):
                        sub.panel_user_uuid = relinked_uuid
                        logger.warning(
                            "TariffTrafficWorker: relinked subscription %s from a legacy "
                            "Remnawave UUID to numeric user id %s.",
                            sub.subscription_id,
                            relinked_uuid,
                        )
                        return relinked_user
            confirmed_missing = False

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
        entitlement_summary = await tariff_dal.get_hwid_device_entitlement_summary(
            session,
            subscription_id=sub.subscription_id,
            at=datetime.now(UTC),
            include_future=False,
        )
        active_extra = int(entitlement_summary.get("active_devices") or 0)
        previous_active_extra = int(sub.extra_hwid_devices or 0)
        update_data = {}
        if sub.hwid_device_limit != base_hwid_limit:
            update_data["hwid_device_limit"] = base_hwid_limit
        if previous_active_extra != active_extra:
            update_data["extra_hwid_devices"] = active_extra
        if update_data:
            for key, value in update_data.items():
                setattr(sub, key, value)

        effective_limit = self.subscription_service._effective_hwid_limit(
            base_hwid_limit,
            active_extra,
        )
        try:
            panel_limit = panel_data.get("hwidDeviceLimit")
            panel_limit_int = int(panel_limit) if panel_limit is not None else None
        except (TypeError, ValueError):
            panel_limit_int = None
        hwid_limit_changed = effective_limit is not None and panel_limit_int != effective_limit

        traffic_limit_for_panel: int | None = None
        panel_traffic_limit_int: int | None = None
        traffic_limit_changed = False
        if tariff.billing_model == "period" and (
            active_extra > 0 or previous_active_extra != active_extra
        ):
            traffic_limit_for_panel = self.subscription_service._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=int(
                    getattr(sub, "tier_baseline_bytes", 0) or tariff.monthly_bytes or 0
                ),
                topup_balance_bytes=max(0, int(getattr(sub, "topup_balance_bytes", 0) or 0)),
                regular_bonus_bytes=int(getattr(sub, "regular_bonus_bytes", 0) or 0),
                regular_unlimited_override=bool(getattr(sub, "regular_unlimited_override", False)),
                traffic_used_bytes=int(getattr(sub, "traffic_used_bytes", 0) or 0),
                hwid_device_bonus_bytes=(
                    self.subscription_service._hwid_traffic_bonus_bytes_from_summary(
                        entitlement_summary
                    )
                ),
            )
            try:
                panel_traffic_limit = panel_data.get("trafficLimitBytes")
                panel_traffic_limit_int = (
                    int(panel_traffic_limit) if panel_traffic_limit is not None else None
                )
            except (TypeError, ValueError):
                panel_traffic_limit_int = None
            traffic_limit_changed = panel_traffic_limit_int != traffic_limit_for_panel

        panel_uuid = str(getattr(sub, "panel_user_uuid", "") or "")
        if not hwid_limit_changed and not traffic_limit_changed:
            self._panel_limit_patches.pop(panel_uuid, None)
            return

        patch_signature = f"hwid:{effective_limit if hwid_limit_changed else '-'}"
        patch_signature += f"|traffic:{traffic_limit_for_panel if traffic_limit_changed else '-'}"
        if not await self._panel_limit_patch_allowed(
            panel_uuid,
            patch_signature,
            subscription_id=int(getattr(sub, "subscription_id", 0) or 0),
            observed=(
                f"hwidDeviceLimit={panel_limit_int} trafficLimitBytes={panel_traffic_limit_int}"
            ),
        ):
            return

        payload = self.subscription_service._build_panel_update_payload(
            panel_user_uuid=sub.panel_user_uuid,
            expire_at=sub.end_date,
            traffic_limit_bytes=traffic_limit_for_panel if traffic_limit_changed else None,
            traffic_limit_strategy=(
                self._period_tariff_traffic_strategy(tariff) if traffic_limit_changed else None
            ),
            hwid_device_limit=effective_limit if hwid_limit_changed else None,
            include_default_squads=False,
        )
        # Every panel PATCH makes Remnawave emit user.modified, so name the reason:
        # a value that never converges shows up here as the same reason each tick.
        logger.info(
            "Sync panel PATCH: source=%s user_id=%s panel_uuid=%s reasons=%s changes=%s",
            "tariff_device_limits",
            getattr(sub, "user_id", None),
            sub.panel_user_uuid,
            ",".join(
                reason
                for reason, changed in (
                    ("hwid_device_limit", hwid_limit_changed),
                    ("traffic_limit_bytes", traffic_limit_changed),
                )
                if changed
            ),
            " ".join(
                change
                for change in (
                    (
                        f"hwidDeviceLimit:{panel_limit_int}->{effective_limit}"
                        if hwid_limit_changed
                        else ""
                    ),
                    (
                        f"trafficLimitBytes:{panel_traffic_limit_int}->{traffic_limit_for_panel}"
                        if traffic_limit_changed
                        else ""
                    ),
                )
                if change
            ),
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
            return
        self._warn_on_unapplied_panel_limits(
            sub,
            updated_panel,
            hwid_device_limit=effective_limit if hwid_limit_changed else None,
            traffic_limit_bytes=traffic_limit_for_panel if traffic_limit_changed else None,
        )
        if traffic_limit_changed:
            sub.traffic_limit_bytes = traffic_limit_for_panel

    async def _panel_limit_patch_allowed(
        self,
        panel_uuid: str,
        signature: str,
        *,
        subscription_id: int,
        observed: str,
    ) -> bool:
        """Stop rewriting the same limits forever when the panel keeps drifting back.

        Each panel write makes Remnawave emit ``user.modified``, so a value that
        never sticks (something else rewrites it, or the panel ignores it) turns
        into a webhook storm. Repeat a few times, then back off and say so.
        """
        if not panel_uuid:
            return True
        state = self._panel_limit_patches.get(panel_uuid)
        now = time.monotonic()
        if state is None or state.signature != signature:
            self._panel_limit_patches[panel_uuid] = PanelLimitPatchState(
                signature=signature,
                attempts=1,
                blocked_until=0.0,
            )
            return True
        if state.blocked_until and now < state.blocked_until:
            return False

        attempts = state.attempts + 1
        if attempts > PANEL_LIMIT_PATCH_MAX_ATTEMPTS:
            state.attempts = attempts
            state.blocked_until = now + PANEL_LIMIT_PATCH_BACKOFF_SECONDS
            logger.error(
                "TariffTrafficWorker: panel limits for subscription %s (panel %s) did not stick "
                "after %s attempts (%s, panel still reports %s); pausing this sync for %s seconds. "
                "Another writer or a stale panel read is the usual cause.",
                subscription_id,
                panel_uuid,
                attempts - 1,
                signature,
                observed,
                PANEL_LIMIT_PATCH_BACKOFF_SECONDS,
            )
            await record_panel_limit_drift(
                self.settings,
                panel_uuid=panel_uuid,
                subscription_id=subscription_id,
                desired=signature,
                observed=observed,
            )
            return False
        state.attempts = attempts
        state.blocked_until = 0.0
        return True

    @staticmethod
    def _warn_on_unapplied_panel_limits(
        sub: Subscription,
        updated_panel: dict[str, Any],
        *,
        hwid_device_limit: int | None,
        traffic_limit_bytes: int | None,
    ) -> None:
        """Tell apart "the panel refused our value" from "someone rewrites it later"."""
        mismatches: list[str] = []
        for field, requested in (
            ("hwidDeviceLimit", hwid_device_limit),
            ("trafficLimitBytes", traffic_limit_bytes),
        ):
            if requested is None:
                continue
            raw_applied = updated_panel.get(field)
            try:
                applied = int(raw_applied) if raw_applied is not None else None
            except (TypeError, ValueError):
                applied = None
            if applied != int(requested):
                mismatches.append(f"{field}:requested={requested} applied={applied}")
        if mismatches:
            logger.warning(
                "TariffTrafficWorker: panel did not apply requested limits for subscription %s: %s",
                getattr(sub, "subscription_id", None),
                ", ".join(mismatches),
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
                traffic_strategy=self._period_tariff_traffic_strategy(tariff),
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
