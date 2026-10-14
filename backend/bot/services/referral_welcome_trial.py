"""Referral welcome bonus added to the free trial instead of granted on its own."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.partner_program_service import PartnerProgramService
from bot.services.registration_invite_gate import referral_program_enabled
from config.settings import Settings


def free_trial_enabled(settings: Settings) -> bool:
    return bool(
        settings.TRIAL_ENABLED
        and settings.TRIAL_DURATION_DAYS > 0
        and not settings.TRIAL_PAYMENT_ENABLED
    )


def referral_welcome_bonus_joins_trial(settings: Settings) -> bool:
    """Whether the welcome bonus waits for the trial instead of a separate grant."""
    if not settings.REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL:
        return False
    if int(settings.referral_settings.welcome_bonus_days) <= 0:
        return False
    return free_trial_enabled(settings)


async def referral_welcome_trial_bonus_days(
    session: AsyncSession,
    settings: Settings,
    user: Any,
) -> int:
    """Return the welcome bonus days to add to this user's trial, or 0."""
    if not referral_welcome_bonus_joins_trial(settings):
        return 0
    if user.referral_welcome_bonus_claimed_at is not None:
        return 0
    eligible = referral_program_enabled(settings) and bool(user.referred_by_id)
    if not eligible:
        eligible = await PartnerProgramService(settings).client_welcome_bonus_eligible(
            session,
            user_id=int(user.user_id),
        )
    if not eligible:
        return 0
    # Same Telegram rule as the separate welcome bonus grant.
    from bot.app.web.webapp.auth_common import _referral_welcome_telegram_required_reason

    if _referral_welcome_telegram_required_reason(settings, user):
        return 0
    return max(0, int(settings.referral_settings.welcome_bonus_days))
