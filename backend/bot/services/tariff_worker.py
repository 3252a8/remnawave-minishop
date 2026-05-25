import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.infra.redis import redis_lock
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.utils.date_utils import month_start
from bot.utils.mini_app_url import subscription_mini_app_topup_url
from config.settings import Settings
from db.dal import subscription_dal, tariff_dal, user_dal
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
        self._premium_nodes_cache = {}
        self._premium_node_usage_tick_cache = {}
        self._premium_squad_match_cache = {}

    async def _user_lang(self, session: AsyncSession, user_id: int) -> str:
        try:
            row = await user_dal.get_user_by_id(session, user_id)
            if row and getattr(row, "language_code", None):
                code = str(row.language_code or "").strip()
                if code:
                    return code
        except Exception:
            logging.exception("TariffTrafficWorker: failed to load user language for %s", user_id)
        return self.settings.DEFAULT_LANGUAGE

    def _usage_placeholders(self, used_bytes: int, limit_bytes: int) -> dict:
        """Formatted traffic stats for warning messages (HTML-safe quoted)."""
        used_b = max(0, int(used_bytes or 0))
        lim_b = max(0, int(limit_bytes or 0))
        remaining_b = max(0, lim_b - used_b)
        return {
            "used": hd.quote(self._fmt_bytes(used_b)),
            "remaining": hd.quote(self._fmt_bytes(remaining_b)),
            "limit_total": hd.quote(self._fmt_bytes(lim_b)),
        }

    def _traffic_topup_markup(self, user_lang: str, kind: str) -> Optional[InlineKeyboardMarkup]:
        if not self.bot:
            return None
        _ = lambda k, **kw: (
            self.i18n.gettext(user_lang, k, **kw) if self.i18n else (lambda key, **_: key)
        )
        normalized = "premium" if str(kind or "").lower() == "premium" else "regular"
        url = subscription_mini_app_topup_url(self.settings, normalized)
        if normalized == "premium":
            label_key = "traffic_warn_btn_topup_webapp_premium"
            fallback_key = "traffic_warn_btn_topup_premium"
        else:
            label_key = "traffic_warn_btn_topup_webapp_regular"
            fallback_key = "traffic_warn_btn_topup_regular"
        # Mini App inside Telegram when SUBSCRIPTION_MINI_APP_URL is configured.
        if url:
            button = InlineKeyboardButton(text=_(label_key), web_app=WebAppInfo(url=url))
        else:
            button = InlineKeyboardButton(text=_(fallback_key), callback_data="tariff_topup:list")
        return InlineKeyboardMarkup(inline_keyboard=[[button]])

    async def run(self) -> None:
        if not self.settings.tariffs_config:
            return
        while not self._stopped.is_set():
            try:
                async with redis_lock(
                    self.settings,
                    "tariff-traffic-worker",
                    ttl_seconds=self.settings.TARIFF_WORKER_LOCK_TTL_SECONDS,
                ) as acquired:
                    if not acquired:
                        logging.info("TariffTrafficWorker tick skipped: Redis lock is held")
                    else:
                        started = time.monotonic()
                        async with self.session_factory() as session:
                            await self.traffic_period_tick(session)
                            await session.commit()
                        async with self.session_factory() as session:
                            await self.legacy_throttle_recovery_tick(session)
                            await session.commit()
                        logging.info(
                            "metric worker_tick_duration_seconds=%.3f worker=tariff",
                            time.monotonic() - started,
                        )
            except Exception:
                logging.exception("TariffTrafficWorker tick failed")
            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=self.settings.TARIFF_WORKER_TICK_SECONDS,
                )
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()

    async def traffic_period_tick(self, session: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        self._premium_node_usage_tick_cache = {}
        warning_period_start = month_start(now)
        result = await session.execute(
            select(Subscription).where(
                Subscription.is_active == True,
                Subscription.end_date > now,
                Subscription.tariff_key.is_not(None),
            )
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
                    logging.exception(
                        "TariffTrafficWorker: failed to fetch panel user %s",
                        sub.panel_user_uuid,
                    )
                    return {}
            if data:
                return data
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
            for sub, panel_data in zip(chunk, panel_payloads):
                if not panel_data:
                    continue
                try:
                    tariff = self.settings.tariffs_config.require(sub.tariff_key)
                except Exception:
                    continue
                (
                    used,
                    limit,
                    panel_strategy,
                ) = self.subscription_service._extract_panel_traffic_details(panel_data)
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

                if tariff.billing_model == "period":
                    await self._ensure_period_reset_strategy(sub, tariff, limit, panel_strategy)
                await self._maybe_warn_or_throttle(
                    session,
                    sub,
                    tariff,
                    used,
                    limit,
                    warning_period_start=warning_period_start
                    if tariff.billing_model == "period"
                    else None,
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
    ) -> Optional[dict[str, dict]]:
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
            logging.exception("TariffTrafficWorker: failed to bulk-prefetch panel users")
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
        logging.info(
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
        panel_users_by_uuid: Optional[dict[str, dict]],
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
                        logging.exception(
                            "TariffTrafficWorker: failed to fetch canonical panel user %s",
                            canonical_uuid,
                        )
                        panel_user = None
            if panel_user:
                logging.warning(
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
            logging.warning(
                "TariffTrafficWorker: deactivated subscription %s because panel user %s is missing",
                sub.subscription_id,
                current_uuid,
            )
        else:
            logging.warning(
                "TariffTrafficWorker: skipping subscription %s because panel user %s "
                "could not be fetched",
                sub.subscription_id,
                current_uuid,
            )
        return {}

    async def _ensure_period_reset_strategy(
        self,
        sub: Subscription,
        tariff,
        limit: Optional[int],
        panel_strategy: Optional[str],
    ) -> None:
        if str(panel_strategy or "").upper() == "MONTH":
            return
        rb = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
        if bool(getattr(sub, "regular_unlimited_override", False)):
            baseline = int(sub.tier_baseline_bytes or (tariff.monthly_bytes if tariff else 0) or 0)
            traffic_limit_bytes = self.subscription_service._compute_main_traffic_limit_bytes(
                tier_baseline_bytes=baseline,
                topup_balance_bytes=int(sub.topup_balance_bytes or 0),
                regular_bonus_bytes=rb,
                regular_unlimited_override=True,
                traffic_used_bytes=int(sub.traffic_used_bytes or 0),
            )
        else:
            traffic_limit_bytes = int(
                limit
                or sub.traffic_limit_bytes
                or (tariff.monthly_bytes + int(sub.topup_balance_bytes or 0) + rb)
            )
        payload = self.subscription_service._build_panel_update_payload(
            panel_user_uuid=sub.panel_user_uuid,
            expire_at=sub.end_date,
            traffic_limit_bytes=traffic_limit_bytes,
            traffic_limit_strategy="MONTH",
        )
        payload["activeInternalSquads"] = self.subscription_service._panel_squads_for_tariff(
            tariff,
            include_premium=not bool(getattr(sub, "premium_is_limited", False)),
        )
        await self.panel_service.update_user_details_on_panel(
            sub.panel_user_uuid, payload, log_response=False
        )

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
        if bool(getattr(sub, "regular_unlimited_override", False)):
            return
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
                    user_lang = await self._user_lang(session, sub.user_id)
                    _ = (
                        (lambda k, **kw: self.i18n.gettext(user_lang, k, **kw))
                        if self.i18n
                        else (lambda k, **kw: k)
                    )
                    left_pct = max(0, 100 - level)
                    tariff_name = hd.quote(str(tariff.name(user_lang)))
                    usage = self._usage_placeholders(used_val, limit_val)
                    if level < 100:
                        text = _(
                            "traffic_warning_regular_almost",
                            tariff_name=tariff_name,
                            left_pct=left_pct,
                            **usage,
                        )
                    else:
                        text = _(
                            "traffic_warning_regular_depleted",
                            tariff_name=tariff_name,
                            **usage,
                        )
                    markup = self._traffic_topup_markup(user_lang, "regular")
                    await self.bot.send_message(
                        sub.user_id,
                        text,
                        reply_markup=markup,
                        parse_mode="HTML",
                    )
                except Exception:
                    logging.exception("Failed to send traffic warning to user %s", sub.user_id)
        if ratio >= 1.0 and not sub.is_throttled:
            logging.info(
                "Tariff traffic limit reached for user %s subscription %s. "
                "Leaving access control to Remnawave status handling.",
                sub.user_id,
                sub.subscription_id,
            )

    async def _sync_premium_squad_limit(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff,
        now: datetime,
        *,
        panel_username: Optional[str] = None,
        panel_user_dict: Optional[dict] = None,
        panel_view: str = "unknown",
    ) -> None:
        if not getattr(tariff, "premium_squad_uuids", None):
            if (
                any(
                    int(value or 0) > 0
                    for value in (
                        sub.premium_baseline_bytes,
                        sub.premium_topup_balance_bytes,
                        sub.premium_used_bytes,
                    )
                )
                or sub.premium_is_limited
            ):
                sub.premium_baseline_bytes = 0
                sub.premium_topup_balance_bytes = 0
                sub.premium_used_bytes = 0
                sub.premium_is_limited = False
            return

        premium_period_start = month_start(now)
        same_period = self._same_premium_period(
            getattr(sub, "premium_period_start_at", None),
            premium_period_start,
        )
        premium_baseline = int(tariff.premium_monthly_bytes or 0)
        premium_topup_balance = int(sub.premium_topup_balance_bytes or 0)
        premium_topup_used = (
            int(getattr(sub, "premium_topup_used_bytes", 0) or 0) if same_period else 0
        )
        premium_topup_balance = await self._repair_premium_topup_balance_from_ledger(
            session,
            sub,
            premium_period_start,
            premium_topup_balance,
            premium_topup_used,
        )
        # Admin-side overrides for free gifted premium traffic.
        premium_unlimited_override = bool(getattr(sub, "premium_unlimited_override", False))
        premium_bonus = max(0, int(getattr(sub, "premium_bonus_bytes", 0) or 0))
        premium_limit = (
            premium_baseline + premium_topup_balance + premium_topup_used + premium_bonus
        )
        if premium_limit <= 0 and not premium_unlimited_override:
            return

        node_uuids = await self._premium_node_uuids_for_tariff(tariff)
        if not node_uuids:
            logging.warning("Premium squads for tariff %s have no accessible nodes", tariff.key)
            return

        start_date = now.date().replace(day=1).isoformat()
        end_date = now.date().isoformat()
        premium_used = await self._premium_usage_for_user(
            sub.panel_user_uuid,
            node_uuids,
            start_date,
            end_date,
            panel_username=panel_username,
        )
        if premium_used is None:
            return

        # Consume paid top-up balance only for overflow beyond baseline+bonus.
        # Admin-granted bonus is "spent" against usage first along with baseline,
        # so the user's paid top-up survives longer.
        free_quota = premium_baseline + premium_bonus
        overflow = max(0, int(premium_used) - free_quota)
        delta_overflow = max(0, overflow - premium_topup_used)
        consume_from_topup = min(premium_topup_balance, delta_overflow)
        if consume_from_topup > 0:
            premium_topup_balance -= consume_from_topup
            premium_topup_used += consume_from_topup
            premium_limit = (
                premium_baseline + premium_topup_balance + premium_topup_used + premium_bonus
            )

        if premium_unlimited_override:
            should_limit = False
        else:
            should_limit = premium_used >= premium_limit
        access_state_changed = bool(sub.premium_is_limited) != should_limit
        desired_squads = self.subscription_service._panel_squads_for_tariff(
            tariff,
            include_premium=not should_limit,
        )
        desired_set = self._internal_squad_uuid_set(desired_squads)
        squad_match_cache_key = self._premium_squad_match_cache_key(
            sub.panel_user_uuid,
            desired_set,
        )
        panel_needs_update = access_state_changed
        panel_user_for_report = panel_user_dict
        panel_view_for_report = panel_view
        panel_update_reasons: list[str] = []
        if access_state_changed:
            panel_update_reasons.append(
                "premium_access_limited" if should_limit else "premium_access_restored"
            )

        current_known, current_set = self._panel_active_squad_uuid_set(panel_user_dict)
        if current_known:
            current_mismatch = desired_set != current_set
            if not current_mismatch:
                panel_needs_update = False
            elif panel_view == "list":
                if self._premium_squad_match_cache_is_fresh(squad_match_cache_key):
                    panel_needs_update = False
                else:
                    full_panel_user = await self._get_full_panel_user_for_squad_confirmation(
                        sub.panel_user_uuid,
                    )
                    full_known, full_set = self._panel_active_squad_uuid_set(full_panel_user)
                    if full_known:
                        panel_user_for_report = full_panel_user
                        panel_view_for_report = "full_fetch"
                        if desired_set != full_set:
                            panel_needs_update = True
                            panel_update_reasons.append("activeInternalSquads_mismatch")
                        else:
                            self._remember_premium_squad_match(squad_match_cache_key)
                            panel_needs_update = False
                    elif not access_state_changed:
                        panel_needs_update = False
            else:
                panel_needs_update = True
                panel_update_reasons.append("activeInternalSquads_mismatch")
        if (
            not panel_needs_update
            and current_known
            and desired_set == current_set
            and panel_view != "list"
        ):
            self._remember_premium_squad_match(squad_match_cache_key)
        sub.premium_baseline_bytes = premium_baseline
        sub.premium_topup_balance_bytes = premium_topup_balance
        sub.premium_topup_used_bytes = premium_topup_used
        sub.premium_used_bytes = int(premium_used)
        sub.premium_is_limited = bool(should_limit)
        sub.premium_period_start_at = premium_period_start
        if not premium_unlimited_override:
            await self._maybe_warn_premium_squad_limit(
                session,
                sub,
                tariff,
                premium_used,
                premium_limit,
                premium_period_start,
            )
        if not panel_needs_update:
            return

        squads = desired_squads
        self._log_premium_squad_panel_patch(
            sub=sub,
            panel_uuid=sub.panel_user_uuid,
            update_payload={"uuid": sub.panel_user_uuid, "activeInternalSquads": squads},
            current_panel_user=panel_user_for_report,
            reasons=panel_update_reasons or ["premium_squad_sync"],
            panel_view=panel_view_for_report,
        )
        updated_panel_user = await self.panel_service.update_user_details_on_panel(
            sub.panel_user_uuid,
            {"uuid": sub.panel_user_uuid, "activeInternalSquads": squads},
            log_response=False,
        )
        if updated_panel_user:
            self._remember_premium_squad_match(squad_match_cache_key)
        logging.info(
            "Premium squad access %s for user %s tariff %s: %s/%s bytes",
            "limited" if should_limit else "restored",
            sub.user_id,
            tariff.key,
            premium_used,
            premium_limit,
        )

    async def _get_full_panel_user_for_squad_confirmation(
        self,
        panel_user_uuid: str,
    ) -> Optional[dict]:
        try:
            return await self.panel_service.get_user_by_uuid(
                panel_user_uuid,
                log_response=False,
            )
        except Exception:
            logging.exception(
                "TariffTrafficWorker: failed to confirm panel squads for user %s",
                panel_user_uuid,
            )
            return None

    @staticmethod
    def _same_premium_period(value: Optional[datetime], premium_period_start: datetime) -> bool:
        if value is None:
            return False
        try:
            return month_start(value) == premium_period_start
        except Exception:
            return False

    async def _repair_premium_topup_balance_from_ledger(
        self,
        session: AsyncSession,
        sub: Subscription,
        premium_period_start: datetime,
        premium_topup_balance: int,
        premium_topup_used: int,
    ) -> int:
        ledger_total = await self._premium_topup_ledger_total(
            session,
            int(getattr(sub, "subscription_id", 0) or 0),
            premium_period_start,
        )
        if ledger_total is None:
            return premium_topup_balance

        tracked_total = max(0, int(premium_topup_balance or 0)) + max(
            0,
            int(premium_topup_used or 0),
        )
        if ledger_total <= tracked_total:
            return premium_topup_balance

        repaired_bytes = ledger_total - tracked_total
        logging.warning(
            "Premium top-up balance repaired from ledger for user %s subscription %s: "
            "tracked=%s ledger=%s repaired=%s",
            getattr(sub, "user_id", None),
            getattr(sub, "subscription_id", None),
            tracked_total,
            ledger_total,
            repaired_bytes,
        )
        return premium_topup_balance + repaired_bytes

    async def _premium_topup_ledger_total(
        self,
        session: AsyncSession,
        subscription_id: int,
        premium_period_start: datetime,
    ) -> Optional[int]:
        if not subscription_id or not isinstance(session, AsyncSession):
            return None
        try:
            return await tariff_dal.sum_traffic_topups(
                session,
                subscription_id=subscription_id,
                kinds=["premium_topup", "admin_premium_topup"],
                created_at_gte=premium_period_start,
            )
        except Exception:
            logging.exception(
                "TariffTrafficWorker: failed to read premium top-up ledger for subscription %s",
                subscription_id,
            )
            return None

    @staticmethod
    def _premium_squad_match_cache_key(
        panel_user_uuid: str,
        desired_set: set[str],
    ) -> tuple[str, tuple[str, ...]]:
        return str(panel_user_uuid), tuple(sorted(desired_set))

    def _premium_squad_match_cache_is_fresh(self, cache_key: tuple[str, tuple[str, ...]]) -> bool:
        cached_at = self._premium_squad_match_cache.get(cache_key)
        if not cached_at:
            return False
        return (
            time.monotonic() - float(cached_at)
            < TARIFF_WORKER_SQUAD_CONFIRMATION_CACHE_TTL_SECONDS
        )

    def _remember_premium_squad_match(self, cache_key: tuple[str, tuple[str, ...]]) -> None:
        self._premium_squad_match_cache[cache_key] = time.monotonic()

    @classmethod
    def _panel_active_squad_uuid_set(
        cls,
        panel_user_dict: Optional[dict],
    ) -> tuple[bool, set[str]]:
        current_known, current_raw = cls._panel_active_squads_raw(panel_user_dict)
        return current_known, cls._internal_squad_uuid_set(current_raw)

    @staticmethod
    def _panel_active_squads_raw(panel_user_dict: Optional[dict]) -> tuple[bool, Any]:
        if not isinstance(panel_user_dict, dict):
            return False, None
        for key in (
            "activeInternalSquads",
            "active_internal_squads",
            "activeInternalSquadUuids",
            "active_internal_squad_uuids",
        ):
            if key in panel_user_dict:
                return True, panel_user_dict.get(key)
        return False, None

    def _log_premium_squad_panel_patch(
        self,
        *,
        sub: Subscription,
        panel_uuid: str,
        update_payload: dict[str, Any],
        current_panel_user: Optional[dict],
        reasons: list[str],
        panel_view: str,
    ) -> None:
        current_known, current_set = self._panel_active_squad_uuid_set(current_panel_user)
        desired_set = self._internal_squad_uuid_set(update_payload.get("activeInternalSquads"))
        fields = "none" if current_known and current_set == desired_set else "activeInternalSquads"
        logging.info(
            "Sync panel PATCH: source=%s user_id=%s telegram_id=%s panel_uuid=%s "
            "panel_view=%s reasons=%s fields=%s payload_fields=%s changes=%s",
            "premium_squad_limit",
            getattr(sub, "user_id", None),
            getattr(sub, "user_id", None),
            panel_uuid,
            panel_view,
            ",".join(reasons),
            fields,
            "activeInternalSquads",
            "activeInternalSquads:%s->%s"
            % (
                self._format_squad_uuid_set(current_set if current_known else None),
                self._format_squad_uuid_set(desired_set),
            ),
        )

    @staticmethod
    def _internal_squad_uuid_set(raw) -> set[str]:
        if not isinstance(raw, (list, tuple, set)):
            return set()
        out: set[str] = set()
        for item in raw:
            if isinstance(item, dict):
                nested_squad = item.get("internalSquad") or item.get("squad")
                if not isinstance(nested_squad, dict):
                    nested_squad = {}
                u = (
                    item.get("uuid")
                    or item.get("internalSquadUuid")
                    or item.get("squadUuid")
                    or nested_squad.get("uuid")
                )
                if u:
                    out.add(str(u))
            elif item:
                out.add(str(item))
        return out

    @staticmethod
    def _format_squad_uuid_set(value: Optional[set[str]]) -> str:
        if value is None:
            return "missing"
        values = sorted(str(item) for item in value)
        preview = ",".join(values[:4])
        suffix = ",..." if len(values) > 4 else ""
        text = f"[{len(values)}:{preview}{suffix}]"
        if len(text) > 96:
            return f"{text[:93]}..."
        return text

    @staticmethod
    def _fmt_bytes(value: int) -> str:
        size = float(max(0, int(value or 0)))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} TB"

    async def _maybe_warn_premium_squad_limit(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff,
        used: int,
        limit: int,
        period_start_at: datetime,
    ) -> None:
        if limit <= 0:
            return
        used_val = int(used or 0)
        limit_val = int(limit)
        ratio = used_val / limit_val
        levels = list(getattr(self.settings, "tariff_traffic_warning_levels", [85, 90, 95]))

        # Fully exhausted or over quota — one message per period (same idea as regular traffic at 100%).  # noqa: E501
        if ratio >= 1.0:
            depleted_existing = await tariff_dal.get_warning(
                session,
                subscription_id=sub.subscription_id,
                period_start_at=period_start_at,
                level=PREMIUM_WARNING_DEPLETED_LEVEL,
            )
            if depleted_existing:
                return
            await tariff_dal.create_warning(
                session,
                subscription_id=sub.subscription_id,
                period_start_at=period_start_at,
                level=PREMIUM_WARNING_DEPLETED_LEVEL,
                traffic_limit_bytes=None,
            )
            if self.bot:
                try:
                    user_lang = await self._user_lang(session, sub.user_id)
                    _ = (
                        (lambda k, **kw: self.i18n.gettext(user_lang, k, **kw))
                        if self.i18n
                        else (lambda k, **kw: k)
                    )
                    access = await self.subscription_service.premium_access_for_tariff(tariff)
                    labels = access.get("node_labels") or access.get("squad_labels") or []
                    if labels:
                        visible = [hd.quote(str(x)) for x in labels[:8]]
                        servers = "\n".join(f"• {label}" for label in visible)
                        if len(labels) > len(visible):
                            more = len(labels) - len(visible)
                            servers += "\n" + _("traffic_warning_premium_servers_more", count=more)
                    else:
                        servers = _("traffic_warning_premium_generic_servers")
                    usage = self._usage_placeholders(used_val, limit_val)
                    text = _(
                        "traffic_warning_premium_depleted",
                        tariff_name=hd.quote(str(tariff.name(user_lang))),
                        servers=servers,
                        **usage,
                    )
                    markup = self._traffic_topup_markup(user_lang, "premium")
                    await self.bot.send_message(
                        sub.user_id,
                        text,
                        reply_markup=markup,
                        parse_mode="HTML",
                    )
                except Exception:
                    logging.exception(
                        "Failed to send premium traffic depleted warning to user %s", sub.user_id
                    )
            return

        for level in levels:
            if level >= 100:
                continue
            if ratio < level / 100:
                continue
            storage_level = PREMIUM_WARNING_LEVEL_OFFSET + int(level)
            warning = await tariff_dal.get_warning(
                session,
                subscription_id=sub.subscription_id,
                period_start_at=period_start_at,
                level=storage_level,
            )
            if warning:
                continue
            await tariff_dal.create_warning(
                session,
                subscription_id=sub.subscription_id,
                period_start_at=period_start_at,
                level=storage_level,
                traffic_limit_bytes=None,
            )
            if not self.bot:
                continue
            try:
                user_lang = await self._user_lang(session, sub.user_id)
                _ = (
                    (lambda k, **kw: self.i18n.gettext(user_lang, k, **kw))
                    if self.i18n
                    else (lambda k, **kw: k)
                )
                access = await self.subscription_service.premium_access_for_tariff(tariff)
                labels = access.get("node_labels") or access.get("squad_labels") or []
                if labels:
                    visible = [hd.quote(str(x)) for x in labels[:8]]
                    servers = "\n".join(f"• {label}" for label in visible)
                    if len(labels) > len(visible):
                        more = len(labels) - len(visible)
                        servers += "\n" + _("traffic_warning_premium_servers_more", count=more)
                else:
                    servers = _("traffic_warning_premium_generic_servers")
                left_pct = max(0, 100 - int(level))
                usage = self._usage_placeholders(used_val, limit_val)
                text = _(
                    "traffic_warning_premium_almost",
                    tariff_name=hd.quote(str(tariff.name(user_lang))),
                    left_pct=left_pct,
                    servers=servers,
                    **usage,
                )
                markup = self._traffic_topup_markup(user_lang, "premium")
                await self.bot.send_message(
                    sub.user_id,
                    text,
                    reply_markup=markup,
                    parse_mode="HTML",
                )
            except Exception:
                logging.exception("Failed to send premium traffic warning to user %s", sub.user_id)

    async def _premium_node_uuids_for_tariff(self, tariff) -> list[str]:
        cache_key = tuple(sorted(tariff.premium_squad_uuids or []))
        cached = self._premium_nodes_cache.get(cache_key)
        now_ts = datetime.now(timezone.utc).timestamp()
        if cached and now_ts - cached["ts"] < 600:
            return list(cached["nodes"])

        nodes: list[str] = []
        for squad_uuid in tariff.premium_squad_uuids or []:
            accessible = (
                await self.panel_service.get_internal_squad_accessible_nodes(squad_uuid) or []
            )
            for node in accessible:
                if not isinstance(node, dict):
                    continue
                node_uuid = node.get("uuid") or node.get("nodeUuid") or node.get("node_uuid")
                if node_uuid:
                    nodes.append(str(node_uuid))
        deduped = list(dict.fromkeys(nodes))
        self._premium_nodes_cache[cache_key] = {"ts": now_ts, "nodes": deduped}
        return deduped

    async def _premium_usage_for_user(
        self,
        user_uuid: str,
        node_uuids: list[str],
        start_date: str,
        end_date: str,
        *,
        panel_username: Optional[str] = None,
    ) -> Optional[int]:
        total = 0
        found = False
        username = (panel_username or "").strip() or None
        for node_uuid in node_uuids:
            lookup = await self._premium_usage_lookup_for_node(node_uuid, start_date, end_date)
            if not lookup:
                continue

            uuid_total = 0
            username_total = 0
            overlap_total = 0
            if user_uuid:
                user_uuid_str = str(user_uuid)
                uuid_total = int(lookup["by_uuid"].get(user_uuid_str, 0) or 0)
            else:
                user_uuid_str = ""
            if username:
                username_total = int(lookup["by_username"].get(username, 0) or 0)
            if user_uuid_str and username:
                overlap_total = int(
                    lookup["by_uuid_username"].get((user_uuid_str, username), 0) or 0
                )

            node_total = uuid_total + username_total - overlap_total
            if node_total or (
                user_uuid_str in lookup["by_uuid"]
                or (username and username in lookup["by_username"])
            ):
                total += node_total
                found = True
        return total if found else 0

    async def _premium_usage_lookup_for_node(
        self,
        node_uuid: str,
        start_date: str,
        end_date: str,
    ) -> Optional[dict]:
        stats_cache_key = (node_uuid, start_date, end_date)
        if stats_cache_key not in self._premium_node_usage_tick_cache:
            stats = await self.panel_service.get_node_users_bandwidth_stats(
                node_uuid,
                start=start_date,
                end=end_date,
            )
            self._premium_node_usage_tick_cache[stats_cache_key] = self._build_premium_usage_lookup(
                stats
            )
        return self._premium_node_usage_tick_cache.get(stats_cache_key)

    @staticmethod
    def _build_premium_usage_lookup(stats: Optional[dict]) -> Optional[dict]:
        if not isinstance(stats, dict):
            return None
        entries = stats.get("topUsers") or stats.get("usersStats") or stats.get("users") or []
        if not isinstance(entries, list):
            return None

        by_uuid: dict[str, int] = {}
        by_username: dict[str, int] = {}
        by_uuid_username: dict[tuple[str, str], int] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            user_obj = entry.get("user") if isinstance(entry.get("user"), dict) else {}
            entry_uuid = (
                user_obj.get("uuid")
                or entry.get("userUuid")
                or entry.get("uuid")
                or entry.get("user_uuid")
            )
            entry_username = (
                user_obj.get("username") or entry.get("username") or entry.get("userUsername")
            )
            value = entry.get("total")
            if value is None:
                value = int(entry.get("download", 0) or 0) + int(entry.get("upload", 0) or 0)
            total = int(value or 0)
            uuid_key = str(entry_uuid) if entry_uuid else ""
            username_key = str(entry_username) if entry_username else ""
            if uuid_key:
                by_uuid[uuid_key] = by_uuid.get(uuid_key, 0) + total
            if username_key:
                by_username[username_key] = by_username.get(username_key, 0) + total
            if uuid_key and username_key:
                pair = (uuid_key, username_key)
                by_uuid_username[pair] = by_uuid_username.get(pair, 0) + total
        return {
            "by_uuid": by_uuid,
            "by_username": by_username,
            "by_uuid_username": by_uuid_username,
        }

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
                await self.panel_service.add_users_to_internal_squad(
                    squad_uuid, [sub.panel_user_uuid]
                )
            await subscription_dal.update_subscription(
                session,
                sub.subscription_id,
                {"is_throttled": False, "status_from_panel": "ACTIVE"},
            )
