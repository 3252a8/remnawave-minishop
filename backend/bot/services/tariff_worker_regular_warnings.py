import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.tariff_worker_shared import deliver_traffic_warning
from db.dal import tariff_dal
from db.models import Subscription

logger = logging.getLogger(__name__)


async def _log_user_message_delivery(*args: Any, **kwargs: Any) -> None:
    from . import tariff_worker_regular

    await tariff_worker_regular.log_user_message_delivery(*args, **kwargs)


class _RegularTariff(Protocol):
    billing_model: str
    monthly_bytes: int

    def name(self, lang: str, fallback: str = "ru") -> str: ...


class TariffWorkerRegularWarningMixin:
    settings: Any
    i18n: Any
    bot: Any

    if TYPE_CHECKING:

        async def _user_lang(self, session: AsyncSession, user_id: int) -> str: ...
        def _usage_placeholders(self, *args: Any, **kwargs: Any) -> dict: ...
        def _traffic_next_reset_note(self, *args: Any, **kwargs: Any) -> str: ...
        def _period_tariff_traffic_strategy(self, *args: Any, **kwargs: Any) -> str: ...
        def _traffic_topup_markup(self, *args: Any, **kwargs: Any) -> Any: ...
        async def _send_traffic_warning_email(self, *args: Any, **kwargs: Any) -> None: ...

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
        traffic_strategy: str | None = None,
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
                # The panel performs the reset, so its effective strategy decides
                # whether a reset date can be promised at all (NO_RESET: none).
                traffic_strategy=traffic_strategy or self._period_tariff_traffic_strategy(tariff),
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
                settings=self.settings,
                user_id=sub.user_id,
                bot=self.bot,
                text=text,
                markup=markup,
                audit_content=audit_content,
                audit_logger=_log_user_message_delivery,
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
