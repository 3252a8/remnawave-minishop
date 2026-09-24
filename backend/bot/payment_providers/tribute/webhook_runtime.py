from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import subscription_dal, tribute_dal, user_dal
from db.models import User

from ..shared import PaymentSuccessOutcome, PaymentSuccessRequest
from .config import TRIBUTE_PROVIDER, TributeConfig

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object


class TributeWebhookRuntime:
    """State and hooks shared by the focused Tribute webhook mixins."""

    bot: Bot
    settings: Settings
    config: TributeConfig
    i18n: JsonI18n
    async_session_factory: sessionmaker
    subscription_service: SubscriptionService
    referral_service: ReferralService

    async def _finalize_successful_payment(
        self,
        request: PaymentSuccessRequest,
    ) -> PaymentSuccessOutcome | None:
        raise NotImplementedError

    async def _cancel_shop_order(self, order_uuid: str) -> bool:
        """Cancel a conflicting provider-side recurrence."""

        raise NotImplementedError

    async def _refund_shop_order_exact_sell(
        self,
        order_uuid: str,
        *,
        expected_amount: Decimal,
        expected_currency: str,
    ) -> str | None:
        """Refund exactly one sell matching the server-created payment."""

        raise NotImplementedError

    @staticmethod
    async def _lock_user_for_telegram_id(
        session: AsyncSession,
        telegram_user_id: int,
    ) -> User | None:
        """Resolve the local account a Creator webhook is about, then lock it.

        Tribute only knows the Telegram ID. That is not this deployment's user
        identity: ``User.user_id`` is the canonical key every payment,
        entitlement and duplicate-recurrence check is written against, and the
        two differ for an account that started outside Telegram. Locking must
        therefore happen on the row the lookup found, never on the raw
        Telegram ID.

        Imported rows without an explicit Telegram link require separate
        identity reconciliation before a webhook can grant access.
        """

        db_user = await user_dal.get_user_by_telegram_id(session, int(telegram_user_id))
        if db_user is None:
            return None
        return await user_dal.lock_user_by_id(session, int(db_user.user_id))

    @staticmethod
    async def _enable_local_auto_renew(
        session: AsyncSession,
        *,
        user_id: int,
        tariff_key: str,
    ) -> None:
        subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            user_id,
        )
        if (
            subscription is not None
            and str(subscription.provider or "").lower() == TRIBUTE_PROVIDER
            and str(subscription.tariff_key or "") == tariff_key
        ):
            await subscription_dal.set_auto_renew(
                session,
                int(subscription.subscription_id),
                True,
            )

    @staticmethod
    async def _disable_local_auto_renew(
        session: AsyncSession,
        *,
        user_id: int,
        tariff_key: str,
    ) -> None:
        subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            user_id,
        )
        if (
            subscription is not None
            and str(subscription.provider or "").lower() == TRIBUTE_PROVIDER
            and str(subscription.tariff_key or "") == tariff_key
        ):
            await subscription_dal.set_auto_renew(
                session,
                int(subscription.subscription_id),
                False,
            )

    @classmethod
    async def _sync_shop_auto_renew(
        cls,
        session: AsyncSession,
        *,
        user_id: int,
        tariff_key: str,
        order_uuid: str,
    ) -> None:
        state = await tribute_dal.get_shop_recurring_state(session, order_uuid)
        if state == "active":
            await cls._enable_local_auto_renew(
                session,
                user_id=user_id,
                tariff_key=tariff_key,
            )
        elif state == "inactive":
            await cls._disable_local_auto_renew(
                session,
                user_id=user_id,
                tariff_key=tariff_key,
            )
