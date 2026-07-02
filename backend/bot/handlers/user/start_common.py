from aiogram import Router
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.registration_invite_gate import (
    resolve_referrer_user_id,
    telegram_start_referral_lookup_candidates,
)
from config.settings import Settings

router = Router(name="user_start_router")


def _remnashop_referral_compat_enabled(settings: Settings) -> bool:
    return bool(settings.compatibility_settings.remnashop_referral_code_compat_enabled)


def _referral_code_lookup_candidates(
    raw_ref_value: str,
    *,
    remnashop_compat: bool,
) -> list[str]:
    return telegram_start_referral_lookup_candidates(
        raw_ref_value,
        remnashop_compat=remnashop_compat,
    )


async def _resolve_referrer_from_start_ref(
    session: AsyncSession,
    raw_ref_value: str,
    *,
    settings: Settings,
    current_user_id: int,
) -> int | None:
    return await resolve_referrer_user_id(
        session,
        raw_ref_value,
        settings=settings,
        current_user_id=current_user_id,
        source="telegram_start",
    )
