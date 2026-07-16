import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import subscription_dal, tariff_dal, user_dal

from .panel_identity import PanelUserCreateOptions

logger = logging.getLogger(__name__)


async def active_subscription_tariff_key(session: AsyncSession, user_id: int) -> str | None:
    user = await user_dal.get_user_by_id(session, user_id)
    active_sub = (
        await subscription_dal.get_active_subscription_by_user_id(
            session,
            user_id,
            user.panel_user_uuid,
        )
        if user and user.panel_user_uuid
        else None
    )
    return active_sub.tariff_key if active_sub else None


def panel_user_create_options(
    expire_at: datetime,
    traffic_limit_bytes: int,
    traffic_limit_strategy: str,
    hwid_device_limit: int | None,
    squad_uuids: list[str] | None,
    external_squad_uuid: str | None,
) -> PanelUserCreateOptions:
    return PanelUserCreateOptions(
        default_expire_days=1,
        expire_at=expire_at,
        default_traffic_limit_bytes=traffic_limit_bytes,
        default_traffic_limit_strategy=traffic_limit_strategy,
        hwid_device_limit=hwid_device_limit,
        specific_squad_uuids=tuple(squad_uuids or ()),
        external_squad_uuid=external_squad_uuid,
    )


def bonus_provider_for_reason(reason: str) -> str:
    if "referral" in reason:
        return "referral"
    if "promo" in reason:
        return "promo"
    if "admin" in reason:
        return "admin"
    return "bonus"


async def record_tariff_change_best_effort(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    user_id: int,
) -> None:
    try:
        savepoint = await session.begin_nested()
        try:
            await tariff_dal.create_tariff_change(session, payload)
        except Exception:
            await savepoint.rollback()
            raise
        else:
            await savepoint.commit()
    except Exception:
        logger.exception(
            "Failed to record tariff change audit for user %s; entitlement is kept.",
            user_id,
        )


async def record_traffic_topup_best_effort(
    session: AsyncSession,
    *,
    subscription_id: int,
    payment_id: int | None,
    purchased_bytes: int,
    kind: str,
) -> None:
    try:
        savepoint = await session.begin_nested()
        try:
            await tariff_dal.create_traffic_topup(
                session,
                subscription_id=subscription_id,
                payment_id=payment_id,
                purchased_bytes=purchased_bytes,
                kind=kind,
            )
        except Exception:
            await savepoint.rollback()
            raise
        else:
            await savepoint.commit()
    except Exception:
        logger.exception(
            "Failed to record %s audit for subscription %s; entitlement is kept.",
            kind,
            subscription_id,
        )
