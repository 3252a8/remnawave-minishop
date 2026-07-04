import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.message_audit import log_user_message_delivery
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.date_utils import month_start
from bot.utils.traffic_reset import (
    panel_traffic_limit_strategy,
    previous_traffic_reset,
    traffic_period_starts_match,
)
from config.settings import Settings
from db.dal import tariff_dal
from db.models import Subscription

from .tariff_worker_shared import (
    PREMIUM_WARNING_DEPLETED_LEVEL,
    PREMIUM_WARNING_LEVEL_OFFSET,
    TARIFF_WORKER_SQUAD_CONFIRMATION_CACHE_TTL_SECONDS,
    deliver_traffic_warning,
    fmt_bytes,
)

logger = logging.getLogger(__name__)


class _PremiumTariff(Protocol):
    key: str
    premium_monthly_bytes: int
    premium_squad_uuids: list[str]

    def name(self, lang: str, fallback: str = "ru") -> str: ...


class TariffWorkerPremiumMixin:
    settings: Settings
    panel_service: PanelApiService
    subscription_service: SubscriptionService
    bot: Bot | None
    i18n: JsonI18n | None
    _premium_nodes_cache: dict[tuple[str, ...], dict[str, Any]]
    _premium_node_usage_tick_cache: dict[
        tuple[str, str, str],
        dict[str, dict[Any, int]] | None,
    ]
    _premium_squad_match_cache: dict[tuple[str, tuple[str, ...]], float]

    if TYPE_CHECKING:
        PREMIUM_RESET_NOTICE_LEVEL: int

        async def _user_lang(self, session: AsyncSession, user_id: int) -> str: ...
        def _period_tariff_traffic_strategy(self) -> str: ...
        def _usage_placeholders(self, used_bytes: int, limit_bytes: int) -> dict: ...
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
        def _panel_next_traffic_reset_at(
            self,
            panel_user_data: dict[str, Any] | None,
            *,
            now: datetime | None = None,
        ) -> datetime | None: ...
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

    async def _sync_premium_squad_limit(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff: _PremiumTariff,
        now: datetime,
        *,
        panel_username: str | None = None,
        panel_user_dict: dict[str, Any] | None = None,
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

        premium_panel_user_dict = (
            panel_user_dict
            if str(getattr(tariff, "billing_model", "") or "").lower() == "period"
            else None
        )
        premium_period_start = self.subscription_service._premium_accounting_period_start(
            sub,
            now,
            panel_user_data=premium_panel_user_dict,
        )
        effective_strategy = panel_traffic_limit_strategy(
            premium_panel_user_dict,
            self._period_tariff_traffic_strategy(),
        )
        is_trial_premium_tariff = bool(getattr(tariff, "key", "") == "trial")
        previous_premium_period_start = getattr(sub, "premium_period_start_at", None)
        same_period = self._same_premium_period(
            previous_premium_period_start,
            premium_period_start,
            traffic_strategy=effective_strategy,
        )
        if (
            effective_strategy == "NO_RESET"
            and previous_premium_period_start is not None
            and premium_period_start != month_start(now)
        ):
            same_period = True
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
            logger.warning("Premium squads for tariff %s have no accessible nodes", tariff.key)
            return

        start_date = premium_period_start.date().isoformat()
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

        panel_next_reset_at = self._panel_next_traffic_reset_at(
            premium_panel_user_dict,
            now=now,
        )

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

        should_limit = False if premium_unlimited_override else premium_used >= premium_limit
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
        if not premium_unlimited_override and not is_trial_premium_tariff:
            await self._maybe_warn_premium_squad_limit(
                session,
                sub,
                tariff,
                premium_used,
                premium_limit,
                premium_period_start,
                next_reset_at=panel_next_reset_at,
            )
        if not panel_needs_update:
            if not premium_unlimited_override and not is_trial_premium_tariff:
                await self._maybe_send_premium_reset_notice(
                    session,
                    sub,
                    tariff,
                    used=int(premium_used),
                    limit=int(premium_limit),
                    period_start_at=premium_period_start,
                    previous_period_start=previous_premium_period_start,
                    traffic_strategy=effective_strategy,
                )
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
        if updated_panel_user and not updated_panel_user.get("error"):
            self._remember_premium_squad_match(squad_match_cache_key)
            if not premium_unlimited_override and not is_trial_premium_tariff:
                await self._maybe_send_premium_reset_notice(
                    session,
                    sub,
                    tariff,
                    used=int(premium_used),
                    limit=int(premium_limit),
                    period_start_at=premium_period_start,
                    previous_period_start=previous_premium_period_start,
                    traffic_strategy=effective_strategy,
                )
        logger.info(
            "Premium squad access %s for user %s tariff %s: %s/%s bytes",
            "limited" if should_limit else "restored",
            sub.user_id,
            tariff.key,
            premium_used,
            premium_limit,
        )

    async def _maybe_send_premium_reset_notice(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff: _PremiumTariff,
        *,
        used: int,
        limit: int,
        period_start_at: datetime,
        previous_period_start: datetime | None,
        traffic_strategy: str,
    ) -> None:
        if traffic_strategy == "NO_RESET":
            return
        if not self._traffic_notice_channels_available():
            return
        if not self._traffic_reset_notice_is_reassuring(used, limit):
            return

        expected_previous_period = previous_traffic_reset(
            period_start_at,
            traffic_strategy,
        )
        if expected_previous_period is None:
            return
        if not self._same_premium_period(
            previous_period_start,
            expected_previous_period,
            traffic_strategy=traffic_strategy,
        ):
            return
        was_warned_previous_period = await tariff_dal.has_warning_level_between(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=expected_previous_period,
            min_level=PREMIUM_WARNING_LEVEL_OFFSET,
            max_level=PREMIUM_WARNING_DEPLETED_LEVEL,
        )
        if not was_warned_previous_period:
            return
        warned_current_period = await tariff_dal.has_warning_level_between(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=period_start_at,
            min_level=PREMIUM_WARNING_LEVEL_OFFSET,
            max_level=PREMIUM_WARNING_DEPLETED_LEVEL,
        )
        if warned_current_period:
            return
        reset_notice = await tariff_dal.get_warning(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=period_start_at,
            level=self.PREMIUM_RESET_NOTICE_LEVEL,
        )
        if reset_notice:
            return
        await tariff_dal.create_warning(
            session,
            subscription_id=sub.subscription_id,
            period_start_at=period_start_at,
            level=self.PREMIUM_RESET_NOTICE_LEVEL,
            traffic_limit_bytes=None,
        )

        user_lang = await self._user_lang(session, sub.user_id)
        _ = (
            (lambda k, **kw: self.i18n.gettext(user_lang, k, **kw))
            if self.i18n
            else (lambda k, **kw: k)
        )
        servers = await self._premium_servers_text(tariff, _)
        usage = self._usage_placeholders(used, limit)
        text = _(
            "traffic_reset_premium_notification",
            tariff_name=hd.quote(str(tariff.name(user_lang))),
            servers=servers,
            **usage,
        )
        warning_key = "traffic_reset_premium"
        audit_content = (
            f"kind=premium warning_key={warning_key} used_bytes={int(used)} "
            f"limit_bytes={int(limit)} period_start={period_start_at.isoformat()}"
        )
        await self._send_traffic_reset_notice(
            session,
            sub=sub,
            subject_key="email_traffic_reset_premium_subject",
            message_text=text,
            kind="premium",
            warning_key=warning_key,
            audit_content=audit_content,
        )

    async def _premium_servers_text(self, tariff: _PremiumTariff, translate: Any) -> str:
        access = await self.subscription_service.premium_access_for_tariff(tariff)
        labels = access.get("node_labels") or access.get("squad_labels") or []
        if not labels:
            return translate("traffic_warning_premium_generic_servers")
        visible = [hd.quote(str(x)) for x in labels[:8]]
        servers = "\n".join(f"• {label}" for label in visible)
        if len(labels) > len(visible):
            more = len(labels) - len(visible)
            servers += "\n" + translate("traffic_warning_premium_servers_more", count=more)
        return servers

    async def _get_full_panel_user_for_squad_confirmation(
        self,
        panel_user_uuid: str,
    ) -> dict[str, Any] | None:
        try:
            panel_user = await self.panel_service.get_user_by_uuid(
                panel_user_uuid,
                log_response=False,
            )
            return panel_user if isinstance(panel_user, dict) else None
        except Exception:
            logger.exception(
                "TariffTrafficWorker: failed to confirm panel squads for user %s",
                panel_user_uuid,
            )
            return None

    def _same_premium_period(
        self,
        value: datetime | None,
        premium_period_start: datetime,
        *,
        traffic_strategy: str | None = None,
    ) -> bool:
        if value is None:
            return False
        try:
            return traffic_period_starts_match(
                value,
                premium_period_start,
                traffic_strategy or self._period_tariff_traffic_strategy(),
            )
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
        logger.warning(
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
    ) -> int | None:
        if not subscription_id or not isinstance(session, AsyncSession):
            return None
        try:
            total = await tariff_dal.sum_traffic_topups(
                session,
                subscription_id=subscription_id,
                kinds=["premium_topup", "admin_premium_topup"],
                created_at_gte=premium_period_start,
            )
            return int(total) if total is not None else None
        except Exception:
            logger.exception(
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
            time.monotonic() - float(cached_at) < TARIFF_WORKER_SQUAD_CONFIRMATION_CACHE_TTL_SECONDS
        )

    def _remember_premium_squad_match(self, cache_key: tuple[str, tuple[str, ...]]) -> None:
        self._premium_squad_match_cache[cache_key] = time.monotonic()

    @classmethod
    def _panel_active_squad_uuid_set(
        cls,
        panel_user_dict: dict | None,
    ) -> tuple[bool, set[str]]:
        current_known, current_raw = cls._panel_active_squads_raw(panel_user_dict)
        return current_known, cls._internal_squad_uuid_set(current_raw)

    @staticmethod
    def _panel_active_squads_raw(panel_user_dict: dict | None) -> tuple[bool, Any]:
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
        current_panel_user: dict | None,
        reasons: list[str],
        panel_view: str,
    ) -> None:
        current_known, current_set = self._panel_active_squad_uuid_set(current_panel_user)
        desired_set = self._internal_squad_uuid_set(update_payload.get("activeInternalSquads"))
        fields = "none" if current_known and current_set == desired_set else "activeInternalSquads"
        logger.info(
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
            "activeInternalSquads:"
            f"{self._format_squad_uuid_set(current_set if current_known else None)}"
            f"->{self._format_squad_uuid_set(desired_set)}",
        )

    @staticmethod
    def _internal_squad_uuid_set(raw: object) -> set[str]:
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
    def _format_squad_uuid_set(value: set[str] | None) -> str:
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
    def _premium_next_period_available_bytes(sub: Subscription, tariff: _PremiumTariff) -> int:
        baseline = int(
            getattr(sub, "premium_baseline_bytes", 0)
            or getattr(tariff, "premium_monthly_bytes", 0)
            or 0
        )
        topup_balance = int(getattr(sub, "premium_topup_balance_bytes", 0) or 0)
        bonus = int(getattr(sub, "premium_bonus_bytes", 0) or 0)
        return max(0, baseline) + max(0, topup_balance) + max(0, bonus)

    _fmt_bytes = staticmethod(fmt_bytes)

    async def _maybe_warn_premium_squad_limit(
        self,
        session: AsyncSession,
        sub: Subscription,
        tariff: _PremiumTariff,
        used: int,
        limit: int,
        period_start_at: datetime,
        *,
        next_reset_at: datetime | None = None,
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
            user_lang = await self._user_lang(session, sub.user_id)
            _ = (
                (lambda k, _user_lang=user_lang, **kw: self.i18n.gettext(_user_lang, k, **kw))
                if self.i18n
                else (lambda k, **kw: k)
            )
            servers = await self._premium_servers_text(tariff, _)
            usage = self._usage_placeholders(used_val, limit_val)
            reset_note = self._traffic_next_reset_note(
                _,
                kind="premium",
                period_start_at=period_start_at,
                reset_available_bytes=self._premium_next_period_available_bytes(sub, tariff),
                user_lang=user_lang,
                next_reset_at=next_reset_at,
            )
            text = _(
                "traffic_warning_premium_depleted",
                tariff_name=hd.quote(str(tariff.name(user_lang))),
                servers=servers,
                **usage,
            )
            if reset_note:
                text = f"{text}\n\n{reset_note}"
            warning_key = "traffic_warning_premium_depleted"
            audit_content = (
                f"kind=premium warning_key={warning_key} "
                f"used_bytes={used_val} limit_bytes={limit_val}"
            )
            markup = self._traffic_topup_markup(user_lang, "premium") if self.bot else None
            await deliver_traffic_warning(
                session,
                user_id=sub.user_id,
                bot=self.bot,
                text=text,
                markup=markup,
                audit_content=audit_content,
                audit_logger=log_user_message_delivery,
                email_sender=self._send_traffic_warning_email,
                subject_key="email_traffic_warning_premium_depleted_subject",
                kind="premium",
                warning_key=warning_key,
                logger=logger,
                telegram_failure_message=(
                    "Failed to send premium traffic depleted warning to user %s"
                ),
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
            user_lang = await self._user_lang(session, sub.user_id)
            _ = (
                (lambda k, _user_lang=user_lang, **kw: self.i18n.gettext(_user_lang, k, **kw))
                if self.i18n
                else (lambda k, **kw: k)
            )
            servers = await self._premium_servers_text(tariff, _)
            left_pct = max(0, 100 - int(level))
            usage = self._usage_placeholders(used_val, limit_val)
            reset_note = self._traffic_next_reset_note(
                _,
                kind="premium",
                period_start_at=period_start_at,
                reset_available_bytes=self._premium_next_period_available_bytes(sub, tariff),
                user_lang=user_lang,
                next_reset_at=next_reset_at,
            )
            text = _(
                "traffic_warning_premium_almost",
                tariff_name=hd.quote(str(tariff.name(user_lang))),
                left_pct=left_pct,
                servers=servers,
                **usage,
            )
            if reset_note:
                text = f"{text}\n\n{reset_note}"
            warning_key = "traffic_warning_premium_almost"
            audit_content = (
                f"kind=premium warning_key={warning_key} level={int(level)} "
                f"used_bytes={used_val} limit_bytes={limit_val}"
            )
            markup = self._traffic_topup_markup(user_lang, "premium") if self.bot else None
            await deliver_traffic_warning(
                session,
                user_id=sub.user_id,
                bot=self.bot,
                text=text,
                markup=markup,
                audit_content=audit_content,
                audit_logger=log_user_message_delivery,
                email_sender=self._send_traffic_warning_email,
                subject_key="email_traffic_warning_premium_almost_subject",
                kind="premium",
                warning_key=warning_key,
                logger=logger,
                telegram_failure_message="Failed to send premium traffic warning to user %s",
            )

    async def _premium_node_uuids_for_tariff(self, tariff: _PremiumTariff) -> list[str]:
        cache_key = tuple(sorted(tariff.premium_squad_uuids or []))
        cached = self._premium_nodes_cache.get(cache_key)
        now_ts = datetime.now(UTC).timestamp()
        cached_nodes = cached.get("nodes") if cached else None
        cached_ts = cached.get("ts") if cached else None
        if cached and cached_nodes is not None and now_ts - float(cached_ts or 0) < 600:
            return [str(node) for node in cached_nodes] if isinstance(cached_nodes, list) else []

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
        panel_username: str | None = None,
    ) -> int | None:
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
    ) -> dict | None:
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
    def _build_premium_usage_lookup(stats: dict | None) -> dict | None:
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
            user_obj_raw = entry.get("user")
            user_obj: dict[str, Any] = user_obj_raw if isinstance(user_obj_raw, dict) else {}
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
