"""Idempotent Core grants which can share a transaction with a plugin's ticket ledger."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.promo_code_service import PromoCodeService
from bot.services.promo_effects import PromoEffects
from db.dal import subscription_dal, user_dal
from db.extension_models import ExtensionOperation
from db.models import Subscription

from .commerce import ledger_change
from .contracts import ContractModel, ExtensionError
from .jobs import enqueue_internal, json_object, utc
from .registry import get_registry


class Reward(ContractModel):
    kind: Literal["balance", "days", "traffic", "codes"]
    amount: int = Field(gt=0, le=1_000_000_000_000, strict=True)
    currency: str = Field(default="RUB", pattern=r"^[A-Z]{3,8}$")
    # codes uses amount as fixed subscription days; richer code policies remain plugin-owned.


async def grant(
    session: AsyncSession, *, owner: str, user_id: int, idempotency_key: str, reward: Reward
) -> ExtensionOperation:
    """amount is minor currency units, whole days, bytes, or days on a personal code."""
    async with session.begin_nested():
        return await _grant(
            session, owner=owner, user_id=user_id, idempotency_key=idempotency_key, reward=reward
        )


async def _grant(
    session: AsyncSession, *, owner: str, user_id: int, idempotency_key: str, reward: Reward
) -> ExtensionOperation:
    get_registry().permit(owner, f"rewards.{reward.kind}")
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None or user.is_banned:
        raise ExtensionError("access_denied", 403)
    operation = await enqueue_internal(
        session,
        owner=owner,
        kind="_reward",
        user_id=user_id,
        idempotency_key=idempotency_key,
        payload=reward.model_dump(mode="json"),
    )
    if operation.result_json is not None:
        return operation
    if reward.kind == "balance":
        await ledger_change(
            session,
            user_id=user_id,
            amount_minor=reward.amount,
            currency=reward.currency,
            kind="extension_grant",
            reference=str(operation.id),
            owner=owner,
        )
        operation.state = "succeeded"
        operation.result_json = json_object({"applied": True})
    elif reward.kind == "codes":
        if reward.amount > 36500:
            raise ExtensionError("invalid_extension_reward", 400)
        code = await PromoCodeService.issue_code(
            session,
            effects=PromoEffects(bonus_days=reward.amount),
            code=None,
            max_activations=1,
            valid_until=None,
            origin="extension",
            created_by_admin_id=None,
            user_id=user_id,
        )
        operation.state = "succeeded"
        operation.result_json = json_object({"applied": True, "code": str(code.code)})
    else:
        active = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
        if active is None or utc(active.end_date) <= datetime.now(UTC):
            raise ExtensionError("extension_reward_requires_subscription")
        subscription = await session.scalar(
            select(Subscription)
            .where(Subscription.subscription_id == active.subscription_id)
            .with_for_update()
        )
        if subscription is None:
            raise ExtensionError("extension_reward_requires_subscription")
        if reward.kind == "days":
            if reward.amount > 36500:
                raise ExtensionError("invalid_extension_reward", 400)
            subscription.end_date = utc(subscription.end_date) + timedelta(days=reward.amount)
        else:
            traffic = int(subscription.regular_bonus_bytes or 0) + reward.amount
            if traffic > 2**63 - 1:
                raise ExtensionError("invalid_extension_reward", 400)
            subscription.regular_bonus_bytes = traffic
        operation.result_json = json_object(
            {"applied": True, "subscription_id": int(subscription.subscription_id)}
        )
    await session.flush()
    return operation
