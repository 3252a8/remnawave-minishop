import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.infra.redis import redis_lock
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.services.user_email_notifications import send_user_notification_email
from bot.utils.mini_app_url import subscription_mini_app_topup_url
from config.settings import Settings
from db.advisory_locks import acquire_subscription_background_sync_lock
from db.dal import user_dal
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


class _TrialPremiumTariff:
    key = "trial"
    billing_model = "trial"
    premium_topup_packages = None
    hwid_device_limit = None

    def __init__(
        self,
        *,
        squad_uuids: list[str],
        premium_squad_uuids: list[str],
        premium_monthly_bytes: int,
    ) -> None:
        self.squad_uuids = list(squad_uuids)
        self.premium_squad_uuids = list(premium_squad_uuids)
        self._premium_monthly_bytes = int(premium_monthly_bytes or 0)

    @property
    def premium_monthly_bytes(self) -> int:
        return self._premium_monthly_bytes

    def name(self, _lang: str, _fallback: str = "ru") -> str:
        return "Trial"

    def description(self, _lang: str, _fallback: str = "ru") -> str:
        return ""

    def premium_name(self, _lang: str, _fallback: str = "ru") -> str:
        return "Premium servers"


class TariffWorkerCoreMixin:
    if TYPE_CHECKING:

        def _fmt_bytes(self, value: int) -> str: ...
        async def traffic_period_tick(self, session: AsyncSession) -> None: ...
        async def legacy_throttle_recovery_tick(self, session: AsyncSession) -> None: ...

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
        self._premium_nodes_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self._premium_node_usage_tick_cache: dict[
            tuple[str, str, str],
            Optional[dict[str, dict[Any, int]]],
        ] = {}
        self._premium_squad_match_cache: dict[tuple[str, tuple[str, ...]], float] = {}

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

        def translate(key: str, **kwargs: Any) -> str:
            if self.i18n:
                return self.i18n.gettext(user_lang, key, **kwargs)
            return key

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
            button = InlineKeyboardButton(text=translate(label_key), web_app=WebAppInfo(url=url))
        else:
            button = InlineKeyboardButton(
                text=translate(fallback_key),
                callback_data="tariff_topup:list",
            )
        return InlineKeyboardMarkup(inline_keyboard=[[button]])

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
    ) -> None:
        try:
            user = await user_dal.get_user_by_id(session, user_id)
        except Exception:
            logging.exception("TariffTrafficWorker: failed to load user %s for email", user_id)
            return
        if not user:
            return
        await send_user_notification_email(
            settings=self.settings,
            i18n=self.i18n,
            user=user,
            subject_key=subject_key,
            message_text=message_text,
            dashboard_url=subscription_mini_app_topup_url(self.settings, kind),
            cta_label_key=(
                "email_traffic_warning_premium_cta"
                if kind == "premium"
                else "email_traffic_warning_regular_cta"
            ),
            session=session,
            audit_event_type="email_traffic_warning_sent",
            audit_content=f"{audit_content} subject_key={subject_key} warning_key={warning_key}",
        )

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
                        await self._run_db_tick_with_retry(
                            "traffic_period",
                            self.traffic_period_tick,
                        )
                        await self._run_db_tick_with_retry(
                            "legacy_throttle_recovery",
                            self.legacy_throttle_recovery_tick,
                        )
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

    async def _run_db_tick_with_retry(
        self,
        tick_name: str,
        tick: Callable[[AsyncSession], Awaitable[None]],
    ) -> None:
        for attempt in range(1, TARIFF_WORKER_DB_RETRY_ATTEMPTS + 1):
            async with self.session_factory() as session:
                try:
                    await acquire_subscription_background_sync_lock(session)
                    await tick(session)
                    await session.commit()
                    return
                except Exception as exc:
                    await session.rollback()
                    if (
                        attempt < TARIFF_WORKER_DB_RETRY_ATTEMPTS
                        and self._is_retryable_db_exception(exc)
                    ):
                        delay = TARIFF_WORKER_DB_RETRY_BASE_SLEEP_SECONDS * attempt
                        logging.warning(
                            "TariffTrafficWorker %s retrying after database concurrency "
                            "error, attempt %s/%s: %s",
                            tick_name,
                            attempt + 1,
                            TARIFF_WORKER_DB_RETRY_ATTEMPTS,
                            exc,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise

    @staticmethod
    def _is_retryable_db_exception(exc: BaseException) -> bool:
        pending: list[BaseException] = [exc]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)

            sqlstate = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
            if sqlstate in POSTGRES_RETRYABLE_SQLSTATES:
                return True

            error_name = type(current).__name__
            message = str(current).lower()
            if (
                error_name in POSTGRES_RETRYABLE_ERROR_NAMES
                or "deadlock detected" in message
                or "could not serialize access" in message
            ):
                return True

            for attr in ("orig", "__cause__", "__context__"):
                nested = getattr(current, attr, None)
                if isinstance(nested, BaseException):
                    pending.append(nested)

        return False

    @staticmethod
    def _is_trial_subscription(sub: Subscription) -> bool:
        provider = str(getattr(sub, "provider", "") or "").strip().lower()
        status = str(getattr(sub, "status_from_panel", "") or "").strip().upper()
        return provider == "trial" or status == "TRIAL"

    def _trial_premium_tariff(self) -> Optional[_TrialPremiumTariff]:
        premium_squads = self.subscription_service._trial_premium_squad_uuids()
        premium_baseline = self.subscription_service._trial_premium_baseline_bytes()
        if not premium_squads or premium_baseline <= 0:
            return None
        all_squads = self.subscription_service._trial_panel_squad_uuids()
        premium_set = set(premium_squads)
        regular_squads = [uuid for uuid in all_squads if uuid not in premium_set]
        return _TrialPremiumTariff(
            squad_uuids=regular_squads,
            premium_squad_uuids=premium_squads,
            premium_monthly_bytes=premium_baseline,
        )
