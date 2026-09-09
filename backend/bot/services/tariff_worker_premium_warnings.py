import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.tariff_worker_shared import (
    PREMIUM_WARNING_DEPLETED_LEVEL,
    PREMIUM_WARNING_LEVEL_OFFSET,
    deliver_traffic_warning,
)
from db.dal import tariff_dal
from db.models import Subscription

logger = logging.getLogger(__name__)


async def _log_user_message_delivery(*args: Any, **kwargs: Any) -> None:
    from . import tariff_worker_premium

    await tariff_worker_premium.log_user_message_delivery(*args, **kwargs)


class _PremiumTariff(Protocol):
    key: str
    premium_monthly_bytes: int
    premium_squad_uuids: list[str]

    def name(self, lang: str, fallback: str = "ru") -> str: ...


class TariffWorkerPremiumWarningMixin:
    settings: Any
    i18n: Any
    bot: Any

    if TYPE_CHECKING:

        async def _user_lang(self, session: AsyncSession, user_id: int) -> str: ...
        async def _premium_servers_text(self, *args: Any, **kwargs: Any) -> str: ...
        def _usage_placeholders(self, *args: Any, **kwargs: Any) -> dict: ...
        def _traffic_next_reset_note(self, *args: Any, **kwargs: Any) -> str: ...
        def _premium_next_period_available_bytes(self, *args: Any, **kwargs: Any) -> int: ...
        def _traffic_topup_markup(self, *args: Any, **kwargs: Any) -> Any: ...
        async def _send_traffic_warning_email(self, *args: Any, **kwargs: Any) -> None: ...

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
        traffic_strategy: str,
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
                traffic_strategy=traffic_strategy,
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
                settings=self.settings,
                user_id=sub.user_id,
                bot=self.bot,
                text=text,
                markup=markup,
                audit_content=audit_content,
                audit_logger=_log_user_message_delivery,
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
                traffic_strategy=traffic_strategy,
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
                settings=self.settings,
                user_id=sub.user_id,
                bot=self.bot,
                text=text,
                markup=markup,
                audit_content=audit_content,
                audit_logger=_log_user_message_delivery,
                email_sender=self._send_traffic_warning_email,
                subject_key="email_traffic_warning_premium_almost_subject",
                kind="premium",
                warning_key=warning_key,
                logger=logger,
                telegram_failure_message="Failed to send premium traffic warning to user %s",
            )
