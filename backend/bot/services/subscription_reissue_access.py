"""Persist rotation intent and recover ambiguous external results."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.referral_accruals import utc_date
from bot.utils.mini_app_url import subscription_public_install_url
from config.settings import Settings
from db.dal import subscription_dal, user_dal
from db.subscription_access_rotation_models import SubscriptionAccessRotation


class AccessRotationBusy(Exception):
    """Another process owns the bounded external request lease."""


async def _rotation(
    session: AsyncSession, panel_user_uuid: str
) -> SubscriptionAccessRotation | None:
    return await session.scalar(
        select(SubscriptionAccessRotation)
        .where(SubscriptionAccessRotation.panel_user_uuid == panel_user_uuid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _bind_result(
    session: AsyncSession,
    *,
    user_id: int,
    panel_user_uuid: str,
    updated: dict[str, Any],
    settings: Settings,
) -> str | None:
    short_uuid = str(updated.get("shortUuid") or "").strip()
    subscription = await subscription_dal.get_active_subscription_by_user_id(
        session, user_id, panel_user_uuid
    )
    if subscription is None or not short_uuid:
        raise ValueError("subscription_not_active")
    subscription.panel_subscription_uuid = short_uuid
    token = await subscription_dal.ensure_install_share_token(
        session, subscription, panel_short_uuid=short_uuid
    )
    if settings.SUBSCRIPTION_GATEWAY_ENABLED and settings.SUBSCRIPTION_LINK_MODE == "minishop":
        return subscription_public_install_url(settings, token)
    return None


async def reissue_subscription_access(
    session: AsyncSession,
    panel_service: Any,
    *,
    user_id: int,
    panel_user_uuid: str,
    settings: Settings,
) -> tuple[dict[str, Any] | None, str | None]:
    """A retry observes the current panel UUID before attempting another revoke."""
    await user_dal.lock_user_by_id(session, user_id)
    subscription = await subscription_dal.get_active_subscription_by_user_id(
        session, user_id, panel_user_uuid
    )
    if subscription is None:
        return None, None
    now = datetime.now(UTC)
    rotation = await _rotation(session, panel_user_uuid)
    completed_at = utc_date(rotation.completed_at) if rotation is not None else None
    if (
        rotation is not None
        and rotation.state == "completed"
        and completed_at
        and now - completed_at < timedelta(seconds=15)
    ):
        async with asyncio.timeout(45):
            updated = await panel_service.get_user_by_uuid(panel_user_uuid, use_cache=False)
        if not isinstance(updated, dict) or updated.get("shortUuid") != rotation.new_short_uuid:
            return None, None
        url = await _bind_result(
            session,
            user_id=user_id,
            panel_user_uuid=panel_user_uuid,
            updated=updated,
            settings=settings,
        )
        await session.commit()
        return updated, url
    if (
        rotation is not None
        and rotation.state == "pending"
        and (utc_date(rotation.lease_until) or now) > now
    ):
        raise AccessRotationBusy()
    lease_token = str(uuid4())
    baseline_short_uuid = str(subscription.panel_subscription_uuid or "")
    if rotation is None or rotation.state == "completed":
        async with asyncio.timeout(45):
            baseline = await panel_service.get_user_by_uuid(panel_user_uuid, use_cache=False)
        if not isinstance(baseline, dict) or not baseline.get("shortUuid"):
            return None, None
        baseline_short_uuid = str(baseline["shortUuid"])
    if rotation is None:
        rotation = SubscriptionAccessRotation(
            panel_user_uuid=panel_user_uuid,
            user_id=user_id,
            old_short_uuid=baseline_short_uuid,
            state="pending",
        )
        session.add(rotation)
    elif rotation.state == "completed":
        rotation.old_short_uuid = baseline_short_uuid
        rotation.state = "pending"
        rotation.new_short_uuid = None
        rotation.completed_at = None
    rotation.lease_token = lease_token
    rotation.lease_until = datetime.now(UTC) + timedelta(seconds=90)
    old_short_uuid = str(rotation.old_short_uuid)
    await subscription_dal.revoke_install_share_tokens_for_panel_user(session, panel_user_uuid)
    await session.commit()
    try:
        async with asyncio.timeout(45):
            updated = await panel_service.get_user_by_uuid(panel_user_uuid, use_cache=False)
            if not isinstance(updated, dict) or not updated.get("shortUuid"):
                updated = None
            elif str(updated["shortUuid"]) == old_short_uuid:
                await panel_service.revoke_user_subscription(panel_user_uuid)
                updated = await panel_service.get_user_by_uuid(panel_user_uuid, use_cache=False)
            if (
                not isinstance(updated, dict)
                or not updated.get("shortUuid")
                or str(updated["shortUuid"]) == old_short_uuid
            ):
                updated = None
    except Exception:
        updated = None
    await user_dal.lock_user_by_id(session, user_id)
    rotation = await _rotation(session, panel_user_uuid)
    if rotation is None or rotation.lease_token != lease_token:
        raise AccessRotationBusy()
    if updated is None:
        rotation.lease_until = datetime.now(UTC)
        await session.commit()
        return None, None
    await subscription_dal.revoke_install_share_tokens_for_panel_user(session, panel_user_uuid)
    url = await _bind_result(
        session,
        user_id=user_id,
        panel_user_uuid=panel_user_uuid,
        updated=updated,
        settings=settings,
    )
    rotation.state = "completed"
    rotation.new_short_uuid = str(updated["shortUuid"])
    rotation.completed_at = datetime.now(UTC)
    await session.commit()
    return updated, url
