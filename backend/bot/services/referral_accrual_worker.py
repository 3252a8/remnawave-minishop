"""Recover unpaid period obligations independently of provider callback replay."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.infra import events
from bot.infra.event_payloads import ReferralBonusGrantedPayload
from bot.services.referral_accruals import utc_date
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.subscription_periods import days_to_legacy_months
from db.dal import subscription_dal, tariff_dal, user_dal
from db.models import Payment
from db.referral_accrual_models import ReferralPeriodAccrual

logger = logging.getLogger(__name__)


class ReferralAccrualWorker:
    def __init__(
        self,
        session_factory: sessionmaker,
        referral_service: ReferralService,
        subscription_service: SubscriptionService,
    ) -> None:
        self.session_factory = session_factory
        self.referral_service = referral_service
        self.subscription_service = subscription_service

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Invitation accrual worker tick failed")
            await asyncio.sleep(60)

    async def tick(self) -> None:
        await self._recover_decisions()
        async with self.session_factory() as session:
            candidates = (
                await session.execute(
                    select(ReferralPeriodAccrual.accrual_id, ReferralPeriodAccrual.user_id)
                    .where(
                        ReferralPeriodAccrual.state == "pending",
                        or_(
                            ReferralPeriodAccrual.next_attempt_at.is_(None),
                            ReferralPeriodAccrual.next_attempt_at <= datetime.now(UTC),
                        ),
                    )
                    .order_by(ReferralPeriodAccrual.accrual_id)
                    .limit(50)
                )
            ).all()
        for accrual_id, user_id in candidates:
            try:
                await self._apply(int(accrual_id), int(user_id))
            except Exception:
                logger.exception("Period accrual %s deferred after failure", accrual_id)

    async def _recover_decisions(self) -> None:
        async with self.session_factory() as session:
            payments = (
                await session.scalars(
                    select(Payment)
                    .where(
                        Payment.status == "succeeded",
                        Payment.referral_accrual_processed.is_(False),
                    )
                    .order_by(Payment.updated_at, Payment.payment_id)
                    .limit(50)
                )
            ).all()
            payment_ids = [int(payment.payment_id) for payment in payments]
        for payment_id in payment_ids:
            try:
                async with self.session_factory() as session:
                    payment = await session.scalar(
                        select(Payment)
                        .where(
                            Payment.payment_id == payment_id,
                            Payment.status == "succeeded",
                            Payment.referral_accrual_processed.is_(False),
                        )
                        .with_for_update(skip_locked=True)
                    )
                    if payment is None:
                        continue
                    await user_dal.lock_user_by_id(session, int(payment.user_id))
                    mode = str(payment.sale_mode or "").split("@", 1)[0].split("|", 1)[0]
                    if mode == "subscription" and float(payment.amount) > 0:
                        days = int(payment.subscription_duration_days or 0) or None
                        months = (
                            int(payment.subscription_duration_months or 0)
                            or (days_to_legacy_months(days) if days else None)
                            or 1
                        )
                        await self.referral_service.apply_referral_bonuses_for_payment(
                            session,
                            int(payment.user_id),
                            months,
                            current_payment_db_id=payment_id,
                            skip_if_active_before_payment=False,
                            tariff_key=payment.tariff_key,
                            duration_days=days,
                            defer=True,
                            recover=True,
                        )
                    payment.referral_accrual_processed = True
                    await session.commit()
            except Exception:
                logger.exception("Accrual decision recovery failed for payment %s", payment_id)

    async def _locked_accrual(
        self, session: AsyncSession, accrual_id: int
    ) -> ReferralPeriodAccrual | None:
        return await session.scalar(
            select(ReferralPeriodAccrual)
            .where(ReferralPeriodAccrual.accrual_id == accrual_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def _apply(self, accrual_id: int, user_id: int) -> None:
        lease_token = str(uuid4())
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            user = await user_dal.lock_user_by_id(session, user_id)
            accrual = await self._locked_accrual(session, accrual_id)
            if user is None or accrual is None or accrual.state != "pending":
                return
            due = utc_date(accrual.next_attempt_at)
            if due is not None and due > now:
                return
            if accrual.target_end_date is None:
                sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
                previous = utc_date(getattr(sub, "end_date", None)) or now
                base = max(now, previous, utc_date(user.period_accrual_reserved_until) or now)
                target = base + timedelta(days=int(accrual.days))
                accrual.target_end_date = target
                user.period_accrual_reserved_until = target
                if sub is not None:
                    sub.end_date = target
                    await tariff_dal.extend_hwid_device_purchases_for_subscription_bonus(
                        session,
                        subscription_id=int(sub.subscription_id),
                        at=now,
                        subscription_end_before=previous,
                        delta=timedelta(days=int(accrual.days)),
                    )
            accrual.lease_token = lease_token
            accrual.attempts = int(accrual.attempts or 0) + 1
            accrual.next_attempt_at = now + timedelta(minutes=5)
            await session.commit()
        # The target and local reservation survive a process crash or ambiguous HTTP result.
        async with self.session_factory() as session:
            await user_dal.lock_user_by_id(session, user_id)
            accrual = await self._locked_accrual(session, accrual_id)
            if accrual is None or accrual.state != "pending" or accrual.lease_token != lease_token:
                return
            try:
                end_date = await self.subscription_service.extend_active_subscription_days(
                    session,
                    user_id=user_id,
                    bonus_days=int(accrual.days),
                    reason="referral period accrual",
                    tariff_key=accrual.tariff_key,
                    target_end_date=utc_date(accrual.target_end_date),
                    extend_hwid_devices=False,
                )
            except Exception:
                # A failed transaction is retried after the persisted lease expires.
                await session.rollback()
                raise
            if end_date is None:
                accrual.last_error = "panel_confirmation_unavailable"
                accrual.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 60 * 2 ** min(6, int(accrual.attempts)))
                )
                await session.commit()
                return
            accrual.state = "applied"
            accrual.applied_at = datetime.now(UTC)
            accrual.last_error = None
            payload = ReferralBonusGrantedPayload(
                referee_user_id=int(accrual.referee_user_id),
                referee_bonus_days=int(accrual.days) if accrual.role == "referee" else None,
                referee_new_end_date=end_date if accrual.role == "referee" else None,
                inviter_bonus_applied=accrual.role == "inviter",
                inviter_user_id=user_id if accrual.role == "inviter" else None,
                inviter_bonus_days=int(accrual.days) if accrual.role == "inviter" else None,
                inviter_bonus_end_date=end_date if accrual.role == "inviter" else None,
                inviter_bonus_kind="extended" if accrual.role == "inviter" else None,
                payment_db_id=int(accrual.payment_id),
                tariff_key=accrual.tariff_key,
                one_bonus_per_referee=accrual.one_time_referee_id is not None,
                reason="payment",
            )
            await session.commit()
        with contextlib.suppress(Exception):
            await events.emit_model(payload)
